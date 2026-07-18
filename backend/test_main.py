from fastapi.testclient import TestClient

from main import app, ingest_assets, read_input_files


client = TestClient(app)


def test_ingest_builds_ai_ready_assets():
    result = ingest_assets(read_input_files())

    assert result["assets_ingested"] >= 7
    assert result["chunks_indexed"] >= result["assets_ingested"]


def test_governance_summary_reports_readiness():
    ingest_assets(read_input_files())
    response = client.get("/api/governance")

    assert response.status_code == 200
    summary = response.json()["summary"]
    assert summary["asset_count"] >= 7
    assert 0 < summary["average_readiness"] <= 100
    assert summary["issue_count"] >= 1


def test_ask_returns_sources_for_failover_question(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    ingest_assets(read_input_files())
    response = client.post("/api/ask", json={"question": "How do we handle edge router failover?"})

    assert response.status_code == 200
    data = response.json()
    assert data["sources"]
    assert "failover" in data["answer"].lower() or "router" in data["answer"].lower()
