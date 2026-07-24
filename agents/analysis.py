"""Conservative observations derived from the unified evidence."""

from __future__ import annotations

import re
from collections import defaultdict
from decimal import Decimal, InvalidOperation

from models.schemas import Observation, UnifiedRepresentation

METRIC_TERMS = {
    "amount",
    "balance",
    "cgpa",
    "credit",
    "debit",
    "expense",
    "gpa",
    "mark",
    "marks",
    "percentage",
    "score",
    "sgpa",
    "total",
}


def _key(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.casefold()).strip("_")


def _number(value: object) -> Decimal | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float, Decimal)):
        return Decimal(str(value))
    if not isinstance(value, str):
        return None
    ratio = re.match(r"\s*([+-]?\d+(?:\.\d+)?)\s*/", value)
    if ratio:
        return Decimal(ratio.group(1))
    cleaned = re.sub(r"[^0-9.+-]", "", value)
    if not cleaned or cleaned in {"+", "-", "."}:
        return None
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return None


class AnalysisAgent:
    def analyze(self, unified: UnifiedRepresentation) -> list[Observation]:
        observations: list[Observation] = []
        for name, field in unified.fields.items():
            if field.status == "verified":
                observations.append(
                    Observation(
                        statement=(
                            f"{name} is consistent across multiple documents."
                        ),
                        evidence=field.sources,
                        confidence="High",
                        inference=False,
                    )
                )

        numeric_fields: dict[str, list[tuple[Decimal, object, list]]] = defaultdict(list)
        display_names: dict[str, str] = {}
        for record in unified.records:
            for name, sourced in record.fields.items():
                number = _number(sourced.value)
                key = _key(name)
                tokens = set(key.split("_"))
                if (
                    number is not None
                    and sourced.sources
                    and tokens.intersection(METRIC_TERMS)
                ):
                    display_names.setdefault(key, name)
                    numeric_fields[key].append(
                        (number, sourced.value, sourced.sources)
                    )

        for key, values in numeric_fields.items():
            if len(values) < 2:
                continue
            highest = max(values, key=lambda item: item[0])
            lowest = min(values, key=lambda item: item[0])
            label = display_names[key]
            observations.append(
                Observation(
                    statement=f"Highest observed {label}: {highest[1]}.",
                    evidence=highest[2],
                    confidence="Medium",
                    inference=True,
                )
            )
            if lowest[0] != highest[0]:
                observations.append(
                    Observation(
                        statement=f"Lowest observed {label}: {lowest[1]}.",
                        evidence=lowest[2],
                        confidence="Medium",
                        inference=True,
                    )
                )

        semester_order = {
            "i": 1,
            "ii": 2,
            "iii": 3,
            "iv": 4,
            "v": 5,
            "vi": 6,
            "vii": 7,
            "viii": 8,
        }
        ordered_records = []
        for record in unified.records:
            semester = record.fields.get("semester")
            if semester is None:
                continue
            order = semester_order.get(str(semester.value).strip().casefold())
            if order is not None:
                ordered_records.append((order, semester.value, record))
        ordered_records.sort(key=lambda item: item[0])

        for metric in ("total_marks", "percentage", "sgpa"):
            trend = []
            for order, semester, record in ordered_records:
                sourced = record.fields.get(metric)
                number = _number(sourced.value) if sourced is not None else None
                if number is not None and sourced and sourced.sources:
                    trend.append(
                        (order, semester, number, sourced.value, sourced.sources)
                    )
            if len(trend) >= 2 and all(
                current[2] < following[2]
                for current, following in zip(trend, trend[1:])
            ):
                first, last = trend[0], trend[-1]
                observations.append(
                    Observation(
                        statement=(
                            f"{metric} increased across every available ordered "
                            f"semester, from {first[3]} in Semester {first[1]} to "
                            f"{last[3]} in Semester {last[1]}."
                        ),
                        evidence=[
                            source
                            for item in trend
                            for source in item[4]
                        ],
                        confidence="Medium",
                        inference=True,
                    )
                )

        subject_results = []
        for record in unified.records:
            subjects = record.fields.get("subjects")
            if subjects is None or not isinstance(subjects.value, list):
                continue
            for subject in subjects.value:
                if not isinstance(subject, dict):
                    continue
                marks = _number(subject.get("marks"))
                name = subject.get("name") or subject.get("subject_name")
                code = subject.get("code") or subject.get("subject_code")
                if marks is not None and name:
                    subject_results.append(
                        (marks, subject.get("marks"), name, code, subjects.sources)
                    )
        if subject_results:
            highest_subject = max(subject_results, key=lambda item: item[0])
            lowest_subject = min(subject_results, key=lambda item: item[0])
            observations.append(
                Observation(
                    statement=(
                        f"Highest subject mark: {highest_subject[1]} in "
                        f"{highest_subject[2]}"
                        f"{f' ({highest_subject[3]})' if highest_subject[3] else ''}."
                    ),
                    evidence=highest_subject[4],
                    confidence="Medium",
                    inference=True,
                )
            )
            if lowest_subject[0] != highest_subject[0]:
                observations.append(
                    Observation(
                        statement=(
                            f"Lowest subject mark: {lowest_subject[1]} in "
                            f"{lowest_subject[2]}"
                            f"{f' ({lowest_subject[3]})' if lowest_subject[3] else ''}."
                        ),
                        evidence=lowest_subject[4],
                        confidence="Medium",
                        inference=True,
                    )
                )
        return observations
