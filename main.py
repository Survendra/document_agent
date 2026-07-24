"""Command-line coordinator for the document intelligence pipeline."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from agents.analysis import AnalysisAgent
from agents.extractor import ExtractionAgent
from agents.merger import MergeAgent
from agents.report_agent import ReportAgent
from agents.validator import ValidationAgent
from config import Settings, settings
from context import PipelineMemory
from models.schemas import DocumentExtraction, PipelineResult
from ollama_client import OllamaClient, OllamaError
from parser.pdf_parser import parse_pdf


def run_pipeline(
    pdf_paths: list[str | Path],
    output_directory: str | Path,
    *,
    runtime_settings: Settings = settings,
    create_pdf: bool = True,
    reuse_extractions: bool = False,
) -> PipelineResult:
    if not pdf_paths:
        raise ValueError("At least one PDF document is required.")

    output = Path(output_directory)
    output.mkdir(parents=True, exist_ok=True)
    client = OllamaClient(runtime_settings)
    if not reuse_extractions:
        client.ensure_model()
    extractor = ExtractionAgent(client, runtime_settings)
    validator = ValidationAgent()
    memory = PipelineMemory(runtime_settings.context_char_budget)

    extractions = []
    validations = []
    for path in pdf_paths:
        parsed = parse_pdf(path, runtime_settings)
        memory.set_transient("parsed_document", parsed)
        extraction_path = output / f"{Path(path).stem}.extraction.json"
        if reuse_extractions:
            if not extraction_path.is_file():
                raise FileNotFoundError(
                    f"Reusable extraction not found: {extraction_path}"
                )
            extraction = extractor.normalize_existing(
                parsed,
                DocumentExtraction.model_validate_json(
                    extraction_path.read_text(encoding="utf-8")
                ),
            )
        else:
            extraction = extractor.extract(parsed)
        validation = validator.validate(extraction, parsed)
        extractions.append(extraction)
        validations.append(validation)
        memory.remember_fact(extraction.model_dump(mode="json"))
        memory.clear_tools()

        stem = Path(path).stem
        (output / f"{stem}.extraction.json").write_text(
            extraction.model_dump_json(indent=2),
            encoding="utf-8",
        )
        (output / f"{stem}.validation.json").write_text(
            validation.model_dump_json(indent=2),
            encoding="utf-8",
        )

    unified = MergeAgent().merge(extractions, validations)
    observations = AnalysisAgent().analyze(unified)
    report_agent = ReportAgent()
    report = report_agent.generate(
        extractions, validations, unified, observations
    )
    result = PipelineResult(
        documents=extractions,
        validations=validations,
        unified=unified,
        observations=observations,
        report_markdown=report,
    )

    (output / "unified.json").write_text(
        unified.model_dump_json(indent=2), encoding="utf-8"
    )
    (output / "result.json").write_text(
        result.model_dump_json(indent=2), encoding="utf-8"
    )
    (output / "report.md").write_text(report, encoding="utf-8")
    if create_pdf:
        report_agent.write_pdf(report, output / "report.pdf")
    (output / "memory_summary.json").write_text(
        json.dumps(
            {
                "summaries": memory.summaries,
                "retained_fact_count": len(memory.facts),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return result


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Extract, verify, merge, and report facts from PDF documents."
    )
    parser.add_argument("pdfs", nargs="+", help="One or more input PDF paths")
    parser.add_argument(
        "-o", "--output", default="outputs", help="Output directory"
    )
    parser.add_argument(
        "--no-pdf", action="store_true", help="Skip PDF report generation"
    )
    parser.add_argument(
        "--reuse-extractions",
        action="store_true",
        help="Revalidate existing extraction JSON without calling Ollama",
    )
    return parser


def main() -> int:
    args = _parser().parse_args()
    try:
        run_pipeline(
            args.pdfs,
            args.output,
            create_pdf=not args.no_pdf,
            reuse_extractions=args.reuse_extractions,
        )
    except (ValueError, FileNotFoundError, OllamaError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print(f"Completed. Results written to {Path(args.output).resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
