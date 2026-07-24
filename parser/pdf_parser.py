"""Extract page-aware text from PDFs, using OCR only when needed."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import fitz

from config import Settings
from ocr.extractor import OCRUnavailableError, extract_image_text


@dataclass(frozen=True)
class ParsedPage:
    page_number: int
    text: str
    used_ocr: bool
    warning: str | None = None


@dataclass(frozen=True)
class ParsedDocument:
    filename: str
    path: Path
    pages: list[ParsedPage]

    @property
    def page_count(self) -> int:
        return len(self.pages)


def parse_pdf(path: str | Path, settings: Settings) -> ParsedDocument:
    pdf_path = Path(path)
    if not pdf_path.is_file():
        raise FileNotFoundError(f"Document not found: {pdf_path}")
    if pdf_path.suffix.lower() != ".pdf":
        raise ValueError(f"Only PDF input is supported: {pdf_path.name}")

    pages: list[ParsedPage] = []
    with fitz.open(pdf_path) as document:
        if document.needs_pass:
            raise ValueError(f"Encrypted PDF requires a password: {pdf_path.name}")
        if document.page_count == 0:
            raise ValueError(f"PDF has no pages: {pdf_path.name}")

        for index, page in enumerate(document):
            text = page.get_text("text").strip()
            used_ocr = False
            warning = None
            if len(text) < settings.ocr_min_chars:
                pixmap = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
                try:
                    ocr_text = extract_image_text(
                        pixmap.tobytes("png"), settings.ocr_language
                    )
                    if len(ocr_text) > len(text):
                        text = ocr_text
                        used_ocr = True
                except OCRUnavailableError as exc:
                    warning = str(exc)

            if not text:
                warning = warning or "No readable text was extracted from this page."
            pages.append(
                ParsedPage(
                    page_number=index + 1,
                    text=text,
                    used_ocr=used_ocr,
                    warning=warning,
                )
            )

    return ParsedDocument(filename=pdf_path.name, path=pdf_path, pages=pages)
