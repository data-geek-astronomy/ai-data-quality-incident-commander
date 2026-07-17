import io
import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

import numpy as np
import pandas as pd
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - optional local convenience.
    load_dotenv = None

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover - app works without an LLM key.
    OpenAI = None

if load_dotenv is not None:
    load_dotenv(Path(__file__).resolve().parent / ".env")

app = FastAPI(title="AI Data Quality Incident Commander")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
DB_PATH = DATA_DIR / "incidents.db"
SAMPLE_DIR = ROOT.parent / "sample_uploads"
DATA_DIR.mkdir(exist_ok=True)

DatasetKind = Literal["orders", "payments", "events"]


class StatusUpdate(BaseModel):
    status: Literal["open", "investigating", "fix_ready", "resolved"]


class IncidentResponse(BaseModel):
    incident: dict[str, Any]


DATASET_CONFIG: dict[str, dict[str, Any]] = {
    "orders": {
        "label": "Commerce Orders",
        "required_columns": ["order_id", "customer_id", "order_total", "status", "created_at", "region"],
        "primary_key": "order_id",
        "timestamp": "created_at",
        "business_kpi": "order_total",
        "expected_categories": {"status": ["paid", "pending", "refunded"], "region": ["west", "east", "south", "central"]},
    },
    "payments": {
        "label": "Payments Ledger",
        "required_columns": ["payment_id", "account_id", "amount", "payment_status", "processed_at", "processor"],
        "primary_key": "payment_id",
        "timestamp": "processed_at",
        "business_kpi": "amount",
        "expected_categories": {"payment_status": ["settled", "failed", "review"], "processor": ["stripe", "adyen", "paypal"]},
    },
    "events": {
        "label": "Product Events",
        "required_columns": ["event_id", "user_id", "event_name", "session_duration", "event_time", "platform"],
        "primary_key": "event_id",
        "timestamp": "event_time",
        "business_kpi": "session_duration",
        "expected_categories": {"event_name": ["signup", "search", "checkout", "cancel"], "platform": ["ios", "android", "web"]},
    },
}

SAMPLE_UPLOADS: dict[str, dict[str, str]] = {
    "orders": {
        "filename": "orders_broken.csv",
        "name": "Commerce Orders",
        "scenario": "Revenue report changed overnight",
        "overview": "A small order table with duplicate orders, missing totals, invalid dates, and unexpected customer states.",
    },
    "payments": {
        "filename": "payments_broken.csv",
        "name": "Payments Ledger",
        "scenario": "Payments ledger looks wrong",
        "overview": "A finance ledger with missing account information, negative charges, repeated payments, and a new processor value.",
    },
    "events": {
        "filename": "product_events_broken.csv",
        "name": "Product Events",
        "scenario": "Product analytics dropped",
        "overview": "A product events table with broken timestamps, repeated events, unknown SDK values, and collapsed session duration.",
    },
}


