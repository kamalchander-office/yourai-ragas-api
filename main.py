"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  main.py — The YourAI RAGAs API Server                                      ║
║                                                                              ║
║  WHAT THIS FILE IS:                                                          ║
║  This is the SERVER. It runs on a machine and waits for the QA team's       ║
║  scripts to send it questions. When a question arrives, it forwards it to   ║
║  OpenAI and sends the answer back.                                           ║
║                                                                              ║
║  Think of it like a POST OFFICE:                                             ║
║    QA script → sends a letter (question) to this server                     ║
║    This server → opens the letter, forwards it to OpenAI                    ║
║    OpenAI → writes a reply (answer)                                          ║
║    This server → puts the reply in an envelope and sends it back            ║
║                                                                              ║
║  WHO RUNS THIS:                                                              ║
║  The development team. The QA team never touches this file.                  ║
║                                                                              ║
║  HOW TO START IT:                                                            ║
║    uv run uvicorn main:app --host 127.0.0.1 --port 8001                     ║
║                                                                              ║
║  TWO ENDPOINTS (URLs this server listens on):                               ║
║    GET  /health    → just checks if the server is running (like a ping)     ║
║    POST /v1/query  → the real endpoint — receives a question, returns answer ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

# ── IMPORTS ───────────────────────────────────────────────────────────────────
# Python libraries we need. Each one is a toolbox someone else built.

import logging   # lets us print timestamped messages to the terminal
import os        # lets us read environment variables (from .env file)
import sys

from dotenv import load_dotenv
# python-dotenv reads the .env file and makes its values available via os.environ
# Without this, we'd have to hardcode secrets directly in the code — very bad practice

from fastapi import Depends, FastAPI, HTTPException, status
# FastAPI is the web framework — it handles all the HTTP plumbing for us
# Depends = "run this function before running the route" (used for auth)
# HTTPException = how we send error responses (401, 403, 500, etc.)
# status = HTTP status code constants (status.HTTP_401_UNAUTHORIZED = 401)

from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
# HTTPBearer = tells FastAPI to look for "Authorization: Bearer <token>" in headers
# HTTPAuthorizationCredentials = the object that holds the token once extracted

from pydantic import BaseModel
# Pydantic validates data shapes. If the QA team sends a request without a
# 'question' field, Pydantic catches it and returns a clear error automatically.


# ── STEP 0: LOAD SECRETS ─────────────────────────────────────────────────────
#
# load_dotenv() reads the .env file line by line and puts each value into
# the process's environment variables — like putting sticky notes in memory.
#
# IMPORTANT: This must happen BEFORE we read API keys from the environment below.

load_dotenv()

from llm import config as llm_config
from llm.env_validate import (
    is_gemini_placeholder,
    is_openai_placeholder,
    is_openrouter_placeholder,
)
from llm.router import chat, get_active_model

# Set up logging so every request prints a timestamped line to the terminal.
# Format example: "2026-05-13 10:32:11  INFO  Query received: What is habeas corpus?"
# This lets the dev team watch traffic in real time.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
)
log = logging.getLogger(__name__)
# __name__ = the name of this module ("main") — helps identify which file logged the message


# ── STEP 1: READ CONFIG FROM .env ────────────────────────────────────────────
#
# os.environ["KEY"] reads a variable from the environment.
# Using ["KEY"] (square brackets) instead of .get("KEY") is intentional:
# it RAISES AN ERROR immediately if the key is missing — better to crash on
# startup than to fail silently on the first real request.

BEARER_TOKEN = os.environ["API_BEARER_TOKEN"]  # The password QA team sends with every request

# LLM_PROVIDER in .env selects openai | gemini | openrouter (see llm/router.py).
if llm_config.LLM_PROVIDER == "gemini":
    if is_gemini_placeholder(llm_config.GEMINI_API_KEY):
        sys.exit(
            "ERROR: GEMINI_API_KEY is missing or still a placeholder in .env.\n"
            "Set LLM_PROVIDER=gemini and add a real Gemini API key."
        )
elif llm_config.LLM_PROVIDER == "openrouter":
    if is_openrouter_placeholder(llm_config.OPENROUTER_API_KEY):
        sys.exit(
            "ERROR: OPENROUTER_API_KEY is missing or still a placeholder in .env.\n"
            "Set LLM_PROVIDER=openrouter and add a real OpenRouter API key."
        )
elif is_openai_placeholder(llm_config.OPENAI_API_KEY):
    sys.exit(
        "ERROR: OPENAI_API_KEY is missing or still a placeholder in .env.\n"
        "Add an OpenAI key or set LLM_PROVIDER=gemini / openrouter."
    )

log.info(
    "LLM provider: %s (model: %s)",
    llm_config.LLM_PROVIDER,
    get_active_model(),
)


# ── STEP 2: CREATE THE FASTAPI APPLICATION ───────────────────────────────────
#
# FastAPI() is the main app object. Everything else attaches to it.
# title/description/version appear in the auto-generated docs at /docs

app = FastAPI(
    title="YourAI RAGAs API",
    description="Bespoke wrapper exposing the YourAI chat agent for QA evaluation.",
    version="0.1.0",
)


# ── STEP 3: AUTHENTICATION ───────────────────────────────────────────────────
#
# We don't want random people calling this API — only the QA team.
# We protect it with a BEARER TOKEN — a long random password that the QA team
# includes in every request header, like:
#   Authorization: Bearer b68596d90b0ebf8ba...
#
# How it works:
#   1. bearer_scheme extracts the token from the "Authorization" header
#   2. verify_token() checks if it matches our secret token from .env
#   3. If it doesn't match → reject the request with a 401 error
#   4. If it matches → let the request through to the route handler
#
# The Depends() mechanism means FastAPI calls verify_token() AUTOMATICALLY
# before running any route that declares it as a dependency. The route handler
# never even runs if auth fails.

