"""
Renders a generator's dict output into a PDF.
Kept intentionally simple — one table-based layout that works for
all four report types rather than four bespoke templates.
"""
from io import BytesIO
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet


def write_pdf(report_type: str, data: dict) -> bytes:
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    styles = getSampleStyleSheet()
    story = []

    story.append(Paragraph(f"IntelliWatch — {report_type.replace('_', ' ').title()}", styles["Title"]))
    story.append(Paragraph(f"{data.get('date_start', '')} to {data.get('date_end', '')}", styles["Normal"]))
    story.append(Spacer(1, 20))

    summary_rows = [[k.replace("_", " ").title(), str(v)]
                    for k, v in data.items()
                    if not isinstance(v, (list, dict)) and k not in ("report_type",)]

    if summary_rows:
        table = Table([["Metric", "Value"]] + summary_rows, colWidths=[250, 250])
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1B2A4A")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
        ]))
        story.append(table)

    doc.build(story)
    return buffer.getvalue()