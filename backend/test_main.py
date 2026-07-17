from fastapi.testclient import TestClient

from main import app


client = TestClient(app)


def test_demo_incident_creates_findings(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    response = client.post("/api/analyze-demo/orders")

    assert response.status_code == 200
    incident = response.json()["incident"]
    assert incident["dataset_kind"] == "orders"
    assert incident["issues"]
    assert incident["health_score"] < 100


def test_postmortem_endpoint_returns_markdown(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    created = client.post("/api/analyze-demo/payments").json()["incident"]
    response = client.get(f"/api/incidents/{created['id']}/postmortem")

    assert response.status_code == 200
    assert "# Data Quality Incident Postmortem" in response.json()["markdown"]
