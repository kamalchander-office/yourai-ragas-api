"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  client.py — Send every test question to YourAI and save the answers        ║
║                                                                              ║
║  WHAT THIS FILE DOES:                                                        ║
║  This script is the COLLECTOR. It reads every question from test_cases.json ║
║  sends each one to the YourAI API, and saves the answers.                   ║
║                                                                              ║
║  Think of it as a QA tester sitting at a computer:                          ║
║    1. Opens the test sheet (test_cases.json)                                ║
║    2. Types question 1 into YourAI → writes down the answer                 ║
║    3. Types question 2 into YourAI → writes down the answer                 ║
║    4. Repeats for all questions                                              ║
║    5. Saves all answers in one file (results.json)                          ║
║                                                                              ║
║  WHY A SEPARATE FILE FROM run_eval.py?                                       ║
║  Collecting answers (this file) and scoring answers (run_eval.py) are       ║
║  deliberately split into two steps. If RAGAs has an error during scoring,   ║
║  you don't have to call the API again — just re-run run_eval.py             ║
║  against the already-saved results.json.                                    ║
║                                                                              ║
║  HOW TO RUN:                                                                 ║
║    python client.py                                      ← uses localhost    ║
║    python client.py --api-url https://yourai-api.com    ← uses real server  ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

import argparse   # handles the --api-url command-line argument
import json       # reads test_cases.json, writes results.json
import os         # reads environment variables from .env
import sys        # exits with error messages
import time       # provides time.sleep() for polite pacing between calls
from pathlib import Path  # handles file paths

import requests           # makes HTTP calls (the QA script's way of "calling" the API)
from dotenv import load_dotenv   # reads the .env file


# ── STEP 1: LOAD SECRETS ──────────────────────────────────────────────────────
#
# The .env file is in the project root, one folder above this qa/ script.
# load_dotenv() reads it and puts the values into memory so we can use them below.

load_dotenv(Path(__file__).parent.parent / ".env")

# Read the bearer token — the "password" we send with every API request
BEARER_TOKEN = os.environ.get("API_BEARER_TOKEN", "")
if not BEARER_TOKEN:
    sys.exit(
        "ERROR: API_BEARER_TOKEN not found in .env\n"
        "The API requires authentication. Ask Arjun for the bearer token."
    )


# ── STEP 2: COMMAND-LINE ARGUMENTS ───────────────────────────────────────────
#
# This lets the QA team point the script at any server URL.
# Default = localhost (for local testing)
# Real use = the production YourAI API URL

parser = argparse.ArgumentParser(description="Collect YourAI answers for RAGAs evaluation.")
parser.add_argument(
    "--api-url",
    default="http://127.0.0.1:8001",
    help="Base URL of the YourAI API (default: http://127.0.0.1:8001)"
)
args = parser.parse_args()

# Clean up the URL (remove trailing slash to avoid double-slashes in paths)
API_URL   = args.api_url.rstrip("/")
QUERY_URL = f"{API_URL}/v1/query"   # the full endpoint URL we'll POST to

# HTTP headers — sent with every request
# "Authorization: Bearer <token>" is the standard way to authenticate API calls
HEADERS = {"Authorization": f"Bearer {BEARER_TOKEN}"}


# ── STEP 3: FILE PATHS ────────────────────────────────────────────────────────

QA_DIR          = Path(__file__).parent          # the qa/ folder
TEST_CASES_FILE = QA_DIR / "test_cases.json"     # input: questions + ground truths
RESULTS_FILE    = QA_DIR / "results.json"        # output: questions + API answers + ground truths


# ── STEP 4: MAIN FUNCTION ─────────────────────────────────────────────────────

