"""Deterministic Markdown report generation from verified pipeline artifacts."""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

from models.schemas import (
    DocumentExtraction,
    Observation,
    UnifiedRepresentation,
    ValidationResult,
)


def _value(value: Any) -> str:
    if value is None:
        return "Not Available"
    if isinstance(value, (dict, list)):
        return f"`{json.dumps(value, ensure_ascii=False, default=str)}`"
    return str(value).replace("|", "\\|")


def _sources(sources: list) -> str:
    if not sources:
        return "Not Available"
    return ", ".join(
        f"{source.document}, page {source.page}" for source in sources
    )


class ReportAgent:
    def generate(
        self,
        documents: list[DocumentExtraction],
        validations: list[ValidationResult],
        unified: UnifiedRepresentation,
        observations: list[Observation],
    ) -> str:
        conflicts = [issue for issue in unified.issues if issue.kind == "contradiction"]
        missing = [issue for issue in unified.issues if issue.kind == "missing"]
        duplicates = [issue for issue in unified.issues if issue.kind == "duplicate"]
        warnings = [issue for issue in unified.issues if issue.kind == "warning"]
        verified = [
            (name, field)
            for name, field in unified.fields.items()
            if field.status == "verified"
        ]

        lines = [
            "# Document Intelligence Report",
            "",
            "## Executive Summary",
            (
                f"Processed {len(documents)} document(s). "
                f"{len(verified)} field(s) were cross-verified; "
                f"{len(conflicts)} conflict(s), {len(missing)} missing item(s), "
                f"and {len(duplicates)} duplicate record(s) were identified."
            ),
            "",
            "## Documents Processed",
            "",
            "| Filename | Document type | Pages |",
            "|---|---|---:|",
        ]
        lines.extend(
            f"| {doc.filename} | {doc.document_type} | {doc.page_count} |"
            for doc in documents
        )

        lines.extend(
            [
                "",
                "## Extracted Information",
                "",
                "### Unified fields",
                "",
                "| Field | Value | Status | Source |",
                "|---|---|---|---|",
            ]
        )
        for name, field in unified.fields.items():
            value = (
                _value(field.value)
                if field.status != "conflict"
                else "Not Available (conflict)"
            )
            lines.append(
                f"| {name} | {value} | {field.status} | {_sources(field.sources)} |"
            )

        lines.extend(["", "### Unified records", ""])
        if not unified.records:
            lines.append("Not Available")
        for index, record in enumerate(unified.records, start=1):
            lines.extend([f"#### {record.record_type} {index}", ""])
            for name, sourced in record.fields.items():
                lines.append(
                    f"- {name}: {_value(sourced.value)} "
                    f"(Source: {_sources(sourced.sources)})"
                )

        lines.extend(["", "## Cross Verification Results", ""])
        self._issue_section(lines, "Verified Information", [
            f"{name}: {_value(field.value)} ({_sources(field.sources)})"
            for name, field in verified
        ])
        self._issue_section(
            lines,
            "Conflicts",
            [
                f"{issue.description} Documents: {', '.join(issue.documents)}."
                for issue in conflicts
            ],
        )
        self._issue_section(
            lines,
            "Missing Information",
            [issue.description for issue in missing],
        )
        self._issue_section(
            lines,
            "Duplicates",
            [issue.description for issue in duplicates],
        )
        self._issue_section(
            lines,
            "Warnings",
            [issue.description for issue in warnings],
        )

        lines.extend(["", "## Detailed Analysis", ""])
        for document, validation in zip(documents, validations, strict=True):
            lines.extend(
                [
                    f"### {document.filename}",
                    f"- Type: {document.document_type}",
                    f"- Extracted fields: {len(document.fields)}",
                    f"- Extracted records: {len(document.records)}",
                    f"- Validation status: {'Passed' if validation.valid else 'Review required'}",
                ]
            )
        lines.extend(["", "### Observations", ""])
        if observations:
            lines.extend(
                f"- {item.statement} Source: {_sources(item.evidence)} "
                f"Confidence: {item.confidence}."
                for item in observations
            )
        else:
            lines.append("No supported cross-document trend was available.")

        lines.extend(["", "## Findings", ""])
        findings = [
            item.statement for item in observations if item.inference
        ] + [issue.description for issue in conflicts + missing + duplicates]
        lines.extend(f"- {finding}" for finding in findings)
        if not findings:
            lines.append("- No additional findings beyond the extracted facts.")

        lines.extend(["", "## Confidence Assessment", ""])
        lines.extend(
            [
                "- High: values independently consistent across multiple documents.",
                "- Medium: observations calculated from sourced extracted records.",
                "- Low: unresolved or weakly sourced information; not used as verified fact.",
            ]
        )
        lines.extend(["", "## Final Summary", ""])
        lines.append(
            f"The report contains {len(unified.fields)} unified field(s) and "
            f"{len(unified.records)} unique record(s). Conflicting values remain "
            "unresolved, and unavailable values are explicitly marked."
        )
        return "\n".join(lines).rstrip() + "\n"

    @staticmethod
    def _issue_section(lines: list[str], title: str, items: list[str]) -> None:
        lines.extend([f"### {title}", ""])
        lines.extend(f"- {item}" for item in items)
        if not items:
            lines.append("- None")
        lines.append("")

    @staticmethod
    def write_pdf(markdown: str, output_path: str | Path) -> None:
        styles = getSampleStyleSheet()
        story = []
        for raw_line in markdown.splitlines():
            line = raw_line.strip()
            if not line:
                story.append(Spacer(1, 2 * mm))
                continue
            if line.startswith("# "):
                style = styles["Title"]
                text = line[2:]
            elif line.startswith("## "):
                style = styles["Heading2"]
                text = line[3:]
            elif line.startswith("### "):
                style = styles["Heading3"]
                text = line[4:]
            elif line.startswith("#### "):
                style = styles["Heading4"]
                text = line[5:]
            else:
                style = styles["BodyText"]
                text = line
            story.append(Paragraph(html.escape(text), style))
        document = SimpleDocTemplate(
            str(output_path),
            pagesize=A4,
            rightMargin=16 * mm,
            leftMargin=16 * mm,
            topMargin=16 * mm,
            bottomMargin=16 * mm,
        )
        document.build(story)
