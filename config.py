"""Runtime configuration loaded from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    ollama_url: str = os.getenv("OLLAMA_URL", "http://localhost:11434")
    ollama_model: str = os.getenv("OLLAMA_MODEL", "qwen2.5:7b")
    request_timeout_seconds: int = int(os.getenv("OLLAMA_TIMEOUT", "180"))
    context_char_budget: int = int(os.getenv("CONTEXT_CHAR_BUDGET", "60000"))
    page_chunk_chars: int = int(os.getenv("PAGE_CHUNK_CHARS", "12000"))
    ocr_min_chars: int = int(os.getenv("OCR_MIN_CHARS", "40"))
    ocr_language: str = os.getenv("OCR_LANGUAGE", "eng")
    max_retries: int = int(os.getenv("OLLAMA_MAX_RETRIES", "2"))


settings = Settings()
