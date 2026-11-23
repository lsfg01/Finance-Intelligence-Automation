import json
from io import BytesIO
from urllib.error import HTTPError

import pytest

from app.intelligence.pipeline import LLMPipeline, MockPipeline, ModelDraft, pipeline_from_env
from app.intelligence.providers import APIProvider, OllamaProvider, ProviderError, provider_from_env
from test_intelligence_contract import context


def draft():
    return {"decision": "REVISAR", "findings": [{"statement": "Es un fixture", "category": "source_claim",
            "issuer_candidates": [], "evidence": [{"document_id": "DOC-DEMO-001", "source_field": "summary",
                                                       "excerpt": "Documento ficticio"}]}],
            "arguments_for": [], "arguments_against": [], "proposed_positions": [], "missing_data": [], "warnings": []}


class FakeProvider:
    name = "fake"
    model = "test-model"

    def __init__(self, response=None):
        self.response = json.dumps(draft()) if response is None else response
        self.calls = []

    def generate(self, system, data, schema):
        self.calls.append((system, json.loads(data), schema))
        return self.response


def test_mock_produces_traceable_result_without_network():
    output = MockPipeline().analyze(context())
    assert output.implementation == "mock"
    assert output.findings[0].evidence[0].document_id == "DOC-DEMO-001"
    assert output.findings[0].issuer_candidates == ["DEMO:CHIP"]


def test_model_pipeline_returns_contract_and_minimizes_input():
    provider = FakeProvider()
    output = LLMPipeline(provider).analyze(context())
    assert output.decision == "REVISAR" and output.implementation == "llm:fake"
    assert output.model == "test-model" and output.prompt_version == "portfolio-demo-v2"
    sent = provider.calls[0][1]
    assert set(sent) == {"classification", "instrument_ids", "documents"}
    assert "profile" not in sent and "exposures" not in sent and "quantity" not in json.dumps(sent)


def test_no_evidence_abstains_without_calling_provider():
    provider = FakeProvider()
    ctx = context().model_copy(update={"documents": []})
    output = LLMPipeline(provider).analyze(ctx)
    assert output.decision == "ABSTENERSE" and provider.calls == []


@pytest.mark.parametrize("response", ["not json", json.dumps({**draft(), "extra": "secret"})])
def test_invalid_model_output_is_rejected(response):
    with pytest.raises(ProviderError, match="incumple"):
        LLMPipeline(FakeProvider(response)).analyze(context())


def test_model_cannot_invent_evidence_or_instrument():
    data = draft()
    data["findings"][0]["evidence"][0]["excerpt"] = "inventado"
    with pytest.raises(ProviderError, match="evidencias"):
        LLMPipeline(FakeProvider(json.dumps(data))).analyze(context())
    data = draft()
    data["proposed_positions"] = [{"instrument_id": "UNKNOWN", "action": "REVISAR", "rationale": "x",
                                  "evidence": data["findings"][0]["evidence"], "risks": []}]
    with pytest.raises(ProviderError, match="contrato"):
        LLMPipeline(FakeProvider(json.dumps(data))).analyze(context())
    data = draft()
    data["findings"][0]["issuer_candidates"] = ["EMISOR INVENTADO"]
    with pytest.raises(ProviderError, match="contrato"):
        LLMPipeline(FakeProvider(json.dumps(data))).analyze(context())


def test_external_context_not_sent():
    provider = FakeProvider()
    portfolio = context().portfolio.model_copy(deep=True)
    portfolio.positions[0].instrument_id = "REAL-ID"
    with pytest.raises(ValueError, match="fixtures"):
        LLMPipeline(provider).analyze(context().model_copy(update={"portfolio": portfolio}))
    assert provider.calls == []


def test_default_factory_is_mock(monkeypatch):
    monkeypatch.delenv("INTELLIGENCE_PROVIDER", raising=False)
    assert isinstance(pipeline_from_env(), MockPipeline)


