# Aegis Knowledge Hub Quick Start

## 1. Install backend dependencies

```bash
cd "/Users/aravindkumar/Research agent/backend"
python -m pip install -r requirements.txt
```

## 2. Start the backend

```bash
cd "/Users/aravindkumar/Research agent/backend"
uvicorn main:app --reload --port 8000
```

Optional LLM refinement:

```bash
export OPENAI_API_KEY="your_key_here"
export OPENAI_MODEL="gpt-4o-mini"
```

## 3. Start the frontend

```bash
cd "/Users/aravindkumar/Research agent/frontend"
npm install
npm start
```

## 4. Try the project

Open `http://localhost:3000`, re-index the synthetic inputs, inspect readiness issues, search for `edge router failover rollback`, and ask one of the starter questions.

Synthetic inputs live in `knowledge_inputs/network_knowledge_assets.json`.