bearer_scheme = HTTPBearer()
# HTTPBearer tells FastAPI: "look for 'Authorization: Bearer <token>' in headers"

def verify_token(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> None:
    """
    Check the bearer token. Raise HTTP 401 if it's wrong.

    This function runs before every protected route.
    Think of it as the security guard at the front door.
    """
    if credentials.credentials != BEARER_TOKEN:
        # Log a warning so devs can see if someone is trying invalid tokens
        log.warning("Rejected request — bad token")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing bearer token.",
        )
    # If we reach here without raising, the token is valid — gate is open


# ── STEP 4: REQUEST AND RESPONSE SHAPES (PYDANTIC MODELS) ───────────────────
#
# These classes define exactly what JSON the API accepts and returns.
#
# WHY THIS MATTERS FOR QA:
# RAGAs needs four specific fields to score an answer:
#   question     — what was asked
#   answer       — what the AI said
#   contexts     — document chunks used to form the answer (empty in Tier 1)
#   ground_truth — the correct answer (QA team provides this separately)
#
# Our API returns question + answer + contexts.
# The QA team's client.py combines that with ground_truth from test_cases.json.

class QueryRequest(BaseModel):
    """
    The shape of the JSON body the QA team sends TO this API.

    Example request body:
    {
        "question": "What is habeas corpus?",
        "intent": "Legal Q&A"
    }
    """
    question: str
    # Required. If missing, FastAPI automatically returns a 422 error.

    intent: str = "General Chat"
    # Which YourAI mode is being tested.
    # Default = "General Chat" if not specified.
    # Values: "General Chat", "Legal Q&A", "Legal Research",
    #         "Case Law Analysis", "Find Document", "Clause Analysis", "Clause Comparison"

    system_prompt: str | None = None
    # Optional. Lets the QA team override the system prompt to test different
    # persona configurations without restarting the server.
    # If not provided, the default legal assistant prompt is used.


class QueryResponse(BaseModel):
    """
    The shape of the JSON body this API sends BACK to the QA team.

    Example response body:
    {
        "question": "What is habeas corpus?",
        "answer": "Habeas corpus is a legal action that...",
        "contexts": [],
        "model": "gpt-4o-mini"
    }
    """
    question: str
    # Echoed back so client.py can match the response to the right test case
    # (useful if the QA team ever parallelises calls)

    answer: str
    # The full text of the AI's response

    contexts: list[str]
    # The document chunks that were retrieved to help form the answer.
    # In Tier 1 this is always [] because we have no document retrieval yet.
    # In Tier 2 (Chroma vector store) this will contain actual legal text excerpts.
    # RAGAs uses this field for faithfulness, context_precision, context_recall metrics.

    model: str
    # Which model produced this answer — for traceability in the QA report


# ── STEP 5: ROUTE HANDLERS ───────────────────────────────────────────────────
#
# Routes are the actual endpoints — the URLs the API listens on.
# Each route is a Python function decorated with @app.get() or @app.post()

@app.get("/health")
def health():
    """
    Liveness check endpoint.

    PURPOSE: Before the QA team runs their full test suite, client.py calls
    this endpoint first to confirm the server is alive. If this fails,
    the script stops immediately with a clear error message instead of
    sending 75 questions and getting 75 confusing errors back.

    Returns: {"ok": true}
    """
    return {"ok": True}


@app.post(
    "/v1/query",
    response_model=QueryResponse,         # FastAPI will validate our return value against this shape
    dependencies=[Depends(verify_token)], # Auth runs FIRST — if token is bad, we never reach the function body
)
def query(body: QueryRequest) -> QueryResponse:
    """
    The main endpoint. Receives a question, sends it to OpenAI, returns the answer.

    FLOW:
      1. Auth check (automatic via Depends above)
      2. Log the incoming question
      3. Build the system prompt (the AI's "personality/role" instructions)
      4. Call OpenAI with system prompt + user question
      5. Extract the answer text
      6. Return it in the QueryResponse format

    The QA team's client.py calls this endpoint once per test case.
    """

    # Log the question so devs can monitor activity in the terminal
    # [:80] = only log first 80 characters to keep logs readable
    log.info("Query received — intent: %s | question: %s", body.intent, body.question[:80])

    # ── Build the system prompt ───────────────────────────────────────────────
    #
    # The system prompt is the instruction we give the AI BEFORE the user's question.
    # It defines the AI's role, personality, and constraints.
    # Think of it as the briefing you give a new employee on their first day.
    #
    # The QA team can override this via body.system_prompt to test whether
    # different instructions produce better or worse answers.
    # If they don't override, we use this default legal assistant prompt.

    system = body.system_prompt or (
        "You are a helpful AI legal assistant for a US law firm. "
        "Answer questions clearly and accurately. "
        "If you do not know the answer, say so — do not guess."
    )

    # ── Call configured LLM (OpenAI / Gemini / OpenRouter via llm.router) ───
    answer = chat(
        body.question,
        system_text=system,
        temperature=0.2,
    )
    log.info("Answer generated — %d characters", len(answer))

    # ── Return the response ───────────────────────────────────────────────────
    #
    # We return a QueryResponse object. FastAPI automatically serialises it to JSON.
    # The QA team's client.py reads this JSON and saves it to results.json.

    return QueryResponse(
        question=body.question,   # echo the question back
        answer=answer,            # the AI's full response text
        contexts=[],              # Tier 1: no retrieval — empty list
                                  # Tier 2: this will contain real document chunks
        model=get_active_model(),  # record which model answered
    )
