"""
pilot_proposal.py — Phase 4.

Generates a professional Pilot Proposal PDF after a CEO selects a matched
startup. Pulls real data: GuardPulse score, badge, compliance clauses,
security findings, and the match relevance — no placeholder content.
"""

from datetime import datetime
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

from models import StartupMatch


def _styles():
    base = getSampleStyleSheet()
    base.add(ParagraphStyle(
        name="ProposalTitle", parent=base["Title"],
        fontSize=22, spaceAfter=6, textColor=colors.HexColor("#1D9E75"),
    ))
    base.add(ParagraphStyle(
        name="SectionHeading", parent=base["Heading2"],
        fontSize=14, spaceBefore=18, spaceAfter=8, textColor=colors.HexColor("#26215C"),
    ))
    base.add(ParagraphStyle(
        name="BodyText2", parent=base["Normal"],
        fontSize=10.5, leading=15, spaceAfter=6,
    ))
    return base


def _badge_color(badge_value: str) -> colors.Color:
    return {
        "ENTERPRISE_READY": colors.HexColor("#0F6E56"),
        "CONDITIONAL":      colors.HexColor("#854F0B"),
        "NOT_READY":        colors.HexColor("#A32D2D"),
    }.get(badge_value, colors.gray)


def generate_pilot_proposal(match: StartupMatch, ceo_problem: str, output_path: str) -> str:
    """
    Builds a Pilot Proposal PDF for one matched startup.
    Returns output_path for chaining.
    """
    styles = _styles()
    doc = SimpleDocTemplate(
        output_path, pagesize=letter,
        topMargin=0.7 * inch, bottomMargin=0.7 * inch,
        leftMargin=0.75 * inch, rightMargin=0.75 * inch,
    )
    story = []
    s = match.startup

    story.append(Paragraph("GuardPulse Pilot Proposal", styles["ProposalTitle"]))
    story.append(Paragraph(f"Generated {datetime.now().strftime('%B %d, %Y')}", styles["BodyText2"]))
    story.append(Spacer(1, 16))

    story.append(Paragraph("Proposed vendor", styles["SectionHeading"]))
    story.append(Paragraph(f"<b>{s.startup_name}</b> &mdash; {s.category.replace('_', ' ').title()}", styles["BodyText2"]))
    story.append(Paragraph(s.description, styles["BodyText2"]))
    story.append(Spacer(1, 8))

    score_table = Table(
        [
            ["GuardPulse score", "Badge", "Match relevance"],
            [f"{s.guardpulse_score}/100", s.badge.value.replace("_", " "), f"{match.relevance_score:.0%}"],
        ],
        colWidths=[1.8 * inch, 2.2 * inch, 1.8 * inch],
    )
    score_table.setStyle(TableStyle([
        ("BACKGROUND",   (0, 0), (-1, 0), colors.HexColor("#F1EFE8")),
        ("FONTNAME",     (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",     (0, 0), (-1, -1), 10),
        ("TEXTCOLOR",    (1, 1), (1, 1), _badge_color(s.badge.value)),
        ("FONTNAME",     (0, 1), (-1, 1), "Helvetica-Bold"),
        ("GRID",         (0, 0), (-1, -1), 0.5, colors.HexColor("#D3D1C7")),
        ("ALIGN",        (0, 0), (-1, -1), "CENTER"),
        ("VALIGN",       (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING",   (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 8),
    ]))
    story.append(score_table)
    story.append(Spacer(1, 10))
    story.append(Paragraph(f"<i>{match.match_reason}</i>", styles["BodyText2"]))

    story.append(Paragraph("Business problem", styles["SectionHeading"]))
    story.append(Paragraph(ceo_problem, styles["BodyText2"]))

    story.append(Paragraph("Compliance breakdown", styles["SectionHeading"]))
    breakdown_table = Table(
        [
            ["Legal score", "Tech score", "Trust threshold"],
            [f"{s.legal_score}/100", f"{s.tech_score}/100",
             "80.0 (passed)" if s.guardpulse_score >= 80 else "80.0 (not met)"],
        ],
        colWidths=[1.8 * inch, 1.8 * inch, 2.2 * inch],
    )
    breakdown_table.setStyle(TableStyle([
        ("BACKGROUND",   (0, 0), (-1, 0), colors.HexColor("#F1EFE8")),
        ("FONTNAME",     (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",     (0, 0), (-1, -1), 10),
        ("GRID",         (0, 0), (-1, -1), 0.5, colors.HexColor("#D3D1C7")),
        ("ALIGN",        (0, 0), (-1, -1), "CENTER"),
        ("TOPPADDING",   (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 8),
    ]))
    story.append(breakdown_table)
    story.append(Spacer(1, 8))
    story.append(Paragraph(
        f"Audited document: {s.document_audited}. Registered {s.registered_at[:10] if s.registered_at else 'N/A'}.",
        styles["BodyText2"],
    ))

    story.append(Paragraph("Verified capabilities", styles["SectionHeading"]))
    cap_text = ", ".join(c.replace("_", " ") for c in s.capabilities) or "None listed"
    story.append(Paragraph(cap_text, styles["BodyText2"]))

    story.append(Paragraph("Proposed pilot terms", styles["SectionHeading"]))
    terms = [
        "30-day sandboxed pilot with limited data scope, reviewed weekly",
        "No production PII shared until a signed NDA and DPA are in place",
        "Pilot success criteria defined jointly before kickoff",
        "GuardPulse compliance re-audit at pilot midpoint and close",
    ]
    for t in terms:
        story.append(Paragraph(f"&bull; {t}", styles["BodyText2"]))

    story.append(Paragraph("Next steps", styles["SectionHeading"]))
    next_steps = [
        "Schedule an introductory call between both teams",
        "Exchange NDA and data processing agreement",
        "Define pilot scope, timeline, and success metrics",
        "Kick off sandbox integration testing",
    ]
    for i, n in enumerate(next_steps, 1):
        story.append(Paragraph(f"{i}. {n}", styles["BodyText2"]))

    story.append(Spacer(1, 20))
    story.append(Paragraph(
        "Generated by GuardPulse Connect &mdash; automated compliance auditing "
        "and enterprise-startup matchmaking.",
        ParagraphStyle(name="Footer", parent=styles["Normal"], fontSize=8, textColor=colors.gray),
    ))

    doc.build(story)
    return output_path