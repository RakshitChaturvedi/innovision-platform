"""
Renders a generator's dict output into a PDF.
Scalar fields go into a summary table.
Dict values get a sub-table section.
List values (e.g. incidents[]) get a row-per-item section,
  with each item's scalar fields as columns.
"""
from io import BytesIO
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet

_HEADER_STYLE = TableStyle([
    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1B2A4A")),
    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
    ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
    ("FONTSIZE", (0, 0), (-1, -1), 9),
    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F0F4FA")]),
])

_SKIP_KEYS = {"report_type"}


def _scalar_table(rows: list[list], col_widths=(250, 250)) -> Table:
    t = Table(rows, colWidths=list(col_widths))
    t.setStyle(_HEADER_STYLE)
    return t


def _section_heading(label: str, styles) -> Paragraph:
    return Paragraph(f"<b>{label.replace('_', ' ').title()}</b>", styles["Heading3"])


def write_pdf(report_type: str, data: dict) -> bytes:
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=36, rightMargin=36)
    styles = getSampleStyleSheet()
    story = []

    # Title
    story.append(
        Paragraph(
            f"IntelliWatch — {report_type.replace('_', ' ').title()}",
            styles["Title"],
        )
    )
    story.append(
        Paragraph(
            f"{data.get('date_start', '')} to {data.get('date_end', '')}",
            styles["Normal"],
        )
    )
    story.append(Spacer(1, 16))

    # Scalar summary table
    scalar_rows = [
        [k.replace("_", " ").title(), str(v)]
        for k, v in data.items()
        if not isinstance(v, (list, dict)) and k not in _SKIP_KEYS
    ]
    if scalar_rows:
        story.append(_scalar_table([["Metric", "Value"]] + scalar_rows))
        story.append(Spacer(1, 12))

    # Dict sections (e.g. by_source_uc, by_severity)
    for key, value in data.items():
        if key in _SKIP_KEYS or not isinstance(value, dict):
            continue
        story.append(_section_heading(key, styles))
        rows = [[k2.replace("_", " ").title(), str(v2)] for k2, v2 in value.items()]
        if rows:
            story.append(_scalar_table([["Key", "Value"]] + rows))
        story.append(Spacer(1, 10))

    # List sections (e.g. incidents, cameras)
    for key, value in data.items():
        if key in _SKIP_KEYS or not isinstance(value, list) or not value:
            continue
        story.append(_section_heading(key, styles))

        # Collect scalar columns from first item
        first = value[0] if isinstance(value[0], dict) else {}
        col_keys = [k for k, v in first.items() if not isinstance(v, (list, dict))][:8]

        if col_keys:
            header = [k.replace("_", " ").title() for k in col_keys]
            item_rows = []
            for item in value:
                if isinstance(item, dict):
                    item_rows.append([str(item.get(k, "")) for k in col_keys])
                else:
                    item_rows.append([str(item)])

            col_w = min(70, int(520 / max(len(col_keys), 1)))
            t = Table(
                [header] + item_rows,
                colWidths=[col_w] * len(col_keys),
                repeatRows=1,
            )
            t.setStyle(_HEADER_STYLE)
            story.append(t)
        else:
            # Non-dict list — render as plain text
            for item in value:
                story.append(Paragraph(str(item), styles["Normal"]))

        story.append(Spacer(1, 10))

    doc.build(story)
    return buffer.getvalue()
