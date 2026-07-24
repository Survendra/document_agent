"""LLM-backed, page-aware document extraction."""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

from config import Settings
from models.schemas import (
    DocumentExtraction,
    DocumentType,
    ExtractedRecord,
    FieldConflict,
    SourceRef,
    SourcedValue,
)
from ollama_client import OllamaClient
from parser.pdf_parser import ParsedDocument

IDENTITY_FIELDS = {
    "course",
    "registration_no",
    "registration_number",
    "roll_number",
    "student_name",
    "university_name",
}

ACADEMIC_EXPECTED_FIELDS = {
    "academic_year",
    "course",
    "percentage",
    "result",
    "roll_number",
    "semester",
    "sgpa",
    "student_name",
    "subjects",
    "total_marks",
    "university_name",
}


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).casefold()


def _normalized(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value)).strip().casefold()


def _field_key(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.casefold()).strip("_")


def _leaf_values(value: Any) -> list[str]:
    if isinstance(value, dict):
        return [leaf for item in value.values() for leaf in _leaf_values(item)]
    if isinstance(value, list):
        return [leaf for item in value for leaf in _leaf_values(item)]
    if value is None or isinstance(value, bool):
        return []
    normalized = _normalized(value)
    return [normalized] if normalized else []


def _ground_source(
    document: ParsedDocument, field_name: str, value: Any
) -> SourceRef | None:
    pages = {
        page.page_number: _normalized(page.text)
        for page in document.pages
    }
    field_label = _normalized(field_name.replace("_", " "))
    if isinstance(value, (str, int, float)) and not isinstance(value, bool):
        value_text = _normalized(value)
        labeled = f"{field_label} {value_text}"
        labeled_colon = f"{field_label}: {value_text}"
        for page_number, text in pages.items():
            if (
                labeled in text
                or labeled_colon in text
                or (len(value_text) >= 3 and value_text in text)
            ):
                return SourceRef(document=document.filename, page=page_number)
        return None

    leaves = [leaf for leaf in _leaf_values(value) if len(leaf) >= 2]
    if not leaves:
        return None
    for page_number, text in pages.items():
        matched = sum(leaf in text for leaf in leaves)
        if matched == len(leaves) or matched / len(leaves) >= 0.8:
            return SourceRef(document=document.filename, page=page_number)
    return None


def _ground_value(
    document: ParsedDocument, field_name: str, sourced: SourcedValue
) -> SourcedValue:
    valid_sources = [
        source
        for source in sourced.sources
        if source.document == document.filename
        and 1 <= source.page <= document.page_count
    ]
    if not valid_sources and sourced.value is not None:
        grounded = _ground_source(document, field_name, sourced.value)
        if grounded is not None:
            valid_sources = [grounded]
    confidence = sourced.confidence if valid_sources else "Low"
    return sourced.model_copy(
        update={"sources": valid_sources, "confidence": confidence}
    )


def _page_chunks(document: ParsedDocument, limit: int) -> list[str]:
    chunks: list[str] = []
    current = ""
    for page in document.pages:
        page_text = f"\n[Page {page.page_number}]\n{page.text}\n"
        while len(page_text) > limit:
            available = max(1, limit - len(current))
            current += page_text[:available]
            page_text = (
                f"\n[Page {page.page_number} continued]\n" + page_text[available:]
            )
            chunks.append(current)
            current = ""
        if current and len(current) + len(page_text) > limit:
            chunks.append(current)
            current = ""
        current += page_text
    if current:
        chunks.append(current)
    return chunks or ["[No readable text]"]


class ExtractionAgent:
    def __init__(self, client: OllamaClient, settings: Settings) -> None:
        self.client = client
        self.settings = settings
        self.system_prompt = (
            Path(__file__).parents[1] / "prompts" / "extract.txt"
        ).read_text(encoding="utf-8")

    def extract(self, document: ParsedDocument) -> DocumentExtraction:
        partials: list[DocumentExtraction] = []
        chunks = _page_chunks(document, self.settings.page_chunk_chars)
        for number, text in enumerate(chunks, start=1):
            prompt = (
                f"Filename: {document.filename}\n"
                f"Total pages: {document.page_count}\n"
                f"Text chunk: {number}/{len(chunks)}\n"
                "The page markers below are authoritative source page numbers.\n"
                f"{text}"
            )
            result = self.client.generate_json(
                system=self.system_prompt,
                user=prompt,
                response_model=DocumentExtraction,
            )
            partials.append(result)
        return self._merge_partials(document, partials)

    def normalize_existing(
        self,
        document: ParsedDocument,
        extraction: DocumentExtraction,
    ) -> DocumentExtraction:
        """Re-ground a persisted extraction without another model request."""
        return self._merge_partials(document, [extraction])

    @staticmethod
    def _merge_partials(
        document: ParsedDocument, partials: list[DocumentExtraction]
    ) -> DocumentExtraction:
        type_counts = Counter(
            item.document_type
            for item in partials
            if item.document_type != DocumentType.UNKNOWN
        )
        document_type = (
            type_counts.most_common(1)[0][0]
            if type_counts
            else DocumentType.UNKNOWN
        )
        combined_text = _normalized(
            " ".join(page.text for page in document.pages)
        )
        academic_markers = ("semester", "subject code", "marks", "sgpa", "result")
        if (
            document_type == DocumentType.UNKNOWN
            and all(marker in combined_text for marker in academic_markers)
        ):
            document_type = DocumentType.ACADEMIC_MARKSHEET

        fields: dict[str, SourcedValue] = {}
        conflicts: dict[str, list[SourcedValue]] = {}
        warnings: list[str] = []
        for partial in partials:
            for name, candidate in partial.fields.items():
                candidate = _ground_value(document, name, candidate)
                if name not in fields:
                    fields[name] = candidate
                elif _canonical(fields[name].value) == _canonical(candidate.value):
                    existing = fields[name]
                    unique_sources = {
                        (source.document, source.page, source.excerpt): source
                        for source in existing.sources + candidate.sources
                    }
                    fields[name] = existing.model_copy(
                        update={"sources": list(unique_sources.values())}
                    )
                else:
                    conflicts.setdefault(name, [fields[name]]).append(candidate)

        for name in conflicts:
            fields.pop(name, None)

        records: list[ExtractedRecord] = []
        for partial in partials:
            for record in partial.records:
                cleaned_fields = {}
                for name, sourced in record.fields.items():
                    cleaned_fields[name] = _ground_value(document, name, sourced)
                records.append(record.model_copy(update={"fields": cleaned_fields}))

        for record in records:
            for name, sourced in record.fields.items():
                if _field_key(name) in IDENTITY_FIELDS and name not in fields:
                    fields[name] = sourced

        present = {_field_key(name) for name in fields}
        present.update(
            _field_key(name)
            for record in records
            for name in record.fields
        )
        if document_type == DocumentType.ACADEMIC_MARKSHEET:
            missing = sorted(ACADEMIC_EXPECTED_FIELDS - present)
        else:
            missing = []
        warnings.extend(
            warning for partial in partials for warning in partial.warnings
        )
        warnings.extend(
            page.warning for page in document.pages if page.warning is not None
        )
        return DocumentExtraction(
            filename=document.filename,
            document_type=document_type,
            page_count=document.page_count,
            fields=fields,
            records=records,
            conflicts=[
                FieldConflict(field=name, alternatives=alternatives)
                for name, alternatives in conflicts.items()
            ],
            missing_fields=missing,
            warnings=list(dict.fromkeys(warnings)),
        )
