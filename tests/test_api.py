import json
from fastapi.testclient import TestClient
from app.main import create_app
from app import db


def test_no_automatic_analysis_and_immutable_report(tmp_path):
    path = str(tmp_path / "state.sqlite3")
    with TestClient(create_app(path)) as client:
        assert client.get("/api/health").json()["model_calls"] == 0
        assert "SIMULACIÓN" in client.get("/").text
        assert client.get("/api/reports").json() == []
        first_portfolio = client.get("/api/portfolio").json()
        first_profile = client.get("/api/profile").json()
        response = client.post("/api/analyses")
        assert response.status_code == 202
        run_id = response.json()["id"]
        assert client.get(f"/api/analyses/{run_id}").json()["status"] == "queued"
        assert client.get("/api/reports").json() == []
        assert db.process_one(path) == run_id
        completed = client.get(f"/api/analyses/{run_id}").json()
        assert completed["status"] == "completed"
        report_id = completed["report_id"]
        old_report = client.get(f"/api/reports/{report_id}").json()
        assert old_report["portfolio_version"] == first_portfolio["version"]
        assert old_report["profile_version"] == first_profile["version"]
        new_portfolio = first_portfolio["data"]
        new_portfolio["positions"][0]["quantity"] = "100"
        assert client.put("/api/portfolio", json=new_portfolio).status_code == 200
        assert client.get("/api/portfolio").json()["version"] == first_portfolio["version"] + 1
        assert client.get(f"/api/reports/{report_id}").json() == old_report
        assert client.get("/api/reports").json()[0]["id"] == report_id


def test_failed_validation_does_not_create_portfolio_version(tmp_path):
    path = str(tmp_path / "state.sqlite3")
    with TestClient(create_app(path)) as client:
        original = client.get("/api/portfolio").json()
        wrong = json.loads(json.dumps(original["data"]))
        wrong["positions"][1]["holdings"] = [{"issuer_id": "DEMO:CHIP", "weight": "1.5"}]
        assert client.put("/api/portfolio", json=wrong).status_code == 422
        assert client.get("/api/portfolio").json()["version"] == original["version"]
