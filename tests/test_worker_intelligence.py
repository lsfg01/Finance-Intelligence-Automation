"""Integración de cola, snapshots e inteligencia sin acceso a red."""
import json

from fastapi.testclient import TestClient

from app import db
from app.intelligence.contracts import AnalysisEnvelope
from app.intelligence.pipeline import LLMPipeline
from app.intelligence.providers import ProviderError
from app.main import create_app


class RecordingProvider:
    name = "test"
    model = "fixture"

    def __init__(self, fail=False):
        self.requests = []
        self.fail = fail

    def generate(self, system, data, schema):
        self.requests.append(json.loads(data))
        if self.fail:
            raise ProviderError("Proveedor de prueba no disponible")
        document = self.requests[-1]["documents"][0]
        return json.dumps({
            "decision": "REVISAR", "findings": [{"statement": "Documento de prueba",
                "category": "source_claim", "issuer_candidates": [],
                "evidence": [{"document_id": document["document_id"], "source_field": "summary",
                              "excerpt": document["summary"]}]}],
            "arguments_for": [], "arguments_against": [], "proposed_positions": [],
            "missing_data": [], "warnings": ["Datos ficticios"],
        })


def test_worker_persists_llm_result_with_original_snapshot(tmp_path):
    path = str(tmp_path / "demo.sqlite3")
    provider = RecordingProvider()
    with TestClient(create_app(path)) as client:
        initial = client.get("/api/portfolio").json()
        run = client.post("/api/analyses").json()
        assert provider.requests == []
        changed = initial["data"]
        changed["positions"][0]["quantity"] = "99"
        client.put("/api/portfolio", json=changed).raise_for_status()
        assert db.process_one(path, pipeline=LLMPipeline(provider)) == run["id"]
        state = client.get(f"/api/analyses/{run['id']}").json()
        assert state["status"] == "completed" and len(provider.requests) == 1
        report = client.get(f"/api/reports/{state['report_id']}").json()
        envelope = AnalysisEnvelope.model_validate(report["result"]["intelligence"])
        assert envelope.result.implementation == "llm:test" and envelope.result.model == "fixture"
        assert envelope.context.run_id == run["id"] and envelope.context.portfolio_version == initial["version"]
        assert envelope.context.portfolio.positions[0].quantity == 30
        assert envelope.context.exposures[0].known_total == 3600
        assert report["result"]["exposures"][0]["known_total_eur"] == "3600.00"
        assert client.get(f"/api/reports/{state['report_id']}").json() == report


def test_worker_marks_provider_failure_without_partial_report(tmp_path):
    path = str(tmp_path / "demo.sqlite3")
    provider = RecordingProvider(fail=True)
    with TestClient(create_app(path)) as client:
        run = client.post("/api/analyses").json()
        db.process_one(path, pipeline=LLMPipeline(provider))
        state = client.get(f"/api/analyses/{run['id']}").json()
        assert state["status"] == "failed" and state["report_id"] is None
        assert state["error"] == "Proveedor de prueba no disponible"
        assert client.get("/api/reports").json() == []


def test_existing_report_without_intelligence_remains_readable(tmp_path):
    path = str(tmp_path / "demo.sqlite3")
    with TestClient(create_app(path)) as client:
        run = client.post("/api/analyses").json()
        db.process_one(path)
        report_id = client.get(f"/api/analyses/{run['id']}").json()["report_id"]
        # Simula el JSON persistido por la versión anterior a la integración.
        with db.connect(path) as conn:
            row = conn.execute("SELECT payload_json FROM reports WHERE id=?", (report_id,)).fetchone()
            legacy = json.loads(row["payload_json"])
            legacy.pop("intelligence")
            conn.execute("UPDATE reports SET payload_json=? WHERE id=?", (json.dumps(legacy), report_id))
        loaded = client.get(f"/api/reports/{report_id}").json()
        assert loaded["result"] == legacy
        assert "intelligence" not in loaded["result"]
