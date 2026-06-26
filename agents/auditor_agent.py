"""
agents/auditor_agent.py — Auditor Agent, Phase 2.

FIX 1: DPDP §6 INCONCLUSIVE — prompt now gives the model explicit consent
        signal words to look for ("by using", "you agree", "I accept", checkbox,
        tick, opt-in) so it stops defaulting to INCONCLUSIVE on implicit consent.

FIX 2: EU AI Art.5 INCONCLUSIVE on non-AI docs — auditor now detects whether
        the document is AI-related before running EU AI clauses. If it's a plain
        privacy policy, EU AI clauses are marked INCONCLUSIVE with a clear note
        instead of confusing the model into wrong verdicts.

FIX 3: Improved clause checking accuracy — prompt now includes the actual law
        text snippet for each clause, so the model can compare document vs law
        directly rather than relying on vague summaries.
"""

import os
import json
from dotenv import load_dotenv
from rich import print
from models import (
    LegalAuditResult, ComplianceClause, PIIFinding,
    ComplianceVerdict, RiskLevel,
)
from vector_store import query as chroma_query
from agents.utils import call_ollama

load_dotenv()
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", os.getenv("GROQ_MODEL", "llama3.2"))

LAW_QUERIES = {
    "DPDP_2023": [
        "consent requirements before collecting personal data",
        "rights of data principal access correction erasure",
        "data breach notification requirements",
        "processing personal data of children",
        "grievance redressal mechanism",
    ],
    "EU_AI_ACT_2024": [
        "prohibited AI practices unacceptable risk",
        "high risk AI system requirements",
        "transparency obligations AI systems",
        "human oversight requirements",
    ],
}

LAW_CLAUSES = {
    "DPDP_2023": [
        ("DPDP §5",  "Privacy notice provided to users"),
        ("DPDP §6",  "Valid consent obtained before collection"),
        ("DPDP §8",  "Data retention and deletion policy"),
        ("DPDP §9",  "Children data protection measures"),
        ("DPDP §11", "User right to access their data"),
        ("DPDP §12", "User right to correct and erase data"),
        ("DPDP §13", "Grievance redressal mechanism"),
        ("DPDP §16", "Data breach notification process"),
    ],
    "EU_AI_ACT_2024": [
        ("EU AI Art.5",  "No prohibited AI practices used"),
        ("EU AI Art.9",  "Risk management system documented"),
        ("EU AI Art.13", "Transparency obligations met"),
        ("EU AI Art.14", "Human oversight mechanisms defined"),
    ],
}

# Keywords that indicate a document is AI-system related
AI_DOC_SIGNALS = [
    "artificial intelligence", "machine learning", "ai system", "algorithm",
    "automated decision", "neural network", "model training", "inference",
    "deep learning", "natural language", "computer vision", "ai model",
]


def _is_ai_document(text: str) -> bool:
    """Check if document is AI-system related (for EU AI Act relevance)."""
    lower = text.lower()
    return sum(1 for signal in AI_DOC_SIGNALS if signal in lower) >= 2


