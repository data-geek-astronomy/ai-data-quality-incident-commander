import json
import math
import os
import re
import sqlite3
import uuid
from collections import Counter, defaultdict
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    load_dotenv = None

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover
    OpenAI = None

if load_dotenv is not None:
    load_dotenv(Path(__file__).resolve().parent / ".env")

ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = ROOT.parent
DATA_DIR = ROOT / "data"
DB_PATH = DATA_DIR / "knowledge_hub.db"
INPUT_DIR = PROJECT_ROOT / "knowledge_inputs"
FRONTEND_BUILD = PROJECT_ROOT / "frontend" / "build"
DATA_DIR.mkdir(exist_ok=True)
INPUT_DIR.mkdir(exist_ok=True)

AssetType = Literal["runbook", "sop", "policy", "standard", "configuration", "telemetry", "incident_record"]
Status = Literal["draft", "review", "approved", "stale"]


@asynccontextmanager
async def lifespan(_: FastAPI):
    if not asset_rows() and list(INPUT_DIR.glob("*.json")):
        ingest_assets(read_input_files())
    yield


app = FastAPI(title="Aegis Knowledge Hub", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=500)
    top_k: int = Field(default=4, ge=1, le=8)


class SearchRequest(BaseModel):
    query: str = Field(min_length=2, max_length=300)
    asset_type: str | None = None
    service: str | None = None
    owner: str | None = None
    min_readiness: int = Field(default=0, ge=0, le=100)
    top_k: int = Field(default=8, ge=1, le=20)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS assets (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            asset_type TEXT NOT NULL,
            service TEXT NOT NULL,
            owner TEXT,
            source TEXT NOT NULL,
            freshness_date TEXT,
            status TEXT NOT NULL,
            metadata TEXT NOT NULL,
            content TEXT NOT NULL,
            readiness_score INTEGER NOT NULL,
            issues TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS chunks (
            id TEXT PRIMARY KEY,
            asset_id TEXT NOT NULL,
            chunk_index INTEGER NOT NULL,
            text TEXT NOT NULL,
            metadata TEXT NOT NULL,
            FOREIGN KEY(asset_id) REFERENCES assets(id)
        )
        """
    )
    return conn


def tokenize(text: str) -> list[str]:
    stop_words = {
        "the", "and", "for", "with", "that", "this", "from", "into", "when", "then", "than", "are", "was", "were",
        "has", "have", "had", "will", "shall", "must", "can", "not", "all", "any", "per", "via", "use", "using",
    }
    return [word for word in re.findall(r"[a-z0-9_/-]+", text.lower()) if len(word) > 2 and word not in stop_words]


def chunk_text(text: str, max_words: int = 120) -> list[str]:
    paragraphs = [item.strip() for item in re.split(r"\n\s*\n", text) if item.strip()]
    chunks: list[str] = []
    current: list[str] = []
    for paragraph in paragraphs:
        words = paragraph.split()
        if current and len(current) + len(words) > max_words:
            chunks.append(" ".join(current))
            current = []
        current.extend(words)
    if current:
        chunks.append(" ".join(current))
    return chunks or [text[:1000]]


def parse_asset(payload: dict[str, Any], source: str) -> dict[str, Any]:
    metadata = payload.get("metadata", {})
    content = payload.get("content", "")
    title = str(payload.get("title") or metadata.get("title") or source)
    asset_id = str(payload.get("id") or re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-") or uuid.uuid4())[:80]
    return {
        "id": asset_id,
        "title": title,
        "asset_type": str(payload.get("asset_type") or metadata.get("asset_type") or "runbook"),
        "service": str(metadata.get("service") or payload.get("service") or "Network Services"),
        "owner": metadata.get("owner"),
        "source": source,
        "freshness_date": metadata.get("freshness_date"),
        "status": str(metadata.get("status") or "draft"),
        "metadata": metadata,
        "content": content,
    }


def readiness(asset: dict[str, Any]) -> tuple[int, list[dict[str, str]]]:
    issues: list[dict[str, str]] = []
    score = 100
    required_metadata = ["owner", "service", "freshness_date", "steward", "lineage", "retrieval_tags"]
    for field_name in required_metadata:
        value = asset["metadata"].get(field_name)
        if value in (None, "", []):
            score -= 10
            issues.append({"control": "metadata", "severity": "high", "message": f"Missing {field_name} metadata."})

    if len(asset["content"].split()) < 80:
        score -= 12
        issues.append({"control": "knowledge_quality", "severity": "medium", "message": "Content is too thin for reliable grounding."})

    if asset["status"] != "approved":
        score -= 8
        issues.append({"control": "governance", "severity": "medium", "message": "Asset is not approved for model use."})

    if asset.get("freshness_date"):
        try:
            fresh = datetime.fromisoformat(str(asset["freshness_date"]).replace("Z", "+00:00"))
            age_days = (datetime.now(timezone.utc) - fresh).days
            if age_days > 180:
                score -= 18
                issues.append({"control": "freshness", "severity": "high", "message": f"Freshness date is {age_days} days old."})
        except ValueError:
            score -= 10
            issues.append({"control": "freshness", "severity": "medium", "message": "Freshness date is not ISO formatted."})
    else:
        score -= 12

    if not re.search(r"(rollback|escalat|owner|validate|verify|monitor)", asset["content"], re.I):
        score -= 8
        issues.append({"control": "supportability", "severity": "medium", "message": "Missing operational support cues."})

    return max(0, min(100, score)), issues


def read_input_files() -> list[dict[str, Any]]:
    assets: list[dict[str, Any]] = []
    for path in sorted(INPUT_DIR.glob("*.json")):
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Could not parse {path.name}: {exc}") from exc
        records = raw if isinstance(raw, list) else raw.get("assets", [raw])
        for record in records:
            assets.append(parse_asset(record, path.name))
    return assets


def ingest_assets(assets: list[dict[str, Any]]) -> dict[str, Any]:
    with db() as conn:
        conn.execute("DELETE FROM chunks")
        conn.execute("DELETE FROM assets")
        created = now_iso()
        chunk_total = 0
        for asset in assets:
            score, issues = readiness(asset)
            conn.execute(
                """
                INSERT INTO assets VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    asset["id"],
                    asset["title"],
                    asset["asset_type"],
                    asset["service"],
                    asset.get("owner"),
                    asset["source"],
                    asset.get("freshness_date"),
                    asset["status"],
                    json.dumps(asset["metadata"]),
                    asset["content"],
                    score,
                    json.dumps(issues),
                    created,
                    created,
                ),
            )
            for index, chunk in enumerate(chunk_text(asset["content"])):
                chunk_id = f"{asset['id']}-{index}"
                chunk_meta = {
                    "title": asset["title"],
                    "asset_type": asset["asset_type"],
                    "service": asset["service"],
                    "owner": asset.get("owner"),
                    "source": asset["source"],
                    "readiness_score": score,
                }
                conn.execute("INSERT INTO chunks VALUES (?, ?, ?, ?, ?)", (chunk_id, asset["id"], index, chunk, json.dumps(chunk_meta)))
                chunk_total += 1
    return {"assets_ingested": len(assets), "chunks_indexed": chunk_total}


