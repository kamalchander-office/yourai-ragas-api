"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  ingest_cases.py — Import test cases from a Word or Excel document          ║
║                                                                              ║
║  WHAT THIS FILE DOES:                                                        ║
║  The QA team writes test questions in Excel or Word — that's their natural  ║
║  tool. But our pipeline needs the data in JSON format (a structured text    ║
║  format that Python scripts can read easily).                                ║
║                                                                              ║
║  This script is the BRIDGE between the two:                                 ║
║    test_cases.xlsx  →  [this script]  →  test_cases.json                   ║
║                                                                              ║
║  Think of it like a TRANSLATOR. The QA team speaks Excel. The scripts       ║
║  speak JSON. This file translates between the two.                           ║
║                                                                              ║
║  WHAT THE QA TEAM'S EXCEL SHOULD LOOK LIKE:                                 ║
║  ┌──────────┬──────────────────────────────┬────────────┬───────────────┐   ║
║  │ question │ case_type                    │ intent     │ ground_truth  │   ║
║  ├──────────┼──────────────────────────────┼────────────┼───────────────┤   ║
║  │ What is  │ positive                     │ Legal Q&A  │ (optional)    │   ║
║  │ habeas   │                              │            │               │   ║
║  │ corpus?  │                              │            │               │   ║
║  └──────────┴──────────────────────────────┴────────────┴───────────────┘   ║
║                                                                              ║
║  ground_truth is OPTIONAL here — generate_cases.py will fill it in.         ║
║                                                                              ║
║  HOW TO RUN:                                                                 ║
║    python ingest_cases.py --file test_cases.xlsx                             ║
║    python ingest_cases.py --file test_cases.docx                             ║
║    python ingest_cases.py --file test_cases.xlsx --merge                    ║
║    (--merge adds to existing cases instead of replacing them)               ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

import argparse   # handles command-line arguments (the --file and --merge flags)
import json       # reads and writes JSON files
import sys        # lets us exit the script with an error message
from pathlib import Path  # modern way to handle file paths in Python


# ── STEP 1: READ COMMAND-LINE ARGUMENTS ──────────────────────────────────────
#
# argparse lets us accept arguments when running the script from terminal.
# Example: python ingest_cases.py --file test_cases.xlsx --merge
#                                   ↑ this is args.file   ↑ this sets args.merge = True

parser = argparse.ArgumentParser(description="Import test cases from a Word/Excel doc.")

parser.add_argument(
    "--file",
    required=True,   # script will error and print usage if --file is missing
    help="Path to your .xlsx, .docx, or .pdf file"
)
parser.add_argument(
    "--merge",
    action="store_true",  # if --merge is present, args.merge = True; if absent, args.merge = False
    help="Add to existing test_cases.json instead of replacing it"
)

args = parser.parse_args()

# Path().expanduser() handles ~ (home directory shortcut)
# .resolve() converts relative paths to absolute paths
SOURCE_FILE = Path(args.file).expanduser().resolve()
QA_DIR      = Path(__file__).parent          # the folder this script lives in
OUT_FILE    = QA_DIR / "test_cases.json"     # where we save the output

# Check the file actually exists before trying to read it
if not SOURCE_FILE.exists():
    sys.exit(f"ERROR: File not found: {SOURCE_FILE}")

# Get the file extension (.xlsx, .docx, .pdf) in lowercase
suffix = SOURCE_FILE.suffix.lower()


# ── STEP 2: HELPER FUNCTIONS ──────────────────────────────────────────────────

def normalise(row: dict) -> dict:
    """
    Clean up a row from the spreadsheet before we use it.

    PROBLEM: Column names in real Excel files are messy.
    Someone might type "Question " (with a space), or "QUESTION" (all caps),
    or "Ground Truth" (two words). We need to handle all variations.

    SOLUTION: Convert all keys to lowercase and strip whitespace from values.

    Example:
      Input:  {"Question ": "What is habeas corpus?", "CASE_TYPE": " positive "}
      Output: {"question": "What is habeas corpus?", "case_type": "positive"}
    """
    return {k.strip().lower(): str(v).strip() for k, v in row.items() if v}