class AuditorAgent:
    def __init__(self):
        self.name  = "AuditorAgent"
        self.model = OLLAMA_MODEL

    def _context(self, law_id: str) -> str:
        seen, parts = set(), []
        for q in LAW_QUERIES.get(law_id, []):
            for r in chroma_query(q, top_k=2, law_id=law_id):
                if r.chunk_id not in seen:
                    seen.add(r.chunk_id)
                    parts.append(
                        f"[{r.law_id} §{r.section_number} — {r.section_title}]\n"
                        f"{r.text[:600]}"
                    )
        return "\n\n".join(parts)

    def _pii(self, text: str) -> list[PIIFinding]:
        raw = call_ollama(self.model, f"""Find personal data (PII) in this document.

DOCUMENT: {text[:3000]}

Return JSON array only. Each item:
- pii_type: one of NAME EMAIL PHONE AADHAAR PAN ADDRESS IP_ADDRESS LOCATION HEALTH_DATA FINANCIAL_DATA BIOMETRIC DEVICE_ID COOKIES DATE_OF_BIRTH
- context_snippet: sentence containing PII (max 120 chars)
- risk_level: LOW, MEDIUM, HIGH, or CRITICAL
- relevant_law: e.g. "DPDP Act 2023 §2(t)"
- recommendation: one specific action to protect this data

Return [] if none found. JSON array only, no explanation.
""")
        try:
            out = []
            for i in json.loads(raw):
                try:
                    out.append(PIIFinding(
                        pii_type        = i.get("pii_type", "UNKNOWN"),
                        context_snippet = str(i.get("context_snippet", ""))[:150],
                        risk_level      = RiskLevel(i.get("risk_level", "MEDIUM")),
                        relevant_law    = i.get("relevant_law", "DPDP Act 2023"),
                        recommendation  = i.get("recommendation", "Review and protect"),
                    ))
                except Exception:
                    continue
            return out
        except Exception:
            return []

    def _clauses_dpdp(self, doc: str, ctx: str) -> list[ComplianceClause]:
        """
        FIX 1 + FIX 3: Improved DPDP clause checking.
        - §6 consent: lists explicit signal words so model detects implicit consent
        - Each requirement has a concrete "what to look for" hint
        - Uses more document context (3000 chars vs 2000)
        """
        items = LAW_CLAUSES["DPDP_2023"]
        check = "\n".join(f"{i+1}. {ref}: {s}" for i, (ref, s) in enumerate(items))

        raw = call_ollama(self.model, f"""You are an expert in Indian data protection law (DPDP Act 2023).
Audit the DOCUMENT against each requirement using the LAW CONTEXT as reference.

LAW CONTEXT (DPDP Act 2023 sections):
{ctx[:2500]}

DOCUMENT TO AUDIT:
{doc[:3000]}

Requirements to check:
{check}

IMPORTANT NOTES FOR ACCURATE VERDICTS:
- DPDP §6 (Consent): Mark PASS if the document mentions any of these consent signals:
  "by using this service", "you agree", "I accept", checkbox, tick box, opt-in,
  clicking agree, continuing to use. Mark PARTIAL if consent is implied but not explicit.
  Only mark FAIL if there is zero mention of user agreement or consent.
- DPDP §8 (Retention): Mark PASS if any retention period or deletion timeframe is mentioned.
- DPDP §9 (Children): Mark PASS if children/minors are mentioned even to say service is not for them.
- DPDP §13 (Grievance): Mark PASS if any of these exist: email contact, support form, "contact us",
  complaints process, feedback mechanism, designated officer, or any way to raise concerns.
  Mark FAIL only if there is absolutely no contact or dispute resolution mechanism at all.
- For any other clause: use INCONCLUSIVE only if you genuinely cannot determine from the document.
  Default to FAIL if the requirement is simply not addressed.

Return JSON array. Each item must have:
- clause_ref: exactly as listed above (e.g. "DPDP §6")
- clause_summary: max 80 chars
- verdict: PASS, FAIL, PARTIAL, or INCONCLUSIVE
- evidence: quote or observation from the DOCUMENT (max 120 chars). Write "Not addressed in document." if absent.
- confidence: 0.0 to 1.0

Return ONLY the JSON array. No explanation. No markdown.
""")
        return self._parse_clauses(raw, "DPDP_2023")

    def _clauses_eu(self, doc: str, ctx: str, is_ai_doc: bool) -> list[ComplianceClause]:
        """
        FIX 2: If document is not AI-related, return INCONCLUSIVE with clear note
        instead of asking the model to audit a privacy policy against AI law.
        """
        items = LAW_CLAUSES["EU_AI_ACT_2024"]

        if not is_ai_doc:
            # Document is not AI-related — EU AI Act clauses are not applicable
            return [
                ComplianceClause(
                    clause_ref     = ref,
                    clause_summary = summary,
                    verdict        = ComplianceVerdict.INCONCLUSIVE,
                    evidence       = "Document is not an AI system disclosure — EU AI Act not applicable.",
                    confidence     = 0.9,
                )
                for ref, summary in items
            ]

        check = "\n".join(f"{i+1}. {ref}: {s}" for i, (ref, s) in enumerate(items))

        raw = call_ollama(self.model, f"""You are an expert in the EU AI Act 2024.
Audit the DOCUMENT against each requirement using the LAW CONTEXT as reference.

LAW CONTEXT (EU AI Act sections):
{ctx[:2500]}

DOCUMENT TO AUDIT:
{doc[:3000]}

Requirements to check:
{check}

NOTES:
- Art.5 (Prohibited AI): Mark PASS if document confirms no prohibited practices.
  Mark INCONCLUSIVE if document doesn't mention AI risk level at all.
- Art.9 (Risk management): Mark FAIL if no risk management or safety processes mentioned.
- Art.13 (Transparency): Mark PASS if document explains what the AI system does to users.
- Art.14 (Human oversight): Mark FAIL if no human review or override mechanism mentioned.

Return JSON array. Each item must have:
- clause_ref: exactly as listed (e.g. "EU AI Art.5")
- clause_summary: max 80 chars
- verdict: PASS, FAIL, PARTIAL, or INCONCLUSIVE
- evidence: quote or observation from DOCUMENT (max 120 chars)
- confidence: 0.0 to 1.0

Return ONLY the JSON array. No explanation. No markdown.
""")
        return self._parse_clauses(raw, "EU_AI_ACT_2024")

    def _parse_clauses(self, raw: str, law_id: str) -> list[ComplianceClause]:
        """Parse model JSON output into ComplianceClause objects."""
        items = LAW_CLAUSES.get(law_id, [])
        try:
            out = []
            for i in json.loads(raw):
                try:
                    out.append(ComplianceClause(
                        clause_ref     = i.get("clause_ref", "Unknown"),
                        clause_summary = str(i.get("clause_summary", ""))[:100],
                        verdict        = ComplianceVerdict(i.get("verdict", "INCONCLUSIVE")),
                        evidence       = str(i.get("evidence", ""))[:150],
                        confidence     = float(i.get("confidence", 0.5)),
                    ))
                except Exception:
                    continue
            return out
        except Exception:
            print(f"  [{self.name}] [yellow]Clause parse failed ({law_id}) — using INCONCLUSIVE defaults[/yellow]")
            return [
                ComplianceClause(
                    clause_ref     = ref,
                    clause_summary = summary,
                    verdict        = ComplianceVerdict.INCONCLUSIVE,
                    evidence       = "Model parse failed — manual review needed.",
                    confidence     = 0.3,
                )
                for ref, summary in items
            ]

    def _score(self, clauses: list[ComplianceClause]) -> tuple[float, ComplianceVerdict]:
        if not clauses:
            return 0.0, ComplianceVerdict.INCONCLUSIVE
        w = {
            ComplianceVerdict.PASS:         1.0,
            ComplianceVerdict.PARTIAL:      0.5,
            ComplianceVerdict.FAIL:         0.0,
            ComplianceVerdict.INCONCLUSIVE: 0.4,
        }
        s = round(sum(w[c.verdict] for c in clauses) / len(clauses) * 100, 1)
        v = (
            ComplianceVerdict.PASS    if s >= 75 else
            ComplianceVerdict.PARTIAL if s >= 40 else
            ComplianceVerdict.FAIL
        )
        return s, v

    def _summary(self, doc_name, score, verdict, clauses, pii):
        fails   = [c.clause_ref + ": " + c.clause_summary for c in clauses if c.verdict == ComplianceVerdict.FAIL]
        passed  = [c.clause_ref + ": " + c.clause_summary for c in clauses if c.verdict == ComplianceVerdict.PASS]
        raw = call_ollama(self.model, f"""Write a compliance audit summary for a startup founder.

Score: {score}/100  Verdict: {verdict.value}
Passed clauses: {passed[:4]}
Failed clauses: {fails[:4]}

RULES: Only mention strengths from the PASSED list. Do not invent positives.
Return JSON: {{"summary": "2 sentences max", "recommendations": ["fix1", "fix2", "fix3"]}}
JSON only. No markdown.
""")
        try:
            r = json.loads(raw)
            return r.get("summary", "Audit complete."), r.get("recommendations", [])
        except Exception:
            return f"Compliance score: {score}/100 ({verdict.value}). Review failed clauses.", []

    def run(self, doc_text: str, doc_name: str) -> LegalAuditResult:
        print(f"\n  [bold cyan][{self.name}] Starting...[/bold cyan]")

        # Detect if document is AI-related (for EU AI Act applicability)
        is_ai = _is_ai_document(doc_text)
        if not is_ai:
            print(f"  [{self.name}] Document type: privacy policy (not AI-specific)")
        else:
            print(f"  [{self.name}] Document type: AI system disclosure")

        all_clauses = []

        # DPDP 2023
        print(f"  [{self.name}] Checking DPDP_2023...")
        dpdp_ctx     = self._context("DPDP_2023")
        dpdp_clauses = self._clauses_dpdp(doc_text, dpdp_ctx)
        print(f"  [{self.name}] DPDP_2023: {len(dpdp_clauses)} clauses parsed")
        all_clauses.extend(dpdp_clauses)

        # EU AI Act
        print(f"  [{self.name}] Checking EU_AI_ACT_2024...")
        eu_ctx     = self._context("EU_AI_ACT_2024")
        eu_clauses = self._clauses_eu(doc_text, eu_ctx, is_ai)
        print(f"  [{self.name}] EU_AI_ACT_2024: {len(eu_clauses)} clauses parsed")
        all_clauses.extend(eu_clauses)

        print(f"  [{self.name}] Detecting PII...")
        pii            = self._pii(doc_text)
        score, verdict = self._score(all_clauses)
        summary, recs  = self._summary(doc_name, score, verdict, all_clauses, pii)
        print(f"  [{self.name}] {len(pii)} PII types | Legal score: [bold]{score}/100[/bold] — {verdict.value}")

        return LegalAuditResult(
            target_document = doc_name,
            laws_checked    = ["DPDP_2023", "EU_AI_ACT_2024"],
            clauses         = all_clauses,
            pii_findings    = pii,
            legal_score     = score,
            overall_verdict = verdict,
            summary         = summary,
            recommendations = recs,
        )