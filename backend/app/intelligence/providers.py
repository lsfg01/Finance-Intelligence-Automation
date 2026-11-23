"""Clientes HTTP mínimos; nunca se ejecutan durante la importación."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


class ProviderError(RuntimeError):
    """Error sin incluir claves, prompts ni respuesta del proveedor."""


class TextProvider(Protocol):
    name: str
    model: str

    def generate(self, system: str, data: str, schema: dict) -> str: ...


@dataclass(frozen=True, repr=False)
class APIProvider:
    name: str
    model: str
    api_key: str
    timeout_seconds: float = 60.0
    max_output_tokens: int = 2048

    def __post_init__(self):
        if self.name not in {"xai", "groq"}:
            raise ValueError("Proveedor desconocido")
        if not self.api_key.strip() or not self.model.strip():
            raise ValueError("Faltan clave o modelo")
        if self.timeout_seconds <= 0 or self.max_output_tokens < 1:
            raise ValueError("Límites inválidos")

    def generate(self, system: str, data: str, schema: dict) -> str:
        if self.name == "xai":
            url = "https://api.x.ai/v1/responses"
            body = {
                "model": self.model,
                "input": [{"role": "system", "content": system}, {"role": "user", "content": data}],
                "text": {"format": {"type": "json_schema", "name": "intelligence_draft", "schema": schema, "strict": True}},
                "max_output_tokens": self.max_output_tokens,
                "reasoning": {"effort": "none"},
                "store": False,
            }
        else:
            url = "https://api.groq.com/openai/v1/chat/completions"
            body = {
                "model": self.model,
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": data}],
                "response_format": {"type": "json_schema", "json_schema": {"name": "intelligence_draft", "schema": schema, "strict": True}},
                "max_completion_tokens": self.max_output_tokens,
            }
        request = Request(url, data=json.dumps(body, ensure_ascii=False).encode("utf-8"), method="POST",
                          headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"})
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                payload = json.loads(response.read())
        except HTTPError as exc:
            raise ProviderError(f"El proveedor rechazó la solicitud (HTTP {exc.code})") from None
        except (URLError, OSError, TimeoutError):
            raise ProviderError("No se pudo conectar con el proveedor") from None
        except (ValueError, UnicodeDecodeError):
            raise ProviderError("El proveedor devolvió una respuesta HTTP inválida") from None
        try:
            if self.name == "xai":
                if payload.get("status") != "completed":
                    raise ValueError("respuesta incompleta")
                texts = [part["text"] for item in payload["output"] if item.get("type") == "message"
                         for part in item.get("content", []) if part.get("type") == "output_text"]
                if len(texts) != 1:
                    raise ValueError("respuesta sin texto único")
                content = texts[0]
            else:
                choice = payload["choices"][0]
                if choice.get("finish_reason") != "stop" or choice["message"].get("refusal"):
                    raise ValueError("respuesta incompleta o rechazada")
                content = choice["message"]["content"]
            if not isinstance(content, str) or not content.strip():
                raise ValueError("respuesta vacía")
            return content
        except (AttributeError, KeyError, IndexError, TypeError, ValueError):
            raise ProviderError("El proveedor devolvió una respuesta incompleta o rechazada") from None


@dataclass(frozen=True)
class OllamaProvider:
    """Modelo local: loopback o el servicio Ollama de la red de Compose."""

    model: str = "qwen3:1.7b"
    host: str = "127.0.0.1:11434"
    timeout_seconds: float = 300.0
    name: str = "ollama"

    def __post_init__(self):
        if not self.model.strip() or self.timeout_seconds <= 0:
            raise ValueError("Modelo o timeout inválidos")
        try:
            parsed = urlsplit(self.host if "://" in self.host else f"http://{self.host}")
            if (parsed.scheme != "http" or parsed.hostname not in {"localhost", "127.0.0.1", "::1", "ollama"}
                    or parsed.username is not None or parsed.password is not None
                    or parsed.path not in {"", "/"} or parsed.query or parsed.fragment):
                raise ValueError("Ollama debe usar loopback o el servicio de Compose")
            _ = parsed.port
        except ValueError:
            raise ValueError("Ollama debe usar loopback o el servicio de Compose mediante HTTP") from None

    def generate(self, system: str, data: str, schema: dict) -> str:
        base = self.host if "://" in self.host else f"http://{self.host}"
        body = {"model": self.model, "messages": [{"role": "system", "content": system},
                {"role": "user", "content": data}], "format": schema, "stream": False,
                "think": False, "options": {"temperature": 0, "num_predict": 2048, "num_ctx": 4096}}
        request = Request(base.rstrip("/") + "/api/chat", data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
                          method="POST", headers={"Content-Type": "application/json"})
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                payload = json.loads(response.read())
        except HTTPError as exc:
            raise ProviderError(f"Ollama rechazó la solicitud (HTTP {exc.code})") from None
        except (URLError, OSError, TimeoutError):
            raise ProviderError("No se pudo conectar con Ollama local") from None
        except (ValueError, UnicodeDecodeError):
            raise ProviderError("Ollama devolvió una respuesta HTTP inválida") from None
        try:
            content = payload["message"]["content"]
            if not payload.get("done") or payload.get("done_reason") == "length" or not isinstance(content, str) or not content.strip():
                raise ValueError("respuesta incompleta")
            return content
        except (AttributeError, KeyError, TypeError, ValueError):
            raise ProviderError("Ollama devolvió una respuesta incompleta o vacía") from None


def provider_from_env() -> TextProvider:
    """Solo llamar explícitamente; no imprime ni guarda claves."""
    name = os.environ.get("INTELLIGENCE_PROVIDER", "mock").lower()
    if name == "ollama":
        return OllamaProvider(model=os.environ.get("INTELLIGENCE_MODEL", "qwen3:1.7b"),
                              host=os.environ.get("OLLAMA_HOST", "127.0.0.1:11434"))
    if name == "xai":
        return APIProvider("xai", os.environ.get("INTELLIGENCE_MODEL", "grok-4.3"), os.environ.get("XAI_API_KEY", ""))
    if name == "groq":
        return APIProvider("groq", os.environ.get("INTELLIGENCE_MODEL", "openai/gpt-oss-20b"), os.environ.get("GROQ_API_KEY", ""))
    raise ValueError("Configura INTELLIGENCE_PROVIDER como ollama, xai o groq")
