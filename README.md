Part B — Run the pipeline (every test run)
All commands assume you are in the qa folder after step 1.

cd /Users/appinvenitv/Downloads/yourai-ragas-api/qa
Step 3: Import TestCases.xlsx → test_cases.json
python3 ingest_cases.py --file ../TestCases.xlsx
Expected:

✓ Saved → .../qa/test_cases.json
About 4 cases (from your current Excel)
To add more later without losing old cases:

python3 ingest_cases.py --file ../TestCases.xlsx --merge
Step 4 (optional): Fill correct answers with AI
Uses Gemini or OpenAI from .env. Skip if you only want API answers first.

python3 generate_cases.py
This fills empty ground_truth fields in test_cases.json.

Step 5: Call YourAI and save answers
python3 client.py --backend yourai
Expected:

Progress per case: ✓ Answer received (... chars, ...ms)
File created: qa/results.json
You do not need main.py running for this step.

If it fails:

Missing required environment variables → fix .env YourAI section
401 / 403 → wrong client ID/secret or org/user IDs
Timeout → increase YOURAI_TIMEOUT_SECONDS=120
Step 6: Score answers and build report
python3 run_eval.py
Expected:

qa/scores.csv
qa/report.html — open in a browser
Takes a few minutes (RAGAs calls the judge LLM per case).

Quick reference
TestCases.xlsx
    ↓  ingest_cases.py
test_cases.json
    ↓  generate_cases.py (optional)
    ↓  client.py --backend yourai
results.json
    ↓  run_eval.py
scores.csv + report.html
