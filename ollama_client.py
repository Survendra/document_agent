"""Small, schema-aware client for the local Ollama API."""

from __future__ import annotations

import json
import time
from typing import Any

import requests
from pydantic import BaseModel

from config import Settings


class OllamaError(RuntimeError):
    pass


class OllamaClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def generate_json(
        self,
        *,
        system: str,
        user: str,
        response_model: type[BaseModel],
    ) -> BaseModel:
        schema = response_model.model_json_schema()
        error: Exception | None = None
        for attempt in range(self.settings.max_retries + 1):
            try:
                response = requests.post(
                    f"{self.settings.ollama_url.rstrip('/')}/api/chat",
                    json={
                        "model": self.settings.ollama_model,
                        "stream": False,
                        "format": schema,
                        "messages": [
                            {"role": "system", "content": system},
                            {"role": "user", "content": user},
                        ],
                        "options": {"temperature": 0, "num_ctx": 8192},
                    },
                    timeout=self.settings.request_timeout_seconds,
                )
                response.raise_for_status()
                payload: dict[str, Any] = response.json()
                content = payload["message"]["content"].strip()
                if content.startswith("```"):
                    content = content.strip("`")
                    if content.startswith("json"):
                        content = content[4:].lstrip()
                return response_model.model_validate(json.loads(content))
            except (requests.RequestException, KeyError, ValueError) as exc:
                error = exc
                if attempt < self.settings.max_retries:
                    time.sleep(1 + attempt)

        raise OllamaError(
            f"Ollama failed after {self.settings.max_retries + 1} attempts: {error}"
        )

    def ensure_model(self) -> None:
        try:
            response = requests.get(
                f"{self.settings.ollama_url.rstrip('/')}/api/tags",
                timeout=10,
            )
            response.raise_for_status()
            models = {
                item.get("name")
                for item in response.json().get("models", [])
                if item.get("name")
            }
        except requests.RequestException as exc:
            raise OllamaError(
                f"Cannot reach Ollama at {self.settings.ollama_url}. "
                "Start Ollama before running the pipeline."
            ) from exc

        requested = self.settings.ollama_model
        if requested not in models and f"{requested}:latest" not in models:
            raise OllamaError(
                f"Ollama model '{requested}' is not installed. "
                f"Run: ollama pull {requested}"
            )
