"""
agents/utils.py
Shared LLM caller for all GuardPulse agents.

FIX 1: call_llm()      — for JSON responses (validates + extracts)
FIX 2: call_llm_text() — for plain text responses (no JSON validation)
        Tech agent summary was failing because call_llm rejects non-JSON.
FIX 3: Groq-compatible — uses openai-compatible client.
"""

import re
import os
import json
import time
from dotenv import load_dotenv
from rich import print

load_dotenv()

# ── Provider config ───────────────────────────────────────────────────────────
# Supports Groq, OpenRouter, or Gemini via env vars.
# Priority: GROQ_API_KEY → OPENROUTER_API_KEY → GEMINI_API_KEY

GROQ_API_KEY       = os.getenv("GROQ_API_KEY", "")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
GEMINI_API_KEY     = os.getenv("GEMINI_API_KEY", "")

_provider = None
_client   = None
_model    = None

if GROQ_API_KEY:
    from groq import Groq
    _client   = Groq(api_key=GROQ_API_KEY)
    _model    = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
    _provider = "groq"

elif OPENROUTER_API_KEY:
    from openai import OpenAI
    _client   = OpenAI(
        api_key  = OPENROUTER_API_KEY,
        base_url = "https://openrouter.ai/api/v1",
    )
    _model    = os.getenv("OPENROUTER_MODEL", "meta-llama/llama-3.3-70b-instruct:free")
    _provider = "openrouter"

elif GEMINI_API_KEY:
    try:
        from google import genai
        from google.genai import types as genai_types
        _client   = genai.Client(api_key=GEMINI_API_KEY)
        _model    = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
        _provider = "gemini_new"
    except ImportError:
        import google.generativeai as _genai_old
        _genai_old.configure(api_key=GEMINI_API_KEY)
        _client   = _genai_old.GenerativeModel(os.getenv("GEMINI_MODEL", "gemini-1.5-flash"))
        _model    = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
        _provider = "gemini_old"

else:
    raise EnvironmentError(
        "No LLM API key found. Add one of these to .env:\n"
        "  GROQ_API_KEY=...        (recommended, free, fast)\n"
        "  OPENROUTER_API_KEY=...  (free models available)\n"
        "  GEMINI_API_KEY=...      (15 req/min free tier)\n"
        "Get Groq key free at: https://console.groq.com"
    )

print(f"[cyan]LLM provider: {_provider} / {_model}[/cyan]")


# ── JSON extractor ────────────────────────────────────────────────────────────

def _extract_json(text: str) -> str:
    """Extract first valid JSON array or object from model output."""
    text = re.sub(r"```json\s*", "", text)
    text = re.sub(r"```\s*",     "", text)
    text = text.strip()

    # Direct parse
    try:
        json.loads(text)
        return text
    except Exception:
        pass

    # Find first [...] or {...}
    for open_c, close_c in [("[", "]"), ("{", "}")]:
        start = text.find(open_c)
        if start == -1:
            continue
        depth = 0
        for i, ch in enumerate(text[start:], start):
            if ch == open_c:
                depth += 1
            elif ch == close_c:
                depth -= 1
                if depth == 0:
                    candidate = text[start:i+1]
                    try:
                        json.loads(candidate)
                        return candidate
                    except Exception:
                        break
    return text


# ── Raw LLM call (internal) ───────────────────────────────────────────────────

def _raw_call(prompt: str) -> str:
    """Single LLM call, returns raw string. No validation."""
    if _provider in ("groq", "openrouter"):
        response = _client.chat.completions.create(
            model    = _model,
            messages = [{"role": "user", "content": prompt}],
            temperature      = 0.1,
            max_tokens       = 4096,
        )
        return response.choices[0].message.content.strip()

    elif _provider == "gemini_new":
        from google.genai import types as genai_types
        response = _client.models.generate_content(
            model    = _model,
            contents = prompt,
            config   = genai_types.GenerateContentConfig(
                temperature       = 0.1,
                max_output_tokens = 4096,
            ),
        )
        return (response.text or "").strip()

    elif _provider == "gemini_old":
        import google.generativeai as _genai_old
        response = _client.generate_content(
            prompt,
            generation_config=_genai_old.GenerationConfig(
                temperature=0.1, max_output_tokens=4096,
            )
        )
        return (response.text or "").strip()

    return ""


# ── Public: JSON call ─────────────────────────────────────────────────────────

def call_llm(
    model:   str,         # kept for API compat — ignored, env model used
    prompt:  str,
    retries: int   = 3,
    delay:   float = 2.0,
) -> str:
    """
    Call LLM and return a JSON-parseable string.
    Use this for all structured outputs (clauses, PII, findings).
    Returns "[]" after all retries fail.
    """
    raw = ""
    for attempt in range(1, retries + 1):
        try:
            raw     = _raw_call(prompt)
            if not raw:
                raise ValueError("Empty response")
            cleaned = _extract_json(raw)
            json.loads(cleaned)   # validate
            return cleaned

        except json.JSONDecodeError:
            print(f"  [yellow]JSON parse failed attempt {attempt}/{retries}[/yellow]")
            if attempt == 1 and raw:
                preview = raw[:200].replace("\n", " ")
                print(f"  [dim]Preview: {preview}[/dim]")
            if attempt < retries:
                time.sleep(delay)

        except Exception as e:
            err = str(e)
            if "429" in err or "rate" in err.lower() or "quota" in err.lower():
                wait = delay * attempt * 2
                print(f"  [yellow]Rate limit — waiting {wait:.0f}s (attempt {attempt})[/yellow]")
                time.sleep(wait)
            elif "api_key" in err.lower() or "auth" in err.lower():
                print(f"  [red]Auth error: {err[:120]}[/red]")
                return "[]"
            else:
                print(f"  [yellow]LLM error attempt {attempt}: {err[:100]}[/yellow]")
                if attempt < retries:
                    time.sleep(delay)

    print("  [red]All retries failed — returning [][/red]")
    return "[]"


# ── Public: plain text call ───────────────────────────────────────────────────

def call_llm_text(
    model:   str,
    prompt:  str,
    retries: int   = 2,
    delay:   float = 2.0,
) -> str:
    """
    Call LLM and return plain text (no JSON validation).
    Use this for summaries, free-form descriptions.
    Returns empty string on failure.
    """
    for attempt in range(1, retries + 1):
        try:
            raw = _raw_call(prompt)
            if raw:
                return raw
        except Exception as e:
            err = str(e)
            if "429" in err or "rate" in err.lower():
                wait = delay * attempt * 2
                print(f"  [yellow]Rate limit — waiting {wait:.0f}s[/yellow]")
                time.sleep(wait)
            elif attempt < retries:
                time.sleep(delay)
    return ""


# ── Aliases for backward compat ───────────────────────────────────────────────
# All existing agent files import call_ollama — zero changes needed there.
call_ollama = call_llm
