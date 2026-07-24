"""OCR fallback for scanned PDF pages."""

from __future__ import annotations

import io

from PIL import Image
import pytesseract


class OCRUnavailableError(RuntimeError):
    pass


def extract_image_text(image_bytes: bytes, language: str = "eng") -> str:
    try:
        image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        return pytesseract.image_to_string(image, lang=language).strip()
    except pytesseract.TesseractNotFoundError as exc:
        raise OCRUnavailableError(
            "Tesseract OCR is not installed or is not available on PATH."
        ) from exc
