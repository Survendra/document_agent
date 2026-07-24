"""Generate plainly labeled, non-official PDFs for pipeline testing."""

from __future__ import annotations

from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas


STUDENT = {
    "university": "XYZ University",
    "course": "B.Tech Computer Science & Engineering",
    "name": "Rahul Sharma",
    "roll_number": "CSE230145",
    "registration_number": "23BTCS0145",
}

SEMESTERS = [
    {
        "semester": "I",
        "academic_year": "2023-24",
        "subjects": [
            ("CS101", "Programming Fundamentals", 86),
            ("MA101", "Engineering Mathematics-I", 81),
            ("PH101", "Engineering Physics", 79),
            ("EE101", "Basic Electrical Engineering", 84),
            ("HS101", "English Communication", 90),
        ],
        "total": "420 / 500",
        "percentage": "84.00%",
        "sgpa": "8.72",
    },
    {
        "semester": "II",
        "academic_year": "2023-24",
        "subjects": [
            ("CS201", "Data Structures", 88),
            ("MA201", "Engineering Mathematics-II", 76),
            ("EC201", "Digital Electronics", 82),
            ("CS202", "Object Oriented Programming", 91),
            ("EVS201", "Environmental Studies", 87),
        ],
        "total": "424 / 500",
        "percentage": "84.80%",
        "sgpa": "8.84",
    },
    {
        "semester": "III",
        "academic_year": "2024-25",
        "subjects": [
            ("CS301", "Database Management Systems", 85),
            ("CS302", "Operating Systems", 82),
            ("CS303", "Computer Networks", 90),
            ("CS304", "Discrete Mathematics", 78),
            ("CS305", "Python Programming", 94),
        ],
        "total": "429 / 500",
        "percentage": "85.80%",
        "sgpa": "8.91",
    },
    {
        "semester": "IV",
        "academic_year": "2024-25",
        "subjects": [
            ("CS401", "Software Engineering", 89),
            ("CS402", "Design & Analysis of Algorithms", 86),
            ("CS403", "Web Technologies", 93),
            ("CS404", "Computer Organization", 81),
            ("CS405", "Probability & Statistics", 84),
        ],
        "total": "433 / 500",
        "percentage": "86.60%",
        "sgpa": "9.02",
    },
]


def centered(pdf: canvas.Canvas, text: str, y: float, font: str, size: int) -> None:
    pdf.setFont(font, size)
    x = (A4[0] - stringWidth(text, font, size)) / 2
    pdf.drawString(x, y, text)


def create_pdf(output: Path, semester: dict) -> None:
    pdf = canvas.Canvas(str(output), pagesize=A4)
    width, height = A4
    pdf.setTitle(f"Unofficial test data - Semester {semester['semester']}")

    pdf.setFillColorRGB(0.7, 0.0, 0.0)
    centered(
        pdf,
        "UNOFFICIAL SAMPLE - TEST DATA ONLY - NOT A UNIVERSITY RECORD",
        height - 36,
        "Helvetica-Bold",
        10,
    )
    pdf.setFillColorRGB(0, 0, 0)
    centered(pdf, STUDENT["university"], height - 72, "Helvetica-Bold", 16)
    centered(pdf, "Semester Examination Result", height - 94, "Helvetica", 13)

    lines = [
        ("University Name", STUDENT["university"]),
        ("Course", STUDENT["course"]),
        ("Semester", semester["semester"]),
        ("Academic Year", semester["academic_year"]),
        ("Student Name", STUDENT["name"]),
        ("Roll Number", STUDENT["roll_number"]),
        ("Registration No", STUDENT["registration_number"]),
    ]
    y = height - 135
    pdf.setFont("Helvetica", 10)
    for label, value in lines:
        pdf.drawString(55, y, f"{label}:")
        pdf.drawString(165, y, str(value))
        y -= 18

    y -= 12
    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawString(55, y, "Subject Code")
    pdf.drawString(145, y, "Subject Name")
    pdf.drawRightString(width - 55, y, "Marks")
    y -= 8
    pdf.line(55, y, width - 55, y)
    y -= 18

    pdf.setFont("Helvetica", 10)
    for code, name, marks in semester["subjects"]:
        pdf.drawString(55, y, code)
        pdf.drawString(145, y, name)
        pdf.drawRightString(width - 55, y, str(marks))
        y -= 20

    y -= 6
    pdf.line(55, y, width - 55, y)
    y -= 22
    summary = [
        ("Total Marks", semester["total"]),
        ("Percentage", semester["percentage"]),
        ("SGPA", semester["sgpa"]),
        ("Result", "PASS"),
    ]
    for label, value in summary:
        pdf.drawString(55, y, f"{label}:")
        pdf.drawString(165, y, str(value))
        y -= 18

    pdf.setFillColorRGB(0.35, 0.35, 0.35)
    centered(
        pdf,
        "Generated solely to test document extraction; no signature, seal, or credential.",
        30,
        "Helvetica-Oblique",
        8,
    )
    pdf.save()


def main() -> None:
    output_dir = Path(__file__).parents[1] / "sample_docs"
    output_dir.mkdir(parents=True, exist_ok=True)
    for index, semester in enumerate(SEMESTERS, start=1):
        create_pdf(output_dir / f"semester_{index}.pdf", semester)


if __name__ == "__main__":
    main()
