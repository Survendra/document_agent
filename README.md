# Document Intelligence Agent

A local Python pipeline that extracts page-sourced facts from PDFs with
`qwen2.5:7b` through Ollama, validates the extraction, detects cross-document
conflicts, removes duplicate records, and writes JSON, Markdown, and PDF output.

## Safety and verification behavior

- Extraction uses Ollama's JSON-schema constrained response format.
- Every non-null field is expected to carry a filename and page number.
- Invalid source references are removed and reported by validation.
- Conflicting values are retained as alternatives; no winner is guessed.
- Merging and report generation are deterministic Python operations.
- Missing values remain `null` or are rendered as `Not Available`.
- Raw OCR text and model payloads are transient and cleared after each document.
- Bounded pipeline memory compacts old stage metadata without modifying the
  persisted extraction artifacts.

LLM output still requires human review when validation reports weak grounding,
poor OCR, or a conflict.

## Prerequisites

1. Python 3.11 or newer.
2. [Ollama](https://ollama.com/) running locally.
3. The configured model:

   ```powershell
   ollama pull qwen2.5:7b
   ```

4. Optional for scanned PDFs: install Tesseract OCR and ensure `tesseract.exe`
   is on `PATH`. Text-based PDFs work without it.

## Install

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

## Run

```powershell
python main.py sample_docs\semester1.pdf sample_docs\semester2.pdf -o outputs
```

Use `--no-pdf` to write only JSON and Markdown. Runtime settings can be changed
with environment variables:

- `OLLAMA_URL` (default `http://localhost:11434`)
- `OLLAMA_MODEL` (default `qwen2.5:7b`)
- `OLLAMA_TIMEOUT`
- `OLLAMA_MAX_RETRIES`
- `CONTEXT_CHAR_BUDGET`
- `PAGE_CHUNK_CHARS`
- `OCR_MIN_CHARS`
- `OCR_LANGUAGE`

## Outputs

- `<document>.extraction.json`: schema-validated extracted facts
- `<document>.validation.json`: grounding, missing, and duplicate issues
- `unified.json`: merged fields, records, conflicts, and warnings
- `result.json`: complete machine-readable pipeline result
- `report.md`: professional report
- `report.pdf`: rendered report
- `memory_summary.json`: compaction metadata only; no raw document text

## Tests

```powershell
python -m pytest
```

test
