---
title: Aegis Knowledge Hub
colorFrom: green
colorTo: gray
sdk: docker
app_port: 7860
pinned: false
---

# Aegis Knowledge Hub

AI-ready network knowledge platform that turns runbooks, SOPs, standards, configuration templates, telemetry summaries, policies, and incident records into governed, searchable context assets.

## Why this project matches the role

This project demonstrates the work behind trusted AI and agentic systems: knowledge curation, metadata standards, lineage, freshness, ownership, quality controls, retrieval, grounding, and source-backed answers.

## Features

- Synthetic network operations corpus in `knowledge_inputs/network_knowledge_assets.json`
- Asset ingestion and chunking for retrieval
- Metadata, ownership, lineage, freshness, stewardship, and status checks
- AI readiness score for every knowledge asset
- Governance dashboard with issue counts by control area
- Keyword/TF-IDF style local search with source metadata
- Ask panel that returns grounded answers and citations
- Optional OpenAI-powered answer refinement when `OPENAI_API_KEY` is set
- FastAPI backend, React frontend, SQLite persistence
- Docker setup for Hugging Face Spaces

## Architecture

```text
Synthetic knowledge inputs
  -> FastAPI ingestion and validation
  -> SQLite asset and chunk index
  -> local retrieval engine
  -> React governance and Q&A UI
```

## Local setup

Backend:

```bash
cd "/Users/aravindkumar/Research agent/backend"
python -m pip install -r requirements.txt
uvicorn main:app --reload --port 8000
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

## Hugging Face Spaces

This repo is configured as a Docker Space. Build the React frontend before pushing:

```bash
cd "/Users/aravindkumar/Research agent/frontend"
npm run build
```

Then push the repo to a Hugging Face Space. Keep `OPENAI_API_KEY` as a Space secret if you want LLM-refined answers.