def main():

    # ── Load test cases ───────────────────────────────────────────────────────
    # json.loads() converts the JSON string into a Python list of dicts
    test_cases = json.loads(TEST_CASES_FILE.read_text())
    print(f"Loaded {len(test_cases)} test cases from {TEST_CASES_FILE.name}")
    print(f"Sending to: {API_URL}\n")

    # ── Health check ──────────────────────────────────────────────────────────
    # Before sending 75 questions, we first hit /health to confirm the server is up.
    # If the server is down, this gives a clear error immediately
    # instead of 75 confusing "connection refused" errors.
    try:
        health_response = requests.get(f"{API_URL}/health", timeout=5)
        health_response.raise_for_status()   # raises an error if status is 4xx or 5xx
        print(f"✓ API is healthy at {API_URL}\n")
    except Exception as e:
        sys.exit(
            f"ERROR: Cannot reach the API at {API_URL}\n"
            f"  Details: {e}\n"
            f"  → Check that the API server is running and the URL is correct."
        )

    # ── Send questions one by one ─────────────────────────────────────────────
    results = []   # we'll build this list up as we go

    for i, tc in enumerate(test_cases, start=1):
        # Print progress so the QA team can see what's happening
        print(f"  [{i}/{len(test_cases)}] {tc['id']}: {tc['question'][:60]}...")

        # ── Build the request payload ─────────────────────────────────────────
        # This is the JSON body we send to POST /v1/query
        # It must match the QueryRequest model in main.py
        payload = {
            "question": tc["question"],           # the legal question
            "intent":   tc.get("intent", "General Chat"),  # which YourAI mode to use
        }

        try:
            # ── Make the HTTP POST request ────────────────────────────────────
            # requests.post() sends an HTTP POST request to the API
            # json=payload    → automatically serialises our dict to JSON and sets Content-Type header
            # headers=HEADERS → includes the Authorization: Bearer token
            # timeout=30      → if no response in 30 seconds, raise an error (don't hang forever)
            resp = requests.post(QUERY_URL, json=payload, headers=HEADERS, timeout=30)

            # raise_for_status() raises an exception if the server returned an error
            # (HTTP 4xx = client error, HTTP 5xx = server error)
            resp.raise_for_status()

            # Parse the JSON response body into a Python dict
            data = resp.json()

            # ── Build the result row ──────────────────────────────────────────
            # This is what run_eval.py will read later.
            # We combine the API's answer with the ground_truth from our test file.
            # RAGAs needs all four fields: question, answer, contexts, ground_truth
            results.append({
                "id":           tc["id"],
                "question":     tc["question"],
                "answer":       data["answer"],     # what YourAI said ← from the API response
                "contexts":     data["contexts"],   # retrieved chunks ← [] in Tier 1
                "ground_truth": tc["ground_truth"], # correct answer   ← from our test file (NOT the API)
                "case_type":    tc.get("case_type", "positive"),    # positive/negative/edge/adversarial
                "intent":       tc.get("intent", "General Chat"),   # which mode was tested
                "source":       tc.get("source", "human"),          # human or ai-generated
            })

            print(f"        ✓ Answer received ({len(data['answer'])} chars)")

        except requests.HTTPError as e:
            # The server returned an error (401 = bad token, 500 = server crashed, etc.)
            print(f"        ✗ HTTP {e.response.status_code}: {e.response.text[:100]}")

            # Still add a row so the results file stays aligned with test_cases.json
            # The error message becomes the "answer" — run_eval.py will give it a bad score
            results.append({
                "id":           tc["id"],
                "question":     tc["question"],
                "answer":       f"ERROR: HTTP {e.response.status_code}",
                "contexts":     [],
                "ground_truth": tc["ground_truth"],
                "case_type":    tc.get("case_type", "positive"),
                "intent":       tc.get("intent", "General Chat"),
                "source":       tc.get("source", "human"),
            })

        except Exception as e:
            # Catch-all for network errors, timeouts, etc.
            print(f"        ✗ Error: {e}")
            results.append({
                "id":           tc["id"],
                "question":     tc["question"],
                "answer":       f"ERROR: {str(e)[:100]}",
                "contexts":     [],
                "ground_truth": tc["ground_truth"],
                "case_type":    tc.get("case_type", "positive"),
                "intent":       tc.get("intent", "General Chat"),
                "source":       tc.get("source", "human"),
            })

        # ── Polite pacing ─────────────────────────────────────────────────────
        # Small pause between requests so we don't overwhelm the API server.
        # 0.5 seconds = 2 requests per second maximum.
        # For 75 cases: ~38 seconds of total wait time. Reasonable.
        if i < len(test_cases):
            time.sleep(0.5)

    # ── Save results ──────────────────────────────────────────────────────────
    # json.dumps with indent=2 = human-readable, nicely formatted JSON
    RESULTS_FILE.write_text(json.dumps(results, indent=2))

    # Count successes vs errors
    errors = sum(1 for r in results if r["answer"].startswith("ERROR:"))
    success = len(results) - errors

    print(f"\n✓ Done — {success}/{len(results)} answers collected successfully.")
    if errors:
        print(f"  ⚠ {errors} errors — check the output above for details.")
    print(f"✓ Results saved → {RESULTS_FILE}")
    print(f"\nNext step: run  python run_eval.py  to score these answers with RAGAs.")


# ── ENTRY POINT ───────────────────────────────────────────────────────────────
# This block only runs when the script is called directly from the terminal.
# It does NOT run if another script imports this file as a module.
# Standard Python pattern — always include this.

if __name__ == "__main__":
    main()
