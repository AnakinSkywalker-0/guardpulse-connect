"""
sandbox.py — Phase 4.

Mock Sandbox: lets a CEO send a sample query against a registered startup
and see what a response WOULD look like, grounded in that startup's REAL
audited capabilities and category — not a generic placeholder.

No live API exists yet, so the response is simulated by the LLM, but it
is constrained to the startup's actual capability tags and description
so it reads as plausible and specific, not generic filler. Every response
is clearly labeled SIMULATED in the UI layer.
"""

import os
import json
import time
# pyrefly: ignore [missing-import]
from dotenv import load_dotenv
from models import StartupProfile
from agents.utils import call_ollama

load_dotenv()
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", os.getenv("GROQ_MODEL", "llama3.2"))


def run_sandbox_query(startup: StartupProfile, query: str) -> dict:
    """
    Simulate what an API response from this REAL startup might look like,
    grounded in their actual registered capabilities and category.
    """
    start = time.time()

    raw = call_ollama(OLLAMA_MODEL, f"""You are simulating what an API response would look like
from a real startup, based ONLY on their actual registered capabilities below.
Do not invent capabilities they don't have. Keep the response grounded and specific.

STARTUP: {startup.startup_name}
CATEGORY: {startup.category}
REGISTERED CAPABILITIES: {', '.join(startup.capabilities)}
DESCRIPTION: {startup.description}

CEO TEST QUERY: {query}

Return a JSON object with exactly these fields:
- status: "success" or "partial" or "unsupported"
- response_summary: 1-2 sentences describing what the API would likely return
- sample_fields: a JSON object with 3-5 realistic field names and example values
- confidence_note: one sentence on how well this query matches their capabilities

Return ONLY the JSON object. No explanation. No markdown.
""")

    elapsed_ms = round((time.time() - start) * 1000)

    try:
        parsed = json.loads(raw)
    except Exception:
        parsed = {
            "status": "unsupported",
            "response_summary": "Could not generate a simulated response for this query.",
            "sample_fields": {},
            "confidence_note": "Try rephrasing the query or check the startup's capabilities.",
        }

    return {
        "simulated":         True,
        "startup_name":       startup.startup_name,
        "category":           startup.category,
        "capabilities":       startup.capabilities,
        "query":              query,
        "status":             parsed.get("status", "unsupported"),
        "response_summary":   parsed.get("response_summary", ""),
        "sample_fields":      parsed.get("sample_fields", {}),
        "confidence_note":    parsed.get("confidence_note", ""),
        "latency_ms":         elapsed_ms,
        "notes": (
            "This is a simulated response based on the startup's registered "
            "capabilities. No live API endpoint is connected yet."
        ),
    }