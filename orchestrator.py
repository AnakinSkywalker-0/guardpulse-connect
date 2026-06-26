"""
orchestrator.py
GuardPulse Swarm Orchestrator — Phase 2.

CHANGED: Replaced direct ollama.chat() with Gemini Flash via utils.call_llm().

Score formula:
  guardpulse_score = (legal_score * 0.50) +
                     (tech_score  * 0.35) +
                     (critic_bonus * 0.15)

  critic_bonus = 100 * (1 - hallucination_rate)
  Any CRITICAL security finding hard-caps final score at 55.

Badge thresholds:
  >= 80  → ENTERPRISE_READY
  60-79  → CONDITIONAL
  < 60   → NOT_READY
"""

import os
import sys
import json
from rich import print
from rich.console import Console
from rich.table import Table

from models import GuardPulseReport, BadgeStatus
from agents.auditor_agent import AuditorAgent
from agents.tech_agent import TechArchitectAgent
from agents.critic_agent import CriticAgent
from agents.utils import call_llm          # for structured JSON exec summary

console = Console()


def _load_document(path: str) -> str:
    if path.endswith(".pdf"):
        import pdfplumber
        with pdfplumber.open(path) as pdf:
            return "\n\n".join(p.extract_text() or "" for p in pdf.pages)
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.read()


def _compute_score(legal: float, tech: float, h_rate: float) -> tuple[float, BadgeStatus]:
    critic_bonus = round(100 * (1 - h_rate), 1)
    raw   = (legal * 0.50) + (tech * 0.35) + (critic_bonus * 0.15)
    score = round(min(100.0, max(0.0, raw)), 1)
    badge = (
        BadgeStatus.AWARDED     if score >= 80 else
        BadgeStatus.CONDITIONAL if score >= 60 else
        BadgeStatus.NOT_AWARDED
    )
    return score, badge


def _executive_summary(report: GuardPulseReport) -> tuple[str, list[str], list[str], list[str]]:
    """Generate exec summary using Gemini Flash."""

    fails     = [c for c in report.legal_audit.clauses    if c.verdict.value == "FAIL"]
    criticals = [f for f in report.tech_audit.security_findings if f.severity.value == "CRITICAL"]
    highs     = [f for f in report.tech_audit.security_findings if f.severity.value == "HIGH"]
    pii_crit  = [p for p in report.legal_audit.pii_findings     if p.risk_level.value == "CRITICAL"]

    passed = [c for c in report.legal_audit.clauses if c.verdict.value == "PASS"]

    prompt = f"""You are a senior enterprise risk advisor writing a board-level compliance summary.

STARTUP: {report.startup_name}
GuardPulse Score: {report.guardpulse_score}/100
Badge: {report.badge.value}

Legal Score : {report.legal_score}/100
Tech Score  : {report.tech_score}/100
Hallucination Rate: {report.critic_result.hallucination_rate:.1%}

Legal PASSED  : {[c.clause_ref+": "+c.clause_summary for c in passed[:4]]}
Legal FAILED  : {[c.clause_ref+": "+c.clause_summary for c in fails[:4]]}
Critical tech : {[f.description for f in criticals]}
High tech     : {[f.description for f in highs[:2]]}
Critical PII  : {[p.pii_type for p in pii_crit]}

STRICT RULES:
1. top_strengths must ONLY reference things in the PASSED list above.
2. Do NOT invent strengths not evidenced by the audit data.
3. top_risks must reference actual FAILED clauses or CRITICAL/HIGH findings.
4. Write for a Fortune 500 CTO. Be direct and factual.

Return a JSON object with exactly these fields:
- executive_summary: 3 sentences — overall readiness, biggest risk, recommendation
- top_risks: array of exactly 3 strings — highest-priority risks for an enterprise buyer
- top_strengths: array of exactly 3 strings — only from PASSED clauses above
- next_steps: array of 4-5 specific actions before a pilot

Return ONLY the JSON object. No markdown.
"""
    raw = call_llm("", prompt)
    try:
        r = json.loads(raw)
        return (
            r.get("executive_summary", "Audit complete."),
            r.get("top_risks",         ["Review audit details"]),
            r.get("top_strengths",     ["Review audit details"]),
            r.get("next_steps",        ["Review recommendations"]),
        )
    except Exception:
        return (
            f"GuardPulse Score: {report.guardpulse_score}/100. Badge: {report.badge.value}.",
            ["Review legal audit", "Review tech audit", "Address critical findings"],
            ["Audit completed",    "RAG-grounded analysis", "Multi-law coverage"],
            ["Fix failed clauses", "Address security findings", "Re-audit"],
        )


