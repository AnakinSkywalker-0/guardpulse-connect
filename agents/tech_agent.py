"""
agents/tech_agent.py — Tech Architect Agent, Phase 2.
Scans technical assets for security risks and good practices.

FIX 1: _boolean_checks() prompt now explicitly says "true or false" not YES/NO
        — Groq/Llama was returning YES/NO which breaks json.loads().
FIX 2: Summary call now uses call_llm_text() instead of call_llm()
        — summary is plain text, not JSON, so JSON validation was always failing.
FIX 3: Dedup applied to findings — prevents duplicate findings.
"""

import os
import json
from dotenv import load_dotenv
from rich import print
from models import TechAuditResult, SecurityFinding, RiskLevel
from agents.utils import call_ollama, call_llm_text

load_dotenv()
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", os.getenv("GROQ_MODEL", "llama3.2"))

SEVERITY_RANK = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1}


def _dedup_findings(findings: list[SecurityFinding]) -> list[SecurityFinding]:
    """Remove duplicate findings — keep highest severity per type+description."""
    seen: dict[str, SecurityFinding] = {}
    for f in findings:
        key = f"{f.finding_type}::{f.description[:60]}"
        if key not in seen:
            seen[key] = f
        else:
            existing_rank = SEVERITY_RANK.get(seen[key].severity.value, 1)
            new_rank      = SEVERITY_RANK.get(f.severity.value, 1)
            if new_rank > existing_rank:
                seen[key] = f
    deduped = list(seen.values())
    removed = len(findings) - len(deduped)
    if removed:
        print(f"  [yellow]Deduped {removed} duplicate finding(s)[/yellow]")
    return deduped


class TechArchitectAgent:
    def __init__(self):
        self.name  = "TechArchitectAgent"
        self.model = OLLAMA_MODEL

    def _load(self, path: str) -> str:
        if path.endswith(".pdf"):
            import pdfplumber
            with pdfplumber.open(path) as pdf:
                return "\n\n".join(p.extract_text() or "" for p in pdf.pages)
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()

    def _find_risks(self, text: str) -> list[SecurityFinding]:
        raw = call_ollama(self.model, f"""Review this technical document for security risks.

DOCUMENT: {text[:4000]}

Return a JSON array of security issues. Each item must have exactly these fields:
- finding_type: one of NO_ENCRYPTION, WEAK_AUTH, PII_LOGGED, NO_RATE_LIMITING, BROAD_DATA_COLLECTION, NO_DELETION_POLICY, INSECURE_STORAGE, MISSING_CONSENT
- severity: exactly one of LOW, MEDIUM, HIGH, CRITICAL
- location: where in the document (max 50 chars)
- description: what the risk is (max 100 chars)
- recommendation: how to fix it (max 100 chars)

Return [] if no risks found.
Return ONLY the JSON array. No explanation. No markdown.
""")
        try:
            out = []
            for i in json.loads(raw):
                try:
                    out.append(SecurityFinding(
                        finding_type   = i.get("finding_type", "UNKNOWN"),
                        severity       = RiskLevel(i.get("severity", "MEDIUM")),
                        location       = str(i.get("location", ""))[:60],
                        description    = str(i.get("description", ""))[:120],
                        recommendation = str(i.get("recommendation", "Review and fix"))[:120],
                    ))
                except Exception:
                    continue
            return _dedup_findings(out)
        except Exception:
            return []

    def _boolean_checks(self, text: str) -> dict:
        """
        FIX: Explicitly instructs model to use JSON true/false (not YES/NO).
        Groq's Llama was returning YES/NO which is invalid JSON.
        """
        raw = call_ollama(self.model, f"""Answer these questions about the document below.

DOCUMENT: {text[:3000]}

Return a JSON object with exactly these four fields.
Use JSON boolean values true or false (lowercase, no quotes):
- api_documented: true if there is API documentation, false otherwise
- encryption_present: true if TLS, HTTPS, or AES encryption is mentioned, false otherwise
- auth_present: true if authentication or login is implemented, false otherwise
- data_minimisation: true if only necessary data is collected, false otherwise

Example of correct format:
{{"api_documented": false, "encryption_present": true, "auth_present": false, "data_minimisation": false}}

Return ONLY the JSON object. No explanation. No markdown.
""")
        defaults = {
            "api_documented":     False,
            "encryption_present": False,
            "auth_present":       False,
            "data_minimisation":  False,
        }
        try:
            r = json.loads(raw)
            for k in defaults:
                v = r.get(k, False)
                # Handle both proper booleans and string YES/NO as fallback
                if isinstance(v, bool):
                    defaults[k] = v
                else:
                    defaults[k] = str(v).lower() in ("yes", "true", "1")
            return defaults
        except Exception:
            return defaults

    def _score(self, findings: list[SecurityFinding], flags: dict) -> float:
        score = 100.0
        deductions = {"CRITICAL": 30, "HIGH": 15, "MEDIUM": 8, "LOW": 3}
        for f in findings:
            score -= deductions.get(f.severity.value, 0)
        score += sum(3 for v in flags.values() if v)
        if any(f.severity.value == "CRITICAL" for f in findings):
            score = min(score, 40.0)
        return max(0.0, min(100.0, round(score, 1)))

    def run(self, asset_paths: list[str]) -> TechAuditResult:
        print(f"\n  [bold cyan][{self.name}] Starting...[/bold cyan]")
        combined = ""
        for path in asset_paths:
            try:
                text      = self._load(path)
                combined += f"\n\nFILE: {path}\n{text}"
                print(f"  [{self.name}] Loaded: {path} ({len(text):,} chars)")
            except Exception as e:
                print(f"  [{self.name}] [yellow]Could not load {path}: {e}[/yellow]")

        if not combined.strip():
            return TechAuditResult(
                target_document="none", security_findings=[], tech_score=0.0,
                api_documented=False, encryption_present=False,
                auth_present=False, data_minimisation=False,
                summary="No assets provided.", recommendations=[],
            )

        findings = self._find_risks(combined)
        flags    = self._boolean_checks(combined)
        score    = self._score(findings, flags)

        by_sev = {}
        for f in findings:
            by_sev[f.severity.value] = by_sev.get(f.severity.value, 0) + 1
        print(f"  [{self.name}] Findings: {by_sev} | Flags: {flags}")
        print(f"  [{self.name}] Tech score: [bold]{score}/100[/bold]")

        recs = [
            f.recommendation for f in sorted(
                findings,
                key=lambda x: SEVERITY_RANK.get(x.severity.value, 0),
                reverse=True
            )[:5]
        ]

        # FIX: use call_llm_text — summary is plain text, not JSON
        summary = call_llm_text(self.model, f"""Write a 2-sentence security summary for a startup founder.
Score: {score}/100
Risks found: {[f.description for f in findings[:3]]}
Good practices present: {[k for k, v in flags.items() if v]}
Be direct and factual. Plain text only.""")

        if not summary:
            critical = [f.description for f in findings if f.severity.value == "CRITICAL"]
            summary  = (
                f"Tech security score is {score}/100. "
                + (f"Critical issues: {', '.join(critical)}." if critical else
                   f"{len(findings)} security findings require attention.")
            )

        return TechAuditResult(
            target_document    = ", ".join(asset_paths),
            security_findings  = findings,
            tech_score         = score,
            api_documented     = flags["api_documented"],
            encryption_present = flags["encryption_present"],
            auth_present       = flags["auth_present"],
            data_minimisation  = flags["data_minimisation"],
            summary            = summary.strip(),
            recommendations    = recs,
        )