# The four valid case types. If the spreadsheet has something else, we default to "positive".
VALID_TYPES = {"positive", "negative", "edge", "adversarial"}


def build_case(row: dict, idx: int) -> dict:
    """
    Turn a raw spreadsheet row into a clean, structured test case dict.

    This is the CORE function. Every row from Excel/Word passes through here.

    Args:
        row: a dictionary like {"question": "...", "case_type": "...", ...}
        idx: the row number — used to auto-generate an ID if none is given

    Returns:
        A clean dict with id, question, ground_truth, case_type, intent
        OR None if the row is empty/invalid
    """

    # Get the question — strip whitespace
    question = row.get("question", "").strip()

    # Skip completely empty rows (common in Excel files with blank rows)
    if not question:
        return None

    # Get ground_truth — try multiple possible column name spellings
    # ("ground_truth", "groundtruth", "expected" — QA teams use different names)
    ground_truth = row.get(
        "ground_truth",
        row.get("groundtruth",
        row.get("expected", ""))   # empty string if none of the above exist
    ).strip()

    # Auto-generate an ID if the spreadsheet doesn't have one
    # TC-001, TC-002, etc.
    case_id = row.get("id", f"TC-{idx:03d}").strip() or f"TC-{idx:03d}"
    # :03d = format as 3-digit number with leading zeros (1 → "001")

    # Get case_type — accept "type" as an alternative column name
    case_type = row.get("case_type", row.get("type", "positive")).strip().lower()
    if case_type not in VALID_TYPES:
        case_type = "positive"   # default to positive if unrecognised value

    # Get intent — which YourAI mode this question tests
    intent = row.get("intent", "General Chat").strip()

    return {
        "id":           case_id,
        "question":     question,
        "ground_truth": ground_truth,  # may be empty — generate_cases.py will fill it
        "case_type":    case_type,
        "intent":       intent,
        "source":       "human",       # these came from a human-written doc
    }


# ── STEP 3: FILE PARSERS ──────────────────────────────────────────────────────
# One function per file format. Each returns a list of test case dicts.

def parse_xlsx(path: Path) -> list[dict]:
    """
    Read an Excel (.xlsx) file and extract test cases.

    How it works:
      - Opens the first sheet (ws = worksheet)
      - Reads row 1 as column headers
      - Reads each subsequent row as a test case
      - Returns a list of test case dicts

    Requires: openpyxl library (installed via pip/uv)
    """
    import openpyxl

    # Load the workbook (the Excel file) and get the active sheet
    wb = openpyxl.load_workbook(path)
    ws = wb.active   # "active" = the sheet that was open when the file was saved

    # Read all rows into a Python list
    # values_only=True means we get the cell values, not the cell objects
    rows = list(ws.iter_rows(values_only=True))

    if not rows:
        sys.exit("ERROR: Excel file is empty.")

    # First row = headers. Convert to lowercase strings.
    # Example: ("Question", "Case Type", "Intent") → ["question", "case type", "intent"]
    headers = [str(h).strip().lower() if h else "" for h in rows[0]]
    print(f"  Columns found in Excel: {headers}")

    cases = []
    for i, row in enumerate(rows[1:], start=1):  # skip header row (rows[0])
        # Zip headers with cell values to create a dict
        # Example: ["question", "case_type"] + ("What is...", "positive") → {"question": "What is...", "case_type": "positive"}
        raw = {headers[j]: (cell or "") for j, cell in enumerate(row)}
        case = build_case(normalise(raw), i)
        if case:   # skip None (empty rows)
            cases.append(case)

    return cases