def run_swarm(
    startup_name: str,
    doc_path:     str,
    asset_paths:  list[str] | None = None,
) -> GuardPulseReport:
    print(f"\n[bold green]{'━'*50}[/bold green]")
    print(f"[bold green]  GuardPulse Swarm v2.0 — Starting[/bold green]")
    print(f"[bold green]{'━'*50}[/bold green]")
    print(f"  Startup  : {startup_name}")
    print(f"  Document : {doc_path}")

    if not os.path.exists(doc_path):
        print(f"[red]File not found: {doc_path}[/red]")
        sys.exit(1)

    asset_paths = asset_paths or [doc_path]
    doc_text    = _load_document(doc_path)
    doc_name    = os.path.basename(doc_path)
    print(f"  Loaded   : {len(doc_text):,} chars\n")

    # ── Agent 1: Auditor ──────────────────────────────────────────────────────
    legal_audit = AuditorAgent().run(doc_text, doc_name)

    # ── Agent 2: Tech Architect ───────────────────────────────────────────────
    tech_audit = TechArchitectAgent().run(asset_paths)

    # ── Agent 3: Critic ───────────────────────────────────────────────────────
    critic_result = CriticAgent().run(legal_audit)

    # ── Merge scores ──────────────────────────────────────────────────────────
    critic_penalty = round(critic_result.hallucination_rate * 100, 1)
    score, badge   = _compute_score(
        legal_audit.legal_score,
        tech_audit.tech_score,
        critic_result.hallucination_rate,
    )

    # Hard cap on critical security finding
    if any(f.severity.value == "CRITICAL" for f in tech_audit.security_findings):
        score = min(score, 55.0)
        badge = BadgeStatus.NOT_AWARDED if score < 60 else BadgeStatus.CONDITIONAL

    print(f"\n[bold]Swarm complete. Computing final score...[/bold]")
    print(f"  Legal score    : {legal_audit.legal_score}/100")
    print(f"  Tech score     : {tech_audit.tech_score}/100")
    print(f"  Critic penalty : -{critic_penalty} pts")
    print(f"  [bold]GuardPulse score: {score}/100[/bold]")
    print(f"  [bold]Badge: {badge.value}[/bold]")

    # Build partial report for exec summary
    partial = GuardPulseReport(
        startup_name      = startup_name,
        document_audited  = doc_name,
        legal_score       = legal_audit.legal_score,
        tech_score        = tech_audit.tech_score,
        critic_penalty    = critic_penalty,
        guardpulse_score  = score,
        badge             = badge,
        legal_audit       = legal_audit,
        tech_audit        = tech_audit,
        critic_result     = critic_result,
        executive_summary = "",
        top_risks         = [],
        top_strengths     = [],
        next_steps        = [],
    )

    print(f"\n  Generating executive summary...")
    summary, risks, strengths, steps = _executive_summary(partial)

    return GuardPulseReport(
        **{**partial.model_dump(),
           "executive_summary": summary,
           "top_risks":         risks,
           "top_strengths":     strengths,
           "next_steps":        steps,
        }
    )


def print_report(r: GuardPulseReport):
    badge_color = "green"  if r.badge == BadgeStatus.AWARDED     else \
                  "yellow" if r.badge == BadgeStatus.CONDITIONAL else "red"
    score_color = "green"  if r.guardpulse_score >= 80 else \
                  "yellow" if r.guardpulse_score >= 60 else "red"

    print(f"\n[bold]{'━'*52}[/bold]")
    print(f"[bold]       GUARDPULSE ENTERPRISE REPORT v2.0       [/bold]")
    print(f"[bold]{'━'*52}[/bold]")
    print(f"  Startup  : [bold]{r.startup_name}[/bold]")
    print(f"  Document : {r.document_audited}")
    print(f"  Score    : [{score_color}][bold]{r.guardpulse_score}/100[/bold][/{score_color}]")
    print(f"  Badge    : [{badge_color}][bold]{r.badge.value}[/bold][/{badge_color}]")
    print(f"\n  Legal : {r.legal_score}/100  |  Tech : {r.tech_score}/100  |  Hallucinations : {r.critic_result.hallucination_rate:.1%}")

    print(f"\n[bold cyan]Executive Summary[/bold cyan]")
    print(f"  {r.executive_summary}")

    print(f"\n[bold cyan]Top Risks[/bold cyan]")
    for i, risk in enumerate(r.top_risks, 1):
        print(f"  [red]{i}.[/red] {risk}")

    print(f"\n[bold cyan]Top Strengths[/bold cyan]")
    for i, s in enumerate(r.top_strengths, 1):
        print(f"  [green]{i}.[/green] {s}")

    print(f"\n[bold cyan]Next Steps Before Pilot[/bold cyan]")
    for i, step in enumerate(r.next_steps, 1):
        print(f"  [bold]{i}.[/bold] {step}")

    if r.legal_audit.clauses:
        print(f"\n[bold cyan]Legal Clauses ({len(r.legal_audit.clauses)})[/bold cyan]")
        t = Table(show_header=True, header_style="bold", box=None)
        t.add_column("Verdict",  width=14)
        t.add_column("Clause",   width=16)
        t.add_column("Summary",  width=40)
        t.add_column("Conf.",    width=5)
        for c in r.legal_audit.clauses:
            color = "green" if c.verdict.value == "PASS" else \
                    "red"   if c.verdict.value == "FAIL" else "yellow"
            t.add_row(
                f"[{color}]{c.verdict.value}[/{color}]",
                c.clause_ref, c.clause_summary, str(round(c.confidence, 1))
            )
        console.print(t)

    if r.tech_audit.security_findings:
        print(f"\n[bold cyan]Security Findings ({len(r.tech_audit.security_findings)})[/bold cyan]")
        t = Table(show_header=True, header_style="bold", box=None)
        t.add_column("Severity",    width=10)
        t.add_column("Type",        width=26)
        t.add_column("Description", width=40)
        for f in r.tech_audit.security_findings:
            color = "red" if f.severity.value in ("CRITICAL", "HIGH") else "yellow"
            t.add_row(
                f"[{color}]{f.severity.value}[/{color}]",
                f.finding_type, f.description
            )
        console.print(t)

    print(f"\n[bold cyan]Critic Report[/bold cyan]")
    print(f"  Verdict          : [bold]{r.critic_result.critic_verdict}[/bold]")
    print(f"  Claims checked   : {r.critic_result.total_claims_checked}")
    print(f"  Hallucination    : {r.critic_result.hallucination_rate:.1%}")
    if r.critic_result.invalid_claims > 0:
        print(f"  [yellow]Corrections:[/yellow]")
        for c in r.critic_result.citation_checks:
            if not c.is_valid and c.correction:
                print(f"    {c.citation_ref}: {c.correction}")