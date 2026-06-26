"""
compliance_agent.py
GuardPulse Phase 1 Compliance Agent.

Uses agents/utils.py (call_llm / call_llm_text) so it works with
Groq, OpenRouter, or Gemini — whichever key is in .env.
No direct google.generativeai import needed here.
"""

import os
import json
from dotenv import load_dotenv
from rich import print
from models import (
    ComplianceScorecard, ComplianceClause, PIIFinding,
    ComplianceVerdict, RiskLevel,
)
from vector_store import query
from agents.utils import call_llm

load_dotenv()

QUERIES_BY_LAW = {
    "DPDP_2023": [
        "consent requirements before collecting personal data",
        "rights of data principal access correction erasure",
        "obligations of data fiduciary privacy notice",
        "data breach notification requirements",
        "processing personal data of children",
        "grievance redressal mechanism complaints",
        "cross border data transfer restrictions",
        "exemptions to data protection obligations",
    ],
    "EU_AI_ACT_2024": [
        "prohibited AI practices unacceptable risk",
        "high risk AI system obligations requirements",
        "transparency obligations AI system users",
        "conformity assessment high risk AI",
        "data governance training data quality",
        "human oversight high risk AI systems",
        "general purpose AI model obligations",
        "penalties fines non compliance AI Act",
    ],
}

CLAUSES_BY_LAW = {
    "DPDP_2023": """Check ALL of these DPDP Act 2023 requirements:
1. Consent obtained before data collection (§6)
2. Privacy notice provided to users (§5)
3. Purpose of data collection clearly stated (§5)
4. User rights: access, correction, erasure (§11, §12, §13)
5. Grievance redressal mechanism exists (§13)
6. Data retention and deletion policy (§8)
7. Children data protection measures (§9)
8. Data breach notification process (§8)""",

    "EU_AI_ACT_2024": """Check ALL of these EU AI Act 2024 requirements:
1. AI system risk classification disclosed (Art. 6)
2. Prohibited AI practices absent (Art. 5)
3. Transparency obligations for AI interactions met (Art. 50)
4. Human oversight mechanisms described (Art. 14)
5. Data governance and quality measures stated (Art. 10)
6. Technical documentation available (Art. 11)
7. Accuracy and robustness measures described (Art. 15)
8. Post-market monitoring plan exists (Art. 72)""",
}


def _load_document(path: str) -> str:
    if path.endswith(".pdf"):
        import pdfplumber
        with pdfplumber.open(path) as pdf:
            return "\n\n".join(p.extract_text() or "" for p in pdf.pages)
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.read()


def _retrieve_legal_context(law_id: str) -> str:
    print("  Retrieving legal context from ChromaDB...")
    queries  = QUERIES_BY_LAW.get(law_id, QUERIES_BY_LAW["DPDP_2023"])
    contexts = []
    seen     = set()
    for question in queries:
        for r in query(question, top_k=2, law_id=law_id):
            if r.chunk_id not in seen:
                seen.add(r.chunk_id)
                contexts.append(f"[{r.law_id} §{r.section_number} — {r.section_title}]\n{r.text}")
    print(f"  Retrieved {len(contexts)} unique legal sections")
    return ("\n\n" + "─" * 60 + "\n\n").join(contexts)


def _detect_pii(text: str) -> list[PIIFinding]:
    print("  Running PII detection...")
    raw = call_llm("", f"""You are a data privacy expert. Find ALL personal data (PII) in this document.

DOCUMENT:
---
{text[:4000]}
---

Return a JSON array. Each item must have exactly these fields:
- pii_type: one of "NAME","EMAIL","PHONE","AADHAAR","PAN","ADDRESS","IP_ADDRESS","LOCATION","HEALTH_DATA","FINANCIAL_DATA","BIOMETRIC","DEVICE_ID","COOKIES","BROWSING_HISTORY","DATE_OF_BIRTH"
- context_snippet: the sentence where this PII appears (max 120 chars)
- risk_level: exactly one of "LOW","MEDIUM","HIGH","CRITICAL"
- relevant_law: e.g. "DPDP Act 2023 §2(t)"
- recommendation: one specific action to protect this data

Return ONLY the JSON array. No explanation. No markdown. If no PII found return [].
""")
    try:
        findings = []
        for item in json.loads(raw):
            try:
                findings.append(PIIFinding(
                    pii_type        = item.get("pii_type", "UNKNOWN"),
                    context_snippet = item.get("context_snippet", "")[:150],
                    risk_level      = RiskLevel(item.get("risk_level", "MEDIUM")),
                    relevant_law    = item.get("relevant_law", "DPDP Act 2023"),
                    recommendation  = item.get("recommendation", "Review and protect")
                ))
            except Exception:
                continue
        return findings
    except json.JSONDecodeError:
        print("  [yellow]PII detection: invalid JSON, skipping[/yellow]")
        return []


