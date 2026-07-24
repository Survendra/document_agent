"""Deterministic validation of extracted facts and source references."""

from __future__ import annotations

import json
import re
from typing import Any, Iterable

from models.schemas import (
    DocumentExtraction,
    ExtractedRecord,
    SourcedValue,
    ValidationIssue,
    ValidationResult,
)
from parser.pdf_parser import ParsedDocument


def _plain(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value)).strip().casefold()


def _record_key(record: ExtractedRecord) -> str:
    values = {
        name: sourced.value
        for name, sourced in sorted(record.fields.items())
    }
    return f"{record.record_type.casefold()}:{json.dumps(values, sort_keys=True, default=str)}"


def _iter_values(
    extraction: DocumentExtraction,
) -> Iterable[tuple[str, SourcedValue]]:
    yield from extraction.fields.items()
    for index, record in enumerate(extraction.records):
        for field, value in record.fields.items():
            yield f"records[{index}].{field}", value


class ValidationAgent:
    def validate(
        self,
        extraction: DocumentExtraction,
        parsed: ParsedDocument,
    ) -> ValidationResult:
        issues: list[ValidationIssue] = []
        page_text = {
            page.page_number: _plain(page.text)
            for page in parsed.pages
        }

        for conflict in extraction.conflicts:
            sources = [
                source
                for alternative in conflict.alternatives
                for source in alternative.sources
            ]
            issues.append(
                ValidationIssue(
                    kind="contradiction",
                    field=conflict.field,
                    description=(
                        f"Conflicting values for '{conflict.field}' were extracted "
                        "from different parts of the document."
                    ),
                    documents=[extraction.filename],
                    sources=sources,
                    severity="error",
                )
            )

        for field in extraction.missing_fields:
            issues.append(
                ValidationIssue(
                    kind="missing",
                    field=field,
                    description=f"Expected field '{field}' is not available.",
                    documents=[extraction.filename],
                    severity="info",
                )
            )

        for field, sourced in _iter_values(extraction):
            if sourced.value is None:
                issues.append(
                    ValidationIssue(
                        kind="missing",
                        field=field,
                        description=f"Field '{field}' has no readable value.",
                        documents=[extraction.filename],
                        sources=sourced.sources,
                        severity="info",
                    )
                )
                continue
            if not sourced.sources:
                issues.append(
                    ValidationIssue(
                        kind="warning",
                        field=field,
                        description=f"Field '{field}' has no valid page source.",
                        documents=[extraction.filename],
                        severity="error",
                    )
                )
                continue

            value_text = _plain(sourced.value)
            scalar = isinstance(sourced.value, (str, int, float))
            if scalar and value_text and not any(
                value_text in page_text.get(source.page, "")
                for source in sourced.sources
            ):
                issues.append(
                    ValidationIssue(
                        kind="warning",
                        field=field,
                        description=(
                            f"Value for '{field}' was not found verbatim on its "
                            "cited page; review OCR and extraction."
                        ),
                        documents=[extraction.filename],
                        sources=sourced.sources,
                        severity="warning",
                    )
                )

        seen_records: dict[str, int] = {}
        for index, record in enumerate(extraction.records):
            key = _record_key(record)
            if key in seen_records:
                issues.append(
                    ValidationIssue(
                        kind="duplicate",
                        field=f"records[{index}]",
                        description=(
                            f"Record duplicates records[{seen_records[key]}]."
                        ),
                        documents=[extraction.filename],
                        severity="warning",
                    )
                )
            else:
                seen_records[key] = index

        issues.extend(
            ValidationIssue(
                kind="warning",
                description=warning,
                documents=[extraction.filename],
                severity="warning",
            )
            for warning in extraction.warnings
        )
        return ValidationResult(
            document=extraction.filename,
            valid=not any(issue.severity == "error" for issue in issues),
            issues=issues,
        )
