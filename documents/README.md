# Local QA document fixtures

Place **PDF**, **DOCX**, or **TXT** files here. The QA pipeline reads them **from disk** (no S3 download) to build corpus-grounded questions and `ground_truth`.

## Quick start

1. Copy your file here, e.g. `CaseFile.pdf`
2. (Optional) Map YourAI `document_id` → filename in `manifest.json`:

```json
{
  "3b0d30b1-7893-4883-ae13-43289cd5eb74": "CaseFile.pdf",
  "3fa85f64-5717-4562-b3fc-2c963f66a36d": "Miranda-Research.pdf"
}
```

3. Generate grounded test data:

```bash
python qa/generate_cases.py --load-all-documents --refill-ground-truth
```

4. Upload the **same files** to the YourAI chat conversation used in `.env` (`YOURAI_CONVERSATION_ID`), then collect answers:

```bash
python qa/client.py --backend yourai
```

## Excel (`TestCases.xlsx`)

Add a column **`document_file`** with the filename only (e.g. `CaseFile.pdf`):

| question | case_type | intent | document_file |
|----------|-----------|--------|---------------|
| What rights must police read? | positive | legal Q&A | CaseFile.pdf |

Then:

```bash
python qa/ingest_cases.py --file TestCases.xlsx
python qa/generate_cases.py --from-test-cases --refill-ground-truth
```

## Environment

Optional in `.env`:

```
DOCUMENTS_DIR=/absolute/path/to/documents
GENERATE_MAX_DOCUMENT_CHARS=80000
```