def test_demo_outputs_the_same_contract(monkeypatch, capsys):
    from app.intelligence.demo import main
    monkeypatch.setenv("INTELLIGENCE_PROVIDER", "mock")
    assert main([]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["contract_version"] == "1.1"
    assert payload["data_classification"] == "SIMULATED"
    assert payload["findings"][0]["issuer_candidates"] == ["DEMO:CHIP"]
    assert payload["proposed_positions"] == []


@pytest.mark.parametrize("name,key,expected", [("xai", "XAI_API_KEY", "grok-4.3"), ("groq", "GROQ_API_KEY", "openai/gpt-oss-20b")])
def test_provider_configuration(monkeypatch, name, key, expected):
    monkeypatch.setenv("INTELLIGENCE_PROVIDER", name)
    monkeypatch.setenv(key, "unit-test-key")
    monkeypatch.delenv("INTELLIGENCE_MODEL", raising=False)
    provider = provider_from_env()
    assert provider.name == name and provider.model == expected
    assert "unit-test-key" not in repr(provider)


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload
    def __enter__(self):
        return self
    def __exit__(self, *args):
        pass
    def read(self):
        return json.dumps(self.payload).encode()


@pytest.mark.parametrize("name", ["xai", "groq"])
def test_http_wire_format_without_network(monkeypatch, name):
    captured = {}
    content = json.dumps(draft())
    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["body"] = json.loads(request.data)
        if name == "xai":
            return FakeResponse({"status": "completed", "output": [{"type": "message", "content": [{"type": "output_text", "text": content}]}]})
        return FakeResponse({"choices": [{"finish_reason": "stop", "message": {"content": content}}]})
    monkeypatch.setattr("app.intelligence.providers.urlopen", fake_urlopen)
    provider = APIProvider(name, "test-model", "test-key")
    assert json.loads(provider.generate("system", "data", ModelDraft.model_json_schema())) == draft()
    if name == "xai":
        assert captured["url"] == "https://api.x.ai/v1/responses"
        assert captured["body"]["text"]["format"]["type"] == "json_schema"
        assert captured["body"]["store"] is False
    else:
        assert captured["url"] == "https://api.groq.com/openai/v1/chat/completions"
        assert captured["body"]["response_format"]["json_schema"]["strict"] is True


def test_http_errors_do_not_expose_key_or_response(monkeypatch):
    def fail(request, timeout):
        raise HTTPError(request.full_url, 429, "secret-body", {}, BytesIO(b"secret-body"))
    monkeypatch.setattr("app.intelligence.providers.urlopen", fail)
    with pytest.raises(ProviderError) as error:
        APIProvider("xai", "model", "secret-key").generate("sensitive", "data", {})
    assert "429" in str(error.value)
    assert "secret" not in str(error.value) and "sensitive" not in str(error.value)


@pytest.mark.parametrize("name", ["xai", "groq"])
def test_complete_pipeline_with_mocked_http(monkeypatch, name):
    content = json.dumps(draft())
    def fake_urlopen(request, timeout):
        if name == "xai":
            return FakeResponse({"status": "completed", "output": [{"type": "message", "content": [{"type": "output_text", "text": content}]}]})
        return FakeResponse({"choices": [{"finish_reason": "stop", "message": {"content": content}}]})
    monkeypatch.setattr("app.intelligence.providers.urlopen", fake_urlopen)
    output = LLMPipeline(APIProvider(name, "fake-model", "fake-key")).analyze(context())
    assert json.loads(output.model_dump_json())["findings"][0]["evidence"][0]["document_id"] == "DOC-DEMO-001"
    assert output.implementation == f"llm:{name}"


def test_ollama_factory_and_wire_format(monkeypatch):
    monkeypatch.setenv("INTELLIGENCE_PROVIDER", "ollama")
    monkeypatch.delenv("INTELLIGENCE_MODEL", raising=False)
    monkeypatch.setenv("OLLAMA_HOST", "127.0.0.1:11435")
    captured = {}

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["body"] = json.loads(request.data)
        return FakeResponse({"done": True, "done_reason": "stop", "message": {"content": json.dumps(draft())}})

    monkeypatch.setattr("app.intelligence.providers.urlopen", fake_urlopen)
    provider = provider_from_env()
    assert isinstance(provider, OllamaProvider) and provider.model == "qwen3:1.7b"
    output = LLMPipeline(provider).analyze(context())
    assert output.implementation == "llm:ollama"
    assert captured["url"] == "http://127.0.0.1:11435/api/chat"
    assert captured["body"]["format"] == ModelDraft.model_json_schema()
    assert captured["body"]["stream"] is False and captured["body"]["think"] is False


@pytest.mark.parametrize("host", ["https://localhost:11434", "example.com:11434", "localhost.evil:11434", "ollama.evil:11434",
                                  "user@localhost:11434", "localhost:11434/path", "localhost:99999"])
def test_ollama_disallows_nonlocal_or_malformed_hosts(host):
    with pytest.raises(ValueError):
        OllamaProvider(host=host)


@pytest.mark.parametrize("payload", [{"done": False, "message": {"content": "{}"}},
                                   {"done": True, "done_reason": "length", "message": {"content": "{}"}},
                                   {"done": True, "message": {"content": ""}}])
def test_ollama_rejects_incomplete_output(monkeypatch, payload):
    monkeypatch.setattr("app.intelligence.providers.urlopen", lambda request, timeout: FakeResponse(payload))
    with pytest.raises(ProviderError, match="incompleta"):
        OllamaProvider().generate("system", "data", {})
