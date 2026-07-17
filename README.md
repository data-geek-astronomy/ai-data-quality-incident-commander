# AI Data Quality Incident Commander

Full-stack AI/data reliability app that detects broken datasets, creates incident briefs, recommends fixes, tracks status, and generates postmortems.

## Why this project stands out

This is not a basic RAG chatbot. It models a real AI company workflow: data contracts, anomaly detection, severity scoring, incident state, AI root-cause assistance, human approval, and operational reporting.

## Features

- CSV upload with selectable dataset contracts
- Demo incident drills for commerce orders, payments, and product events
- Checks for missing schema columns, null spikes, duplicates, primary-key collisions, invalid timestamps, unexpected categories, outliers, negative metrics, and distribution shift
- AI root-cause brief using `OPENAI_API_KEY` when available
- Deterministic fallback when no API key is set
- SQLite incident store
- Status workflow: open, investigating, fix ready, resolved
- Recommended SQL/Python remediation snippets
- Markdown postmortem generator
- React operations dashboard

## Architecture

```text
React UI
  -> FastAPI backend
    -> pandas / numpy data quality engine
    -> optional OpenAI root-cause brief
    -> SQLite incident store
```

## Local setup

Backend:

```bash
cd "/Users/aravindkumar/Research agent/backend"
python -m pip install -r requirements.txt
export OPENAI_API_KEY="your_key_here"   # optional
uvicorn main:app --reload --port 8000
```

You can also put your key in `backend/.env`:

```bash
OPENAI_API_KEY=your_key_here
OPENAI_MODEL=gpt-4o-mini
```

Frontend:

```bash
cd "/Users/aravindkumar/Research agent/frontend"
npm install
npm start
```

Open `http://localhost:3000`.

## Test

```bash
cd "/Users/aravindkumar/Research agent/backend"
python -m pytest
```

## Sample uploads

Use these CSVs in the upload panel:

- `sample_uploads/orders_broken.csv` with data type `Commerce Orders`
- `sample_uploads/payments_broken.csv` with data type `Payments Ledger`
- `sample_uploads/product_events_broken.csv` with data type `Product Events`

## GitHub push commands

```bash
cd "/Users/aravindkumar/Research agent"
git init
git add README.md backend frontend package.json start.sh QUICK_START.md
git commit -m "Build AI data quality incident commander"
git branch -M main
git remote add origin https://github.com/data-geek-astronomy/ai-data-quality-incident-commander.git
git push -u origin main
```

If the remote already exists:

```bash
git remote set-url origin https://github.com/data-geek-astronomy/ai-data-quality-incident-commander.git
git push -u origin main
```

## Hugging Face deployment note

For Hugging Face Spaces, use a Docker Space so the React build and FastAPI server can run together. Keep `OPENAI_API_KEY` as a Space secret.