def asset_rows() -> list[dict[str, Any]]:
    with db() as conn:
        rows = conn.execute("SELECT * FROM assets ORDER BY readiness_score ASC, title ASC").fetchall()
    return [
        {
            **dict(row),
            "metadata": json.loads(row["metadata"]),
            "issues": json.loads(row["issues"]),
        }
        for row in rows
    ]


def chunk_rows() -> list[dict[str, Any]]:
    with db() as conn:
        rows = conn.execute(
            """
            SELECT chunks.*, assets.title, assets.asset_type, assets.service, assets.owner, assets.readiness_score
            FROM chunks
            JOIN assets ON chunks.asset_id = assets.id
            """
        ).fetchall()
    return [dict(row) for row in rows]


def score_chunks(query: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    query_terms = Counter(tokenize(query))
    if not query_terms:
        return []
    docs = [tokenize(row["text"] + " " + row["title"] + " " + row["service"] + " " + row["asset_type"]) for row in rows]
    doc_freq: Counter[str] = Counter()
    for tokens in docs:
        doc_freq.update(set(tokens))

    scored: list[dict[str, Any]] = []
    total_docs = max(len(rows), 1)
    for row, tokens in zip(rows, docs):
        term_counts = Counter(tokens)
        score = 0.0
        for term, q_count in query_terms.items():
            if term not in term_counts:
                continue
            idf = math.log((1 + total_docs) / (1 + doc_freq[term])) + 1
            score += q_count * term_counts[term] * idf
        score = score / math.sqrt(max(len(tokens), 1))
        if score > 0:
            scored.append({**row, "score": round(score, 4), "metadata": json.loads(row["metadata"])})
    return sorted(scored, key=lambda item: item["score"], reverse=True)


def summarize_context(question: str, matches: list[dict[str, Any]]) -> str:
    if not matches:
        return "I could not find enough approved context for that question. Add or improve the related knowledge asset, then re-index."
    sentences: list[str] = []
    terms = set(tokenize(question))
    for match in matches:
        for sentence in re.split(r"(?<=[.!?])\s+", match["text"]):
            sentence_terms = set(tokenize(sentence))
            if terms & sentence_terms:
                sentences.append(sentence.strip())
            if len(sentences) >= 5:
                break
        if len(sentences) >= 5:
            break
    if not sentences:
        sentences = [matches[0]["text"][:500]]
    answer = " ".join(sentences)
    return answer[:1200]


def generate_answer(question: str, matches: list[dict[str, Any]]) -> str:
    fallback = summarize_context(question, matches)
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key or OpenAI is None or not matches:
        return fallback
    try:
        client = OpenAI(api_key=api_key)
        context = "\n\n".join(
            f"Source: {item['title']} ({item['asset_type']}, readiness {item['readiness_score']})\n{item['text']}"
            for item in matches[:4]
        )
        response = client.chat.completions.create(
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            temperature=0.1,
            messages=[
                {"role": "system", "content": "Answer from the supplied network operations context. Be concise and cite source titles."},
                {"role": "user", "content": json.dumps({"question": question, "context": context})},
            ],
        )
        return response.choices[0].message.content.strip()
    except Exception:
        return fallback


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/config")
def config() -> dict[str, Any]:
    return {
        "openai_enabled": bool(os.getenv("OPENAI_API_KEY")) and OpenAI is not None,
        "model": os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        "input_dir": str(INPUT_DIR),
    }


@app.post("/api/ingest")
def ingest_from_inputs() -> dict[str, Any]:
    assets = read_input_files()
    if not assets:
        raise HTTPException(status_code=404, detail="No JSON knowledge inputs found.")
    return ingest_assets(assets)


@app.get("/api/assets")
def list_assets() -> dict[str, Any]:
    return {"assets": asset_rows()}


@app.get("/api/governance")
def governance() -> dict[str, Any]:
    assets = asset_rows()
    if not assets:
        return {"summary": {"asset_count": 0, "average_readiness": 0, "approved_count": 0, "issue_count": 0}, "by_type": [], "control_issues": []}
    by_type: dict[str, list[int]] = defaultdict(list)
    control_counts: Counter[str] = Counter()
    for asset in assets:
        by_type[asset["asset_type"]].append(asset["readiness_score"])
        for item in asset["issues"]:
            control_counts[item["control"]] += 1
    return {
        "summary": {
            "asset_count": len(assets),
            "average_readiness": round(sum(item["readiness_score"] for item in assets) / len(assets)),
            "approved_count": sum(1 for item in assets if item["status"] == "approved"),
            "issue_count": sum(len(item["issues"]) for item in assets),
        },
        "by_type": [
            {"asset_type": key, "count": len(values), "average_readiness": round(sum(values) / len(values))}
            for key, values in sorted(by_type.items())
        ],
        "control_issues": [{"control": key, "count": value} for key, value in control_counts.most_common()],
    }


@app.post("/api/search")
def search(payload: SearchRequest) -> dict[str, Any]:
    rows = chunk_rows()
    if payload.asset_type:
        rows = [row for row in rows if row["asset_type"] == payload.asset_type]
    if payload.service:
        rows = [row for row in rows if row["service"] == payload.service]
    if payload.owner:
        rows = [row for row in rows if row["owner"] == payload.owner]
    rows = [row for row in rows if row["readiness_score"] >= payload.min_readiness]
    return {"matches": score_chunks(payload.query, rows)[: payload.top_k]}


@app.post("/api/ask")
def ask(payload: AskRequest) -> dict[str, Any]:
    matches = score_chunks(payload.question, chunk_rows())[: payload.top_k]
    return {"answer": generate_answer(payload.question, matches), "sources": matches}


@app.post("/api/upload")
async def upload_asset(file: UploadFile = File(...)) -> dict[str, Any]:
    if not file.filename.lower().endswith((".json", ".md", ".txt")):
        raise HTTPException(status_code=400, detail="Upload a JSON, Markdown, or text knowledge file.")
    content = (await file.read()).decode("utf-8")
    if file.filename.lower().endswith(".json"):
        records = json.loads(content)
        assets = [parse_asset(record, file.filename) for record in (records if isinstance(records, list) else records.get("assets", [records]))]
    else:
        assets = [
            parse_asset(
                {
                    "title": file.filename,
                    "asset_type": "runbook",
                    "metadata": {"service": "Network Services", "status": "review", "source_system": "upload"},
                    "content": content,
                },
                file.filename,
            )
        ]
    existing = asset_rows()
    all_assets = [
        {
            "id": item["id"],
            "title": item["title"],
            "asset_type": item["asset_type"],
            "service": item["service"],
            "owner": item["owner"],
            "source": item["source"],
            "freshness_date": item["freshness_date"],
            "status": item["status"],
            "metadata": item["metadata"],
            "content": item["content"],
        }
        for item in existing
    ] + assets
    return ingest_assets(all_assets)


if FRONTEND_BUILD.exists():
    app.mount("/", StaticFiles(directory=FRONTEND_BUILD, html=True), name="frontend")
