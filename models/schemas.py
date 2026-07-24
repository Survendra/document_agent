"""Pydantic models shared by every pipeline stage."""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class DocumentType(str, Enum):
    ACADEMIC_MARKSHEET = "Academic Marksheet"
    TRANSCRIPT = "Transcript"
    RESUME = "Resume"
    INVOICE = "Invoice"
    BANK_STATEMENT = "Bank Statement"
    MEDICAL_REPORT = "Medical Report"
    IDENTITY_DOCUMENT = "Identity Document"
    CERTIFICATE = "Certificate"
    UNKNOWN = "Unknown"


class SourceRef(BaseModel):
    document: str
    page: int = Field(ge=1)
    excerpt: str | None = None


class SourcedValue(BaseModel):
    value: Any = None
    sources: list[SourceRef] = Field(default_factory=list)
    confidence: Literal["High", "Medium", "Low"] = "Medium"


class ExtractedRecord(BaseModel):
    record_type: str
    record_id: str | None = None
    fields: dict[str, SourcedValue] = Field(default_factory=dict)


class FieldConflict(BaseModel):
    field: str
    alternatives: list[SourcedValue] = Field(min_length=2)


class DocumentExtraction(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    filename: str
    document_type: DocumentType = DocumentType.UNKNOWN
    page_count: int = Field(ge=1)
    fields: dict[str, SourcedValue] = Field(default_factory=dict)
    records: list[ExtractedRecord] = Field(default_factory=list)
    conflicts: list[FieldConflict] = Field(default_factory=list)
    missing_fields: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


IssueKind = Literal[
    "missing",
    "format",
    "duplicate",
    "contradiction",
    "impossible_value",
    "warning",
]


class ValidationIssue(BaseModel):
    kind: IssueKind
    field: str | None = None
    description: str
    documents: list[str] = Field(default_factory=list)
    sources: list[SourceRef] = Field(default_factory=list)
    severity: Literal["error", "warning", "info"] = "warning"


class ValidationResult(BaseModel):
    document: str
    valid: bool
    issues: list[ValidationIssue] = Field(default_factory=list)


class MergedField(BaseModel):
    status: Literal["verified", "single_source", "conflict", "missing"]
    value: Any = None
    sources: list[SourceRef] = Field(default_factory=list)
    alternatives: list[SourcedValue] = Field(default_factory=list)


class UnifiedRepresentation(BaseModel):
    fields: dict[str, MergedField] = Field(default_factory=dict)
    records: list[ExtractedRecord] = Field(default_factory=list)
    issues: list[ValidationIssue] = Field(default_factory=list)


class Observation(BaseModel):
    statement: str
    evidence: list[SourceRef] = Field(default_factory=list)
    confidence: Literal["High", "Medium", "Low"]
    inference: bool = True


class PipelineResult(BaseModel):
    documents: list[DocumentExtraction]
    validations: list[ValidationResult]
    unified: UnifiedRepresentation
    observations: list[Observation] = Field(default_factory=list)
    report_markdown: str
