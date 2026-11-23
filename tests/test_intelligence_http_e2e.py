"""Ejercicio completo con API HTTP local simulada y datos de la demo."""
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import threading
from urllib.request import Request, urlopen
from unittest.mock import patch

from fastapi.testclient import TestClient
import pytest

from app import db
from app.main import create_app
from app.intelligence import AnalysisEnvelope, context_from_current_snapshot
from app.intelligence.pipeline import LLMPipeline
from app.intelligence.providers import APIProvider


def run_simulated_api_example(db_path, provider_name="xai"):
    """Usa la API de cartera real y un servidor HTTP local que simula xAI o Groq."""
    requests_seen = []

    class SimulatedGroq(BaseHTTPRequestHandler):
        def do_POST(self):
            request_body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            requests_seen.append(request_body)
            messages = request_body["input"] if provider_name == "xai" else request_body["messages"]
            user_data = json.loads(messages[1]["content"])
            document = user_data["documents"][0]
            evidence = [{"document_id": document["document_id"], "source_field": "summary",
                         "excerpt": document["summary"]}]
            draft = {
                "decision": "REVISAR",
                "findings": [{"statement": "El documento describe un escenario ficticio para revisar.",
                              "category": "source_claim", "issuer_candidates": [], "evidence": evidence}],
                "arguments_for": [], "arguments_against": [],
                "proposed_positions": [{"instrument_id": "DEMO:CHIP", "action": "REVISAR",
                    "rationale": "Revisar la exposición al escenario ficticio antes de adoptar una decisión.",
                    "evidence": evidence, "risks": ["No existen fuentes reales verificadas en esta demo."]}],
                "missing_data": ["No hay documentos de mercado reales ni tesis validada."],
                "warnings": ["Salida generada por un servidor simulado; no procede de un LLM."],
            }
            if provider_name == "xai":
                payload = {"status": "completed", "output": [{"type": "message", "content": [
                    {"type": "output_text", "text": json.dumps(draft)}]}]}
            else:
                payload = {"choices": [{"finish_reason": "stop", "message": {"content": json.dumps(draft)}}]}
            body = json.dumps(payload).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), SimulatedGroq)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    def redirect_to_local_test_server(request, timeout):
        expected_url = ("https://api.x.ai/v1/responses" if provider_name == "xai"
                        else "https://api.groq.com/openai/v1/chat/completions")
        assert request.full_url == expected_url
        local_request = Request(f"http://127.0.0.1:{server.server_port}/chat/completions",
                                data=request.data, method="POST", headers={"Content-Type": "application/json"})
        return urlopen(local_request, timeout=timeout)

    try:
        with TestClient(create_app(str(db_path))) as client:
            run = client.post("/api/analyses").json()
            assert db.process_one(str(db_path)) == run["id"]
            state = client.get(f"/api/analyses/{run['id']}").json()
            assert state["status"] == "completed"
            report = client.get(f"/api/reports/{state['report_id']}").json()
            snapshot = report["input_snapshot"]
            context = context_from_current_snapshot(
                run_id=run["id"], portfolio_version=report["portfolio_version"],
                profile_version=report["profile_version"], as_of=datetime(2026, 11, 21, tzinfo=timezone.utc),
                data_classification=report["result"]["data_classification"],
                portfolio=snapshot["portfolio"], profile=snapshot["profile"],
                documents=snapshot["documents"], exposures=report["result"]["exposures"],
            )
            # Redirection occurs inside the test; no credentials or remote API are used.
            with patch("app.intelligence.providers.urlopen", side_effect=redirect_to_local_test_server):
                result = LLMPipeline(APIProvider(provider_name, "simulated-http-test", "fake-test-key")).analyze(context)
            # A persisted sample must never claim that the real provider was called.
            result.implementation = f"simulated_http:{provider_name}"
            envelope = AnalysisEnvelope(context=context, result=result)
            assert client.get(f"/api/reports/{state['report_id']}").json() == report
            return envelope, requests_seen
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@pytest.mark.parametrize("provider_name", ["xai", "groq"])
def test_api_current_snapshot_to_intelligence_over_real_local_http(tmp_path, provider_name):
    envelope, requests = run_simulated_api_example(tmp_path / "financial-demo.sqlite3", provider_name)
    restored = AnalysisEnvelope.model_validate_json(envelope.model_dump_json())
    assert len(requests) == 1
    assert requests[0]["model"] == "simulated-http-test"
    assert restored.contract_version == "1.1"
    assert restored.context.exposures[0].known_total == 3600
    assert restored.result.proposed_positions[0].instrument_id == "DEMO:CHIP"
    assert restored.result.proposed_positions[0].action == "REVISAR"
    assert restored.result.implementation == f"simulated_http:{provider_name}"
    assert restored.result.findings[0].evidence[0].document_id == "DOC-DEMO-001"
    assert "servidor simulado" in restored.result.warnings[0]