def parse_docx(path: Path) -> list[dict]:
    """
    Read a Word (.docx) file and extract test cases from tables.

    How it works:
      - Opens the Word document
      - Looks for tables (most structured way to store test cases in Word)
      - Treats the first row of each table as headers
      - Falls back to reading plain paragraphs if no tables found

    Requires: python-docx library
    """
    from docx import Document

    doc = Document(path)

    cases = []
    idx = 1

    # Iterate through all tables in the document
    for table in doc.tables:
        if not table.rows:
            continue   # skip empty tables

        # First row = column headers (same logic as Excel)
        headers = [cell.text.strip().lower() for cell in table.rows[0].cells]
        print(f"  Table found in Word doc — columns: {headers}")

        # Every row after the first = one test case
        for row in table.rows[1:]:
            raw = {headers[j]: cell.text.strip() for j, cell in enumerate(row.cells)}
            case = build_case(raw, idx)
            if case:
                cases.append(case)
                idx += 1

    # Fallback: if the Word doc has no tables, treat each paragraph as a question
    # (less structured but better than failing completely)
    if not cases:
        print("  No tables found — trying to read as a list of questions...")
        for i, para in enumerate(doc.paragraphs, start=1):
            text = para.text.strip()
            if text and len(text) > 10:   # skip very short lines (headings, etc.)
                cases.append(build_case({"question": text}, i))

    return cases


def parse_pdf(path: Path) -> list[dict]:
    """
    Read a PDF file and extract questions from the text.

    NOTE: PDFs are the hardest format to parse reliably.
    We do our best — extracting any line that ends with "?"
    The QA team will likely need to review the output.

    Requires: pypdf library
    """
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    lines = []

    # Extract text from every page
    for page in reader.pages:
        text = page.extract_text() or ""
        lines.extend(text.split("\n"))  # split into individual lines

    # Keep only lines that look like questions (end with "?" and are long enough)
    cases = []
    for i, line in enumerate(lines, start=1):
        line = line.strip()
        if line.endswith("?") and len(line) > 10:
            cases.append(build_case({"question": line}, i))

    print(f"  Extracted {len(cases)} question lines from PDF.")
    print("  NOTE: ground_truth will be empty — run generate_cases.py to fill it in.")
    return cases


# ── STEP 4: CHOOSE THE RIGHT PARSER ──────────────────────────────────────────
# Look at the file extension and call the appropriate parser function.

print(f"\nReading: {SOURCE_FILE.name}  (format: {suffix})\n")

if suffix == ".xlsx":
    new_cases = parse_xlsx(SOURCE_FILE)
elif suffix == ".docx":
    new_cases = parse_docx(SOURCE_FILE)
elif suffix == ".pdf":
    new_cases = parse_pdf(SOURCE_FILE)
else:
    sys.exit(f"ERROR: Unsupported format '{suffix}'. Please use .xlsx, .docx, or .pdf")

if not new_cases:
    sys.exit("ERROR: No test cases could be extracted. Check the file format and column names.")


# ── STEP 5: MERGE OR REPLACE ──────────────────────────────────────────────────
#
# TWO MODES:
#
# REPLACE (default, no --merge flag):
#   Overwrites test_cases.json completely with the new cases.
#   Use this when starting fresh or replacing your entire test set.
#
# MERGE (with --merge flag):
#   Reads existing test_cases.json, then ADDS the new cases to it.
#   Uses case IDs to avoid duplicates — won't add a case if its ID already exists.
#   Use this when adding a new batch of cases without losing previous ones.

if args.merge and OUT_FILE.exists():
    # Load what's already in test_cases.json
    existing = json.loads(OUT_FILE.read_text())
    # Build a set of existing IDs for fast duplicate checking
    existing_ids = {c["id"] for c in existing}
    # Only add cases whose ID doesn't already exist
    added = [c for c in new_cases if c["id"] not in existing_ids]
    final = existing + added
    print(f"Merged: added {len(added)} new cases to {len(existing)} existing cases.")
    print(f"Skipped {len(new_cases) - len(added)} duplicates (same ID already existed).")
else:
    final = new_cases
    print(f"Saving {len(final)} cases to test_cases.json (replacing any previous content).")


# ── STEP 6: SAVE OUTPUT ───────────────────────────────────────────────────────
#
# json.dumps converts the Python list of dicts into a JSON string.
# indent=2 makes it human-readable (nicely indented) rather than one long line.

OUT_FILE.write_text(json.dumps(final, indent=2))
print(f"\n✓ Saved → {OUT_FILE}")
print(f"  {len(final)} total test cases ready.")
print(f"\nNext step: run  python generate_cases.py  to let AI fill in correct answers.")