def _check_compliance(doc_text: str, legal_context: str, law_id: str) -> list[ComplianceClause]:
    print("  Running compliance check...")
    clause_instructions = CLAUSES_BY_LAW.get(law_id, CLAUSES_BY_LAW["DPDP_2023"])
    raw = call_llm("", f"""You are a legal compliance expert.

Audit the DOCUMENT strictly against the LEGAL REQUIREMENTS below.

LEGAL REQUIREMENTS FROM {law_id}:
{legal_context[:4000]}

DOCUMENT:
---
{doc_text[:3000]}
---

Return a JSON array. Each item must have exactly these fields:
- clause_ref: e.g. "DPDP 2023 §6" or "EU AI Act Art.5"
- clause_summary: plain English requirement (max 100 chars)
- verdict: exactly one of "PASS", "FAIL", "PARTIAL", "INCONCLUSIVE"
- evidence: exact quote or observation from the DOCUMENT (max 150 chars). If not found write "Not mentioned in document."
- confidence: number 0.0 to 1.0

{clause_instructions}

Return ONLY the JSON array. No explanation. No markdown.
""")
    try:
        clauses = []
        for item in json.loads(raw):
            try:
                clauses.append(ComplianceClause(
                    clause_ref     = item.get("clause_ref", "Unknown"),
                    clause_summary = item.get("clause_summary", "")[:100],
                    verdict        = ComplianceVerdict(item.get("verdict", "INCONCLUSIVE")),
                    evidence       = item.get("evidence", "")[:150],
                    confidence     = float(item.get("confidence", 0.5))
                ))
            except Exception:
                continue
        return clauses
    except json.JSONDecodeError:
        print("  [yellow]Compliance check: invalid JSON, skipping[/yellow]")
        return []


def _score(clauses: list[ComplianceClause]) -> tuple[float, ComplianceVerdict]:
    if not clauses:
        return 0.0, ComplianceVerdict.INCONCLUSIVE
    weights = {
        ComplianceVerdict.PASS:         1.0,
        ComplianceVerdict.PARTIAL:      0.5,
        ComplianceVerdict.FAIL:         0.0,
        ComplianceVerdict.INCONCLUSIVE: 0.5,
    }
    score = round(sum(weights[c.verdict] for c in clauses) / len(clauses) * 100, 1)
    if score >= 75:   verdict = ComplianceVerdict.PASS
    elif score >= 40: verdict = ComplianceVerdict.PARTIAL
    else:             verdict = ComplianceVerdict.FAIL
    return score, verdict


def _summarise(name, score, verdict, clauses, pii):
    print("  Generating summary...")
    passed   = [f"{c.clause_ref}: {c.clause_summary}" for c in clauses if c.verdict == ComplianceVerdict.PASS]
    failed   = [f"{c.clause_ref}: {c.clause_summary}" for c in clauses if c.verdict == ComplianceVerdict.FAIL]
    partial  = [f"{c.clause_ref}: {c.clause_summary}" for c in clauses if c.verdict == ComplianceVerdict.PARTIAL]
    crit_pii = [p.pii_type for p in pii if p.risk_level == RiskLevel.CRITICAL]

    raw = call_llm("", f"""You are a compliance consultant writing a factual report for a startup founder.

AUDIT RESULTS for: {name}
Score: {score}/100  |  Verdict: {verdict.value}
Clauses PASSED  : {passed  or ["None"]}
Clauses FAILED  : {failed  or ["None"]}
Clauses PARTIAL : {partial or ["None"]}
Critical PII    : {crit_pii or ["None"]}

RULES: Only mention strengths from PASSED list. Recommendations must fix only FAILED/PARTIAL issues.
Return JSON: {{"summary": "2-3 sentences", "recommendations": ["fix1","fix2","fix3"]}}
JSON only. No markdown.
""")
    try:
        result = json.loads(raw)
        return result.get("summary", "Audit complete."), result.get("recommendations", [])
    except Exception:
        return "Audit complete. Review individual clause results.", []


def audit_document(path: str, law_id: str = "DPDP_2023") -> ComplianceScorecard:
    from agents.utils import _provider, _model
    print(f"\n[bold green]━━━ GuardPulse Audit Starting ━━━[/bold green]")
    print(f"  Document : {path}")
    print(f"  Provider : {_provider} / {_model}")
    print(f"  Law      : {law_id}\n")

    doc_text      = _load_document(path)
    print(f"  Loaded   : {len(doc_text):,} chars")

    legal_context = _retrieve_legal_context(law_id)
    pii_findings  = _detect_pii(doc_text)
    print(f"  PII found: {len(pii_findings)} types")

    clauses       = _check_compliance(doc_text, legal_context, law_id)
    print(f"  Clauses  : {len(clauses)} checked")

    score, verdict = _score(clauses)
    print(f"  Score    : {score}/100 — {verdict.value}")

    summary, recs = _summarise(os.path.basename(path), score, verdict, clauses, pii_findings)

    return ComplianceScorecard(
        target_document = os.path.basename(path),
        law_ids_checked = [law_id],
        overall_verdict = verdict,
        score           = score,
        clauses         = clauses,
        pii_findings    = pii_findings,
        summary         = summary,
        recommendations = recs
    )