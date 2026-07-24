"""Evidence-preserving cross-document merge and conflict detection."""

from __future__ import annotations

import json
import re
from collections import defaultdict
from typing import Any

from models.schemas import (
    DocumentExtraction,
    ExtractedRecord,
    MergedField,
    SourcedValue,
    UnifiedRepresentation,
    ValidationIssue,
    ValidationResult,
)


def _field_key(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.casefold()).strip("_")


def _value_key(value: Any) -> str:
    if isinstance(value, str):
        return re.sub(r"\s+", " ", value).strip().casefold()
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def _record_key(record: ExtractedRecord) -> str:
    payload = {
        name: sourced.value
        for name, sourced in sorted(record.fields.items())
    }
    return (
        record.record_type.casefold()
        + ":"
        + json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    )


class MergeAgent:
    def merge(
        self,
        extractions: list[DocumentExtraction],
        validations: list[ValidationResult],
    ) -> UnifiedRepresentation:
        candidates: dict[str, list[tuple[str, str, SourcedValue]]] = defaultdict(list)
        missing_names: dict[str, str] = {}
        for extraction in extractions:
            for name, sourced in extraction.fields.items():
                candidates[_field_key(name)].append(
                    (name, extraction.filename, sourced)
                )
            for conflict in extraction.conflicts:
                for alternative in conflict.alternatives:
                    candidates[_field_key(conflict.field)].append(
                        (conflict.field, extraction.filename, alternative)
                    )
            for name in extraction.missing_fields:
                missing_names.setdefault(_field_key(name), name)

        merged_fields: dict[str, MergedField] = {}
        issues = [issue for result in validations for issue in result.issues]
        for key, entries in candidates.items():
            display_name = entries[0][0]
            available = [entry for entry in entries if entry[2].value is not None]
            if not available:
                merged_fields[display_name] = MergedField(status="missing")
                continue

            groups: dict[str, list[tuple[str, str, SourcedValue]]] = defaultdict(list)
            for entry in available:
                groups[_value_key(entry[2].value)].append(entry)

            if len(groups) == 1:
                group = next(iter(groups.values()))
                sources = [
                    source for _, _, sourced in group for source in sourced.sources
                ]
                documents = {document for _, document, _ in group}
                merged_fields[display_name] = MergedField(
                    status="verified" if len(documents) > 1 else "single_source",
                    value=group[0][2].value,
                    sources=list(
                        {
                            (source.document, source.page, source.excerpt): source
                            for source in sources
                        }.values()
                    ),
                )
            else:
                alternatives = [group[0][2] for group in groups.values()]
                documents = sorted(
                    {document for _, document, _ in available}
                )
                merged_fields[display_name] = MergedField(
                    status="conflict",
                    value=None,
                    alternatives=alternatives,
                    sources=[
                        source
                        for alternative in alternatives
                        for source in alternative.sources
                    ],
                )
                issues.append(
                    ValidationIssue(
                        kind="contradiction",
                        field=display_name,
                        description=(
                            f"Conflicting values were extracted for '{display_name}'."
                        ),
                        documents=documents,
                        sources=[
                            source
                            for alternative in alternatives
                            for source in alternative.sources
                        ],
                        severity="error",
                    )
                )

        for key, display_name in missing_names.items():
            if key not in candidates:
                merged_fields[display_name] = MergedField(status="missing")

        unique_records: dict[str, ExtractedRecord] = {}
        for extraction in extractions:
            for record in extraction.records:
                unique_records.setdefault(_record_key(record), record)

        unique_issues: dict[tuple, ValidationIssue] = {}
        for issue in issues:
            issue_key = (
                issue.kind,
                issue.field,
                tuple(sorted(issue.documents)),
                None if issue.kind == "contradiction" else issue.description,
            )
            unique_issues.setdefault(issue_key, issue)

        return UnifiedRepresentation(
            fields=merged_fields,
            records=list(unique_records.values()),
            issues=list(unique_issues.values()),
        )
