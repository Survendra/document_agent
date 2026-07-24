from pathlib import Path

from agents.extractor import ExtractionAgent
from agents.analysis import AnalysisAgent
from agents.merger import MergeAgent
from agents.report_agent import ReportAgent
from context import PipelineMemory
from models.schemas import (
    DocumentExtraction,
    ExtractedRecord,
    SourceRef,
    SourcedValue,
    UnifiedRepresentation,
    ValidationResult,
)
from parser.pdf_parser import ParsedDocument, ParsedPage


def sourced(value, document, page=1):
    return SourcedValue(
        value=value,
        sources=[SourceRef(document=document, page=page)],
        confidence="High",
    )


def extraction(filename, student_name):
    return DocumentExtraction(
        filename=filename,
        document_type="Academic Marksheet",
        page_count=1,
        fields={"student_name": sourced(student_name, filename)},
        records=[
            ExtractedRecord(
                record_type="subject",
                fields={
                    "subject": sourced("Mathematics", filename),
                    "marks": sourced("88", filename),
                },
            )
        ],
    )


def test_consistent_values_are_cross_verified():
    documents = [extraction("one.pdf", "Asha"), extraction("two.pdf", "Asha")]
    validations = [
        ValidationResult(document=item.filename, valid=True) for item in documents
    ]

    unified = MergeAgent().merge(documents, validations)

    assert unified.fields["student_name"].status == "verified"
    assert unified.fields["student_name"].value == "Asha"
    assert len(unified.fields["student_name"].sources) == 2


def test_conflicts_remain_unresolved():
    documents = [extraction("one.pdf", "Asha"), extraction("two.pdf", "Isha")]
    validations = [
        ValidationResult(document=item.filename, valid=True) for item in documents
    ]

    unified = MergeAgent().merge(documents, validations)

    assert unified.fields["student_name"].status == "conflict"
    assert unified.fields["student_name"].value is None
    assert len(unified.fields["student_name"].alternatives) == 2
    assert any(issue.kind == "contradiction" for issue in unified.issues)


def test_report_contains_required_sections():
    documents = [extraction("one.pdf", "Asha"), extraction("two.pdf", "Asha")]
    validations = [
        ValidationResult(document=item.filename, valid=True) for item in documents
    ]
    unified = MergeAgent().merge(documents, validations)
    observations = AnalysisAgent().analyze(unified)

    report = ReportAgent().generate(
        documents, validations, unified, observations
    )

    for heading in (
        "## Executive Summary",
        "## Documents Processed",
        "## Extracted Information",
        "## Cross Verification Results",
        "## Detailed Analysis",
        "## Findings",
        "## Confidence Assessment",
        "## Final Summary",
    ):
        assert heading in report


def test_memory_compacts_and_clears_transient_payloads():
    memory = PipelineMemory(char_budget=100)
    memory.set_transient("raw_ocr", "large payload")
    for index in range(10):
        memory.remember_fact({"filename": f"{index}.pdf", "value": "x" * 40})
    memory.clear_tools()

    assert memory.get_transient("raw_ocr") is None
    assert memory.summaries
    assert len(memory.prompt_context()) <= 100


def test_existing_extraction_is_classified_and_grounded():
    parsed = ParsedDocument(
        filename="marks.pdf",
        path=Path("marks.pdf"),
        pages=[
            ParsedPage(
                page_number=1,
                text=(
                    "University Name: XYZ University\nSemester: I\n"
                    "Student Name: Rahul Sharma\nSubject Code Subject Name Marks\n"
                    "CS101 Programming 86\nSGPA: 8.72\nResult: PASS"
                ),
                used_ocr=False,
            )
        ],
    )
    raw = DocumentExtraction(
        filename="marks.pdf",
        document_type="Unknown",
        page_count=1,
        records=[
            ExtractedRecord(
                record_type="exam_result",
                fields={
                    "university_name": SourcedValue(value="XYZ University"),
                    "student_name": SourcedValue(value="Rahul Sharma"),
                    "semester": SourcedValue(value="I"),
                    "sgpa": SourcedValue(value="8.72"),
                },
            )
        ],
    )

    normalized = ExtractionAgent._merge_partials(parsed, [raw])

    assert normalized.document_type == "Academic Marksheet"
    assert normalized.fields["student_name"].sources[0].page == 1
    assert normalized.records[0].fields["semester"].sources[0].page == 1


def test_academic_observations_include_trends_and_subject_extremes():
    records = []
    for semester, percentage, sgpa, subject, marks, filename in (
        ("I", "84.00%", "8.72", "Mathematics", 81, "one.pdf"),
        ("II", "84.80%", "8.84", "Programming", 91, "two.pdf"),
    ):
        records.append(
            ExtractedRecord(
                record_type="exam_result",
                fields={
                    "semester": sourced(semester, filename),
                    "percentage": sourced(percentage, filename),
                    "sgpa": sourced(sgpa, filename),
                    "subjects": sourced(
                        [{"name": subject, "marks": marks}], filename
                    ),
                },
            )
        )

    observations = AnalysisAgent().analyze(
        UnifiedRepresentation(records=records)
    )
    statements = [item.statement for item in observations]

    assert any("sgpa increased" in statement for statement in statements)
    assert any("Highest subject mark: 91" in statement for statement in statements)
    assert any("Lowest subject mark: 81" in statement for statement in statements)