def db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS incidents (
            id TEXT PRIMARY KEY,
            dataset_name TEXT NOT NULL,
            dataset_kind TEXT NOT NULL,
            severity TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            payload TEXT NOT NULL
        )
        """
    )
    return conn


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def make_sample(kind: DatasetKind, broken: bool = False) -> pd.DataFrame:
    rng = np.random.default_rng(42 if not broken else 99)
    rows = 240
    dates = pd.date_range("2026-07-01", periods=rows, freq="h")

    if kind == "orders":
        df = pd.DataFrame(
            {
                "order_id": [f"ord_{i:05d}" for i in range(rows)],
                "customer_id": [f"cust_{rng.integers(1000, 1160)}" for _ in range(rows)],
                "order_total": rng.normal(86, 18, rows).round(2).clip(4),
                "status": rng.choice(["paid", "pending", "refunded"], rows, p=[0.82, 0.12, 0.06]),
                "created_at": dates.astype(str),
                "region": rng.choice(["west", "east", "south", "central"], rows, p=[0.34, 0.28, 0.21, 0.17]),
            }
        )
        if broken:
            df.loc[20:42, "order_total"] = np.nan
            df.loc[110:118, "order_total"] = 700
            df.loc[160:175, "status"] = "chargeback_unknown"
            df = pd.concat([df, df.iloc[5:14]], ignore_index=True)
    elif kind == "payments":
        df = pd.DataFrame(
            {
                "payment_id": [f"pay_{i:05d}" for i in range(rows)],
                "account_id": [f"acct_{rng.integers(500, 660)}" for _ in range(rows)],
                "amount": rng.normal(125, 28, rows).round(2).clip(2),
                "payment_status": rng.choice(["settled", "failed", "review"], rows, p=[0.88, 0.08, 0.04]),
                "processed_at": dates.astype(str),
                "processor": rng.choice(["stripe", "adyen", "paypal"], rows, p=[0.58, 0.25, 0.17]),
            }
        )
        if broken:
            df.loc[50:72, "processor"] = "unknown_gateway"
            df.loc[80:94, "amount"] = -abs(df.loc[80:94, "amount"])
            df = df.drop(columns=["account_id"])
    else:
        df = pd.DataFrame(
            {
                "event_id": [f"evt_{i:05d}" for i in range(rows)],
                "user_id": [f"user_{rng.integers(2000, 2190)}" for _ in range(rows)],
                "event_name": rng.choice(["signup", "search", "checkout", "cancel"], rows, p=[0.12, 0.55, 0.27, 0.06]),
                "session_duration": rng.normal(180, 46, rows).round(1).clip(1),
                "event_time": dates.astype(str),
                "platform": rng.choice(["ios", "android", "web"], rows, p=[0.42, 0.35, 0.23]),
            }
        )
        if broken:
            df.loc[0:60, "session_duration"] = 0
            df.loc[130:165, "platform"] = "unknown_sdk"
            df.loc[190:220, "event_time"] = "not-a-date"

    return df


def percent(value: float) -> float:
    return round(float(value) * 100, 2)


def issue(title: str, severity: str, detail: str, metric: float, column: str | None = None) -> dict[str, Any]:
    return {
        "title": title,
        "severity": severity,
        "detail": detail,
        "metric": round(float(metric), 3),
        "column": column,
    }


def severity_rank(severity: str) -> int:
    return {"low": 1, "medium": 2, "high": 3, "critical": 4}.get(severity, 1)


def analyze_frame(df: pd.DataFrame, dataset_kind: DatasetKind, dataset_name: str) -> dict[str, Any]:
    if df.empty:
        raise HTTPException(status_code=400, detail="The dataset is empty.")

    cfg = DATASET_CONFIG[dataset_kind]
    issues: list[dict[str, Any]] = []
    required = cfg["required_columns"]
    missing = [col for col in required if col not in df.columns]
    if missing:
        issues.append(issue("Schema contract broken", "critical", f"Missing required columns: {', '.join(missing)}.", len(missing)))

    duplicate_ratio = df.duplicated().mean()
    if duplicate_ratio > 0.01:
        sev = "critical" if duplicate_ratio > 0.08 else "high"
        issues.append(issue("Duplicate records detected", sev, f"{percent(duplicate_ratio)}% of rows are exact duplicates.", duplicate_ratio))

    key = cfg["primary_key"]
    if key in df.columns:
        key_dupes = df[key].duplicated().mean()
        if key_dupes > 0:
            issues.append(issue("Primary key collision", "critical", f"{percent(key_dupes)}% of {key} values repeat.", key_dupes, key))

    for col in df.columns:
        null_ratio = df[col].isna().mean()
        if null_ratio > 0.05:
            sev = "critical" if null_ratio > 0.20 else "high"
            issues.append(issue("Null spike", sev, f"{col} has {percent(null_ratio)}% null values.", null_ratio, col))

    numeric_cols = list(df.select_dtypes(include=[np.number]).columns)
    for col in numeric_cols:
        series = df[col].dropna()
        if len(series) < 20:
            continue
        q1, q3 = series.quantile([0.25, 0.75])
        iqr = q3 - q1
        if iqr == 0:
            zero_ratio = (series == 0).mean()
            if zero_ratio > 0.20:
                issues.append(issue("Metric collapse", "high", f"{col} is stuck at zero for {percent(zero_ratio)}% of numeric rows.", zero_ratio, col))
            continue
        outlier_ratio = ((series < q1 - 3 * iqr) | (series > q3 + 3 * iqr)).mean()
        if outlier_ratio > 0.03:
            sev = "high" if outlier_ratio < 0.10 else "critical"
            issues.append(issue("Numeric outlier burst", sev, f"{col} has {percent(outlier_ratio)}% extreme values.", outlier_ratio, col))
        if (series < 0).mean() > 0.02 and col in ["amount", "order_total", "session_duration"]:
            issues.append(issue("Invalid negative business metric", "critical", f"{col} contains negative values.", (series < 0).mean(), col))

    timestamp_col = cfg["timestamp"]
    if timestamp_col in df.columns:
        parsed = pd.to_datetime(df[timestamp_col], errors="coerce", utc=True)
        bad_dates = parsed.isna().mean()
        if bad_dates > 0.03:
            issues.append(issue("Timestamp parsing failure", "high", f"{timestamp_col} has {percent(bad_dates)}% invalid timestamps.", bad_dates, timestamp_col))

    for col, expected_values in cfg["expected_categories"].items():
        if col not in df.columns:
            continue
        unexpected = ~df[col].dropna().astype(str).isin(expected_values)
        ratio = unexpected.mean() if len(unexpected) else 0
        if ratio > 0.03:
            sev = "critical" if ratio > 0.15 else "high"
            issues.append(issue("Unexpected category drift", sev, f"{col} contains values outside the expected contract.", ratio, col))

    baseline = make_sample(dataset_kind, broken=False)
    kpi = cfg["business_kpi"]
    psi = 0.0
    if kpi in df.columns and kpi in baseline.columns:
        psi = population_stability_index(baseline[kpi], pd.to_numeric(df[kpi], errors="coerce"))
        if psi > 0.25:
            issues.append(issue("Distribution shift", "high", f"{kpi} distribution shifted materially from the healthy baseline.", psi, kpi))

    max_rank = max([severity_rank(item["severity"]) for item in issues], default=1)
    severity = {1: "low", 2: "medium", 3: "high", 4: "critical"}[max_rank]
    if len(issues) >= 5 and severity != "critical":
        severity = "high"

    root_cause = generate_root_cause(dataset_name, dataset_kind, issues)
    fixes = generate_fixes(dataset_kind, issues)
    incident_id = str(uuid.uuid4())[:8]
    created_at = now_iso()
    incident = {
        "id": incident_id,
        "dataset_name": dataset_name,
        "dataset_kind": dataset_kind,
        "dataset_label": cfg["label"],
        "created_at": created_at,
        "status": "open" if issues else "resolved",
        "severity": severity if issues else "low",
        "health_score": max(0, 100 - sum(severity_rank(item["severity"]) * 9 for item in issues)),
        "row_count": int(len(df)),
        "column_count": int(len(df.columns)),
        "issues": issues,
        "root_cause": root_cause,
        "recommended_fixes": fixes,
        "evidence": {
            "columns": list(df.columns),
            "numeric_columns": numeric_cols,
            "distribution_shift_psi": round(float(psi), 3),
            "sample_rows": df.head(5).replace({np.nan: None}).to_dict(orient="records"),
        },
        "timeline": [
            {"time": created_at, "event": "Dataset analyzed"},
            {"time": created_at, "event": f"{len(issues)} quality issues detected"},
            {"time": created_at, "event": "AI incident brief generated"},
        ],
    }
    save_incident(incident)
    return incident


def population_stability_index(expected: pd.Series, actual: pd.Series, bins: int = 10) -> float:
    expected = pd.to_numeric(expected, errors="coerce").dropna()
    actual = pd.to_numeric(actual, errors="coerce").dropna()
    if len(expected) < 10 or len(actual) < 10:
        return 0.0
    cuts = np.percentile(expected, np.linspace(0, 100, bins + 1))
    cuts = np.unique(cuts)
    if len(cuts) < 3:
        return 0.0
    expected_counts, _ = np.histogram(expected, bins=cuts)
    actual_counts, _ = np.histogram(actual, bins=cuts)
    expected_pct = np.maximum(expected_counts / max(expected_counts.sum(), 1), 0.001)
    actual_pct = np.maximum(actual_counts / max(actual_counts.sum(), 1), 0.001)
    return float(np.sum((actual_pct - expected_pct) * np.log(actual_pct / expected_pct)))


def generate_root_cause(dataset_name: str, dataset_kind: str, issues: list[dict[str, Any]]) -> str:
    if not issues:
        return "No active incident detected. The dataset matches the configured contract and baseline expectations."

    fallback = (
        f"{dataset_name} needs attention before it is used for reporting or automation. "
        f"The clearest signal is: {issues[0]['detail']} "
        "This usually means a recent data source, app release, or scheduled import changed unexpectedly. "
        "Pause downstream use, review the newest records first, and republish once the source is corrected."
    )
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key or OpenAI is None:
        return fallback

    try:
        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            temperature=0.2,
            messages=[
                {"role": "system", "content": "You are a concise senior data reliability incident commander."},
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "dataset": dataset_name,
                            "dataset_kind": dataset_kind,
                            "issues": issues[:8],
                    "task": "Explain the likely root cause and immediate response in 4 plain-English sentences for a business user. Avoid jargon.",
                        }
                    ),
                },
            ],
        )
        return response.choices[0].message.content.strip()
    except Exception:
        return fallback


def generate_fixes(dataset_kind: str, issues: list[dict[str, Any]]) -> list[dict[str, str]]:
    fixes = []
    for item in issues[:6]:
        col = item.get("column") or "affected_column"
        title = item["title"]
        if "Schema" in title:
            fixes.append(
                {
                    "title": "Restore schema contract",
                    "sql": "-- Add the missing source field or update the model contract before publishing the table.",
                    "python": "assert set(required_columns).issubset(df.columns)",
                }
            )
        elif "Null" in title:
            fixes.append(
                {
                    "title": f"Quarantine null-heavy rows in {col}",
                    "sql": f"CREATE TABLE quarantine_{dataset_kind} AS SELECT * FROM raw_{dataset_kind} WHERE {col} IS NULL;",
                    "python": f"clean_df = df[df['{col}'].notna()].copy()",
                }
            )
        elif "Duplicate" in title or "Primary" in title:
            fixes.append(
                {
                    "title": "Deduplicate by stable key",
                    "sql": "SELECT * EXCEPT(row_num) FROM (SELECT *, ROW_NUMBER() OVER(PARTITION BY id ORDER BY updated_at DESC) row_num FROM source) WHERE row_num = 1;",
                    "python": "df = df.drop_duplicates(keep='last')",
                }
            )
        elif "category" in title.lower():
            fixes.append(
                {
                    "title": f"Map or block unexpected {col} values",
                    "sql": f"SELECT {col}, COUNT(*) FROM raw_{dataset_kind} GROUP BY {col} ORDER BY COUNT(*) DESC;",
                    "python": f"df['{col}'] = df['{col}'].where(df['{col}'].isin(allowed_values), 'unknown')",
                }
            )
        else:
            fixes.append(
                {
                    "title": f"Validate {col} before publish",
                    "sql": f"SELECT APPROX_QUANTILES({col}, 10) FROM raw_{dataset_kind};",
                    "python": f"df['{col}'] = pd.to_numeric(df['{col}'], errors='coerce')",
                }
            )
    return fixes


def save_incident(incident: dict[str, Any]) -> None:
    with db() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO incidents VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                incident["id"],
                incident["dataset_name"],
                incident["dataset_kind"],
                incident["severity"],
                incident["status"],
                incident["created_at"],
                json.dumps(incident),
            ),
        )


def read_incident(incident_id: str) -> dict[str, Any]:
    with db() as conn:
        row = conn.execute("SELECT payload FROM incidents WHERE id = ?", (incident_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Incident not found.")
    return json.loads(row["payload"])


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/config")
def config() -> dict[str, Any]:
    return {
        "openai_enabled": bool(os.getenv("OPENAI_API_KEY")) and OpenAI is not None,
        "model": os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
    }


@app.get("/api/demo-datasets")
def demo_datasets() -> dict[str, Any]:
    return {
        "datasets": [
            {"id": "orders", "name": "Commerce Orders", "description": "Null spike, duplicates, outliers, category drift."},
            {"id": "payments", "name": "Payments Ledger", "description": "Missing schema field, negative amounts, gateway drift."},
            {"id": "events", "name": "Product Events", "description": "Metric collapse, SDK drift, invalid timestamps."},
        ]
    }


@app.get("/api/sample-uploads")
def sample_uploads() -> dict[str, Any]:
    samples = []
    for dataset_kind, sample in SAMPLE_UPLOADS.items():
        path = SAMPLE_DIR / sample["filename"]
        row_count = 0
        columns: list[str] = []
        if path.exists():
            preview = pd.read_csv(path, nrows=5)
            row_count = sum(1 for _ in path.open()) - 1
            columns = list(preview.columns)
        samples.append(
            {
                "id": dataset_kind,
                "data_type": dataset_kind,
                "name": sample["name"],
                "filename": sample["filename"],
                "scenario": sample["scenario"],
                "overview": sample["overview"],
                "row_count": row_count,
                "columns": columns,
            }
        )
    return {"samples": samples}


@app.post("/api/analyze-demo/{dataset_kind}", response_model=IncidentResponse)
def analyze_demo(dataset_kind: DatasetKind) -> dict[str, Any]:
    incident = analyze_frame(make_sample(dataset_kind, broken=True), dataset_kind, f"demo_{dataset_kind}.csv")
    return {"incident": incident}


@app.post("/api/analyze-sample/{dataset_kind}", response_model=IncidentResponse)
def analyze_sample_upload(dataset_kind: DatasetKind) -> dict[str, Any]:
    sample = SAMPLE_UPLOADS[dataset_kind]
    path = SAMPLE_DIR / sample["filename"]
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Sample file not found: {sample['filename']}")
    df = pd.read_csv(path)
    incident = analyze_frame(df, dataset_kind, sample["filename"])
    return {"incident": incident}


@app.post("/api/analyze", response_model=IncidentResponse)
async def analyze_upload(dataset_kind: DatasetKind = "orders", file: UploadFile = File(...)) -> dict[str, Any]:
    if not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Upload a CSV file.")
    content = await file.read()
    try:
        df = pd.read_csv(io.BytesIO(content))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Could not parse CSV: {exc}") from exc
    incident = analyze_frame(df, dataset_kind, file.filename)
    return {"incident": incident}


@app.get("/api/incidents")
def list_incidents() -> dict[str, Any]:
    with db() as conn:
        rows = conn.execute("SELECT payload FROM incidents ORDER BY created_at DESC LIMIT 50").fetchall()
    return {"incidents": [json.loads(row["payload"]) for row in rows]}


@app.get("/api/incidents/{incident_id}", response_model=IncidentResponse)
def get_incident(incident_id: str) -> dict[str, Any]:
    return {"incident": read_incident(incident_id)}


@app.patch("/api/incidents/{incident_id}/status", response_model=IncidentResponse)
def update_status(incident_id: str, payload: StatusUpdate) -> dict[str, Any]:
    incident = read_incident(incident_id)
    incident["status"] = payload.status
    incident["timeline"].append({"time": now_iso(), "event": f"Status changed to {payload.status}"})
    save_incident(incident)
    return {"incident": incident}


@app.get("/api/incidents/{incident_id}/postmortem")
def postmortem(incident_id: str) -> dict[str, str]:
    incident = read_incident(incident_id)
    issue_lines = "\n".join(f"- {item['title']}: {item['detail']}" for item in incident["issues"])
    fix_lines = "\n".join(f"- {item['title']}" for item in incident["recommended_fixes"])
    markdown = f"""# Data Quality Incident Postmortem

## Summary
Dataset `{incident['dataset_name']}` triggered a `{incident['severity']}` incident with health score `{incident['health_score']}`.

## Customer / Business Impact
Downstream dashboards, ML features, and operational automations using `{incident['dataset_label']}` may receive incomplete or misleading data until the affected partition is remediated.

## Detected Issues
{issue_lines or "- No active issues detected."}

## Likely Root Cause
{incident['root_cause']}

## Remediation Plan
{fix_lines or "- Continue monitoring."}

## Prevention
- Add schema contract checks to CI and the ingestion job.
- Block publish when critical quality checks fail.
- Alert owners when drift exceeds the configured threshold.
- Keep replayable raw partitions for fast rollback.
"""
    return {"markdown": markdown}
