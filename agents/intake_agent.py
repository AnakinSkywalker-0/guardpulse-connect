"""
agents/intake_agent.py — Phase 3.

Two jobs:
  1. extract_capability_profile() — used at REGISTRATION time, converts a
     startup's plain-English description into category + capability tags.
  2. ProblemIntakeAgent — used at MATCH time, converts a CEO's natural
     language problem into the same category + capability vocabulary,
     so keyword matching actually works.

Both share one extraction function so the tag vocabulary stays consistent
on both sides of the match.
"""

import os
import json
# pyrefly: ignore [missing-import]
from dotenv import load_dotenv
# pyrefly: ignore [missing-import]
from rich import print
from models import ProblemRequirements
from agents.utils import call_ollama

load_dotenv()
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", os.getenv("GROQ_MODEL", "llama3.2"))

# Example categories shown to the LLM to keep vocabulary consistent across
# both startup registration and CEO problem intake. Not an enforced enum —
# the model can return something else if nothing here fits.
EXAMPLE_CATEGORIES = (
    "fintech, healthtech, ai_saas, logistics, edtech, cybersecurity, "
    "ecommerce, hr_tech, legal_tech, martech, climate_tech, proptech, devtools"
)


def _extract(text: str, role_context: str) -> dict:
    """
    Shared LLM extraction. role_context distinguishes a startup
    self-description from a CEO's problem statement in the prompt.
    """
    raw = call_ollama(OLLAMA_MODEL, f"""{role_context}

TEXT: {text[:1500]}

Return a JSON object with exactly these fields:
- category: ONE lowercase snake_case word for the primary industry/domain.
  Examples: {EXAMPLE_CATEGORIES}
  Pick the closest fit, or another fitting snake_case word if none match.
- capabilities: array of 3-6 lowercase snake_case keywords describing
  specific functions/features (e.g. fraud_detection, payment_processing,
  real_time_analytics, api_integration, document_automation)
- summary: one sentence plain English summary (max 120 chars)

Return ONLY the JSON object. No explanation. No markdown.
""")
    try:
        data = json.loads(raw)
        return {
            "category":     str(data.get("category", "general")).lower().strip(),
            "capabilities": [str(c).lower().strip() for c in data.get("capabilities", [])][:6],
            "summary":      str(data.get("summary", ""))[:150],
        }
    except Exception:
        print("  [yellow]Capability extraction failed — using defaults[/yellow]")
        return {"category": "general", "capabilities": [], "summary": text[:120]}


def extract_capability_profile(description: str) -> dict:
    """
    Used at REGISTRATION time.
    Converts a startup's self-description into category + capabilities.
    """
    return _extract(
        description,
        role_context=(
            "You are analyzing a startup's description to build a searchable "
            "capability profile for an enterprise matchmaking system."
        ),
    )


class ProblemIntakeAgent:
    """
    Used at MATCH time.
    Converts a CEO's natural-language problem into structured requirements
    that can be searched against the startup registry.
    """
    def __init__(self):
        self.name = "ProblemIntakeAgent"

    def run(self, problem_text: str) -> ProblemRequirements:
        print(f"\n  [bold cyan][{self.name}] Parsing problem statement...[/bold cyan]")

        extracted = _extract(
            problem_text,
            role_context=(
                "A CEO has described a business problem. Extract structured "
                "requirements to search for a vendor/startup solution."
            ),
        )

        # Separate call for a clean semantic search query —
        # different shape of output than category/capabilities.
        raw = call_ollama(OLLAMA_MODEL, f"""Rephrase this business problem as a single
clear sentence optimized for semantic search against startup descriptions.

PROBLEM: {problem_text[:1000]}

Return a JSON object with exactly one field:
- semantic_query: the rephrased sentence (max 150 chars)

Return ONLY the JSON object. No explanation. No markdown.
""")
        try:
            semantic_query = json.loads(raw).get("semantic_query", problem_text[:150])
        except Exception:
            semantic_query = problem_text[:150]

        result = ProblemRequirements(
            original_problem      = problem_text,
            category               = extracted["category"],
            required_capabilities   = extracted["capabilities"],
            semantic_query          = semantic_query,
        )

        print(f"  [{self.name}] Category: {result.category}")
        print(f"  [{self.name}] Capabilities needed: {result.required_capabilities}")
        return result