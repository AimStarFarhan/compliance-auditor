"""PDF compliance report generator (ReportLab)."""
import io
from datetime import datetime, timezone

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.models import AuditReport

STATUS_COLORS = {
    "pass": colors.HexColor("#2e7d32"),
    "fail": colors.HexColor("#c62828"),
    "needs_review": colors.HexColor("#f9a825"),
}


def generate_pdf(report: AuditReport) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        title=f"Compliance Audit — {report.source_file}",
    )
    styles = getSampleStyleSheet()
    small = ParagraphStyle("small", parent=styles["BodyText"], fontSize=7.5, leading=9.5)
    cell = ParagraphStyle("cell", parent=styles["BodyText"], fontSize=8, leading=10)
    cellb = ParagraphStyle("cellb", parent=cell, fontName="Helvetica-Bold")

    story: list = []

    # Title block
    story.append(Paragraph("Quantum Forgers — Compliance Auditor", styles["Title"]))
    story.append(Paragraph("Network Configuration Compliance Report (SIH26155 prototype)", styles["Normal"]))
    story.append(Spacer(1, 6 * mm))
    story.append(Paragraph(f"<b>Source file:</b> {report.source_file}", styles["Normal"]))
    story.append(Paragraph(f"<b>Device type:</b> {report.device_type}", styles["Normal"]))
    story.append(Paragraph(f"<b>Hostname:</b> {report.hostname or 'unknown'}", styles["Normal"]))
    story.append(
        Paragraph(
            datetime.now(timezone.utc).strftime("<b>Generated (UTC):</b> %Y-%m-%d %H:%M:%S"),
            styles["Normal"],
        )
    )
    story.append(Spacer(1, 3 * mm))

    # Summary
    story.append(Paragraph(
        f"<b>Rules evaluated:</b> {report.total_rules} &nbsp;&nbsp; "
        f"<font color='#2e7d32'><b>Pass:</b> {report.passed}</font> &nbsp;&nbsp; "
        f"<font color='#c62828'><b>Fail:</b> {report.failed}</font> &nbsp;&nbsp; "
        f"<font color='#f9a825'><b>Needs review:</b> {report.needs_review}</font>",
        styles["Normal"],
    ))
    ai_count = sum(1 for u in report.unmapped_lines if u.status == "ai_suggested")
    confirmed_count = sum(1 for u in report.unmapped_lines if u.status == "human_confirmed")
    story.append(Spacer(1, 2 * mm))
    story.append(Paragraph(
        f"<b>Unmapped constructs:</b> {len(report.unmapped_lines)} "
        f"(AI-suggested: {ai_count}, human-confirmed: {confirmed_count})",
        styles["Normal"],
    ))
    story.append(Spacer(1, 5 * mm))

    # Findings table
    story.append(Paragraph("Findings", styles["Heading2"]))
    header = [Paragraph("Rule", cellb), Paragraph("CIS Section", cellb),
              Paragraph("Status", cellb), Paragraph("Sev", cellb),
              Paragraph("Remediation CLI", cellb), Paragraph("AI", cellb)]
    rows = [header]
    for f in report.findings:
        rows.append([
            Paragraph(f.rule_id, cell),
            Paragraph(f.cis_section, cell),
            Paragraph(f.status.upper(), cell),
            Paragraph(f.severity, cell),
            Paragraph(f.remediation_cli, cell),
            Paragraph("AI*" if f.influenced_by_ai_suggestion else ("HC*" if f.influenced_by_confirmed_mapping else ""), cell),
        ])
    t = Table(rows, colWidths=[18 * mm, 76 * mm, 18 * mm, 14 * mm, 42 * mm, 10 * mm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#263238")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#eceff1")]),
        *[("TEXTCOLOR", (2, i + 1), (2, i + 1), STATUS_COLORS.get(f.status, colors.black))
          for i, f in enumerate(report.findings)],
    ]))
    story.append(t)
    story.append(Spacer(1, 2 * mm))
    story.append(Paragraph(
        "AI* = finding touched by an AI-suggested (not yet human-confirmed) mapping. "
        "HC* = mapping previously confirmed by a human operator. "
        "AI suggestions are advisory only and never auto-applied.",
        small,
    ))
    story.append(Spacer(1, 6 * mm))

    # Unmapped lines table
    if report.unmapped_lines:
        story.append(Paragraph("Unmapped Constructs (Training Loop)", styles["Heading2"]))
        header = [Paragraph("Line #", cellb), Paragraph("Raw line", cellb),
                  Paragraph("Suggested category", cellb), Paragraph("Conf", cellb),
                  Paragraph("Status", cellb)]
        rows = [header]
        for u in report.unmapped_lines:
            rows.append([
                Paragraph(str(u.line_number), cell),
                Paragraph(u.raw_line, cell),
                Paragraph(u.suggested_category or "—", cell),
                Paragraph(f"{u.confidence:.2f}" if u.confidence is not None else "—", cell),
                Paragraph(u.status, cell),
            ])
        t = Table(rows, colWidths=[14 * mm, 90 * mm, 40 * mm, 14 * mm, 28 * mm])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#263238")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#eceff1")]),
        ]))
        story.append(t)

    story.append(Spacer(1, 6 * mm))
    story.append(Paragraph(
        "Remediation CLI commands are advisory text only. This tool performs no "
        "auto-remediation and no configuration push. Vendor support is extensible "
        "to new vendors via human-in-the-loop mapping.",
        small,
    ))

    doc.build(story)
    return buf.getvalue()
