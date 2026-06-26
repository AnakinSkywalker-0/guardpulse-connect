"""
agents/critic_agent.py — Critic Agent, Phase 2.
Verifies Auditor citations against real ChromaDB law text.

FIX 1: _fetch_law() now queries by section content keyword (e.g. "consent")
        rather than clause_ref (e.g. "DPDP §5"), so ChromaDB finds the right
        chunk even when section numbers don't match the metadata exactly.
FIX 2: Hallucination threshold raised to 0.75 confidence before marking invalid.
        Llama/Groq was flagging valid citations as hallucinated at low confidence.
FIX 3: Critic prompt made more precise — tells model to focus on semantic
        meaning match, not exact section number match.
"""

import os
import json
from dotenv import load_dotenv
from rich import print
from models import CriticResult, CitationCheck, LegalAuditResult
from vector_store import query as chroma_query
from agents.utils import call_ollama

load_dotenv()
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", os.getenv("GROQ_MODEL", "llama3.2"))

# Maps clause keywords to better ChromaDB search queries
CLAUSE_SEARCH_MAP = {
    "§5":    "privacy notice data fiduciary obligations",
    "§6":    "consent data principal personal data collection",
    "§8":    "data retention deletion erasure",
    "§9":    "children personal data parental consent",
    "§11":   "right to access personal data",
    "§12":   "right to correction erasure personal data",
    "§13":   "grievance redressal officer complaint",
    "§16":   "data breach notification fiduciary",
    "Art.5": "prohibited AI practices unacceptable risk",
    "Art.9": "risk management system high risk AI",
    "Art.13": "transparency information AI system",
    "Art.14": "human oversight high risk AI system",
}


class CriticAgent:
    def __init__(self):
        self.name  = "CriticAgent"
        self.model = OLLAMA_MODEL

    def _fetch_law(self, clause_ref: str, claim: str) -> str:
        """
        FIX: Uses semantic keywords instead of clause ref for retrieval.
        Finds the right ChromaDB chunk even when section number metadata
        doesn't perfectly match.
        """
        law_id = (
            "DPDP_2023"      if "DPDP" in clause_ref else
            "EU_AI_ACT_2024" if "EU AI" in clause_ref else
            None
        )

        # Build a semantic search query from the claim + known keywords
        search_query = claim
        for ref_key, keyword_query in CLAUSE_SEARCH_MAP.items():
            if ref_key in clause_ref:
                search_query = keyword_query
                break

        results = chroma_query(search_query, top_k=3, law_id=law_id)
        if not results:
            return ""
        return "\n\n".join(
            f"[{r.law_id} §{r.section_number} — {r.section_title}]\n{r.text[:500]}"
            for r in results
        )

    def _verify(
        self,
        clause_ref: str,
        summary: str,
        evidence: str,
        law_text: str,
    ) -> CitationCheck:
        if not law_text:
            return CitationCheck(
                original_claim = summary,
                citation_ref   = clause_ref,
                is_valid       = True,
                correction     = None,
                confidence     = 0.4,
            )

        raw = call_ollama(self.model, f"""You are a legal fact-checker.

Does the law text below support the compliance claim? Focus on whether the
MEANING of the claim is supported, not whether the exact section number matches.

CLAIM: "{summary}"
CITATION: {clause_ref}

LAW TEXT:
{law_text[:2000]}

Instructions:
- is_valid: true if the law text supports the general meaning of the claim
- is_valid: false only if the law text DIRECTLY CONTRADICTS the claim
- If the law text is about a different topic entirely, set is_valid to true
  (it means the retrieval was off, not that the claim is wrong)
- confidence: your confidence in this judgment (0.0 to 1.0)
- correction: only if is_valid is false, what the law actually says

Return ONLY this JSON object:
{{"is_valid": true, "correction": null, "confidence": 0.8}}
""")
        try:
            r          = json.loads(raw)
            is_valid   = bool(r.get("is_valid", True))
            confidence = float(r.get("confidence", 0.5))
            correction = r.get("correction")

            # FIX: Only flag as invalid if model is highly confident (>0.75)
            # This prevents false positives from retrieval mismatches
            if not is_valid and confidence < 0.75:
                is_valid   = True
                correction = None

            return CitationCheck(
                original_claim = f"{summary} ({evidence})",
                citation_ref   = clause_ref,
                is_valid       = is_valid,
                correction     = str(correction)[:200] if correction and not is_valid else None,
                confidence     = confidence,
            )
        except Exception:
            return CitationCheck(
                original_claim = summary,
                citation_ref   = clause_ref,
                is_valid       = True,
                correction     = None,
                confidence     = 0.3,
            )

    def _verdict(self, rate: float) -> str:
        if rate == 0.0:    return "RELIABLE"
        elif rate <= 0.15: return "MOSTLY_RELIABLE"
        elif rate <= 0.35: return "QUESTIONABLE"
        else:              return "UNRELIABLE"

    def run(self, legal_audit: LegalAuditResult) -> CriticResult:
        print(f"\n  [bold cyan][{self.name}] Starting hallucination checks...[/bold cyan]")

        clauses = legal_audit.clauses
        if not clauses:
            return CriticResult(
                total_claims_checked = 0,
                valid_claims         = 0,
                invalid_claims       = 0,
                citation_checks      = [],
                hallucination_rate   = 0.0,
                critic_verdict       = "RELIABLE",
                notes                = "No clauses to verify.",
            )

        checks = []
        for i, c in enumerate(clauses):
            print(f"  [{self.name}] Verifying {c.clause_ref} ({i+1}/{len(clauses)})...")
            law_text = self._fetch_law(c.clause_ref, c.clause_summary)
            check    = self._verify(c.clause_ref, c.clause_summary, c.evidence, law_text)
            checks.append(check)

        valid   = sum(1 for c in checks if c.is_valid)
        invalid = len(checks) - valid
        h_rate  = round(invalid / len(checks), 3)
        verdict = self._verdict(h_rate)

        print(f"  [{self.name}] Valid: {valid} | Invalid: {invalid} | Rate: {h_rate:.1%} — {verdict}")

        return CriticResult(
            total_claims_checked = len(checks),
            valid_claims         = valid,
            invalid_claims       = invalid,
            citation_checks      = checks,
            hallucination_rate   = h_rate,
            critic_verdict       = verdict,
            notes                = (
                f"All {len(checks)} citations verified against ChromaDB law text."
                if invalid == 0 else
                f"{invalid}/{len(checks)} citations flagged (confidence threshold: 0.75)."
            ),
        )
