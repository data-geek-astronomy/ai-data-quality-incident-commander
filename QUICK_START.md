# AI Data Quality Incident Commander Quick Start

## 1. Install backend dependencies

```bash
cd "/Users/aravindkumar/Research agent/backend"
python -m pip install -r requirements.txt
```

## 2. Start the backend

```bash
cd "/Users/aravindkumar/Research agent/backend"
export OPENAI_API_KEY="your_key_here"   # optional
uvicorn main:app --reload --port 8000
```

Or use `backend/.env`:

```bash
OPENAI_API_KEY=your_key_here
OPENAI_MODEL=gpt-4o-mini
```

## 3. Start the frontend

```bash
cd "/Users/aravindkumar/Research agent/frontend"
npm install
npm start
```

## 4. Open the app

Visit `http://localhost:3000`.

## 5. Test the workflow

Run one of the built-in incident drills:

- Commerce Orders
- Payments Ledger
- Product Events

Then inspect the incident detail panel, change the status, and generate a postmortem.

Sample CSVs are in `sample_uploads/`.
