"""
startup_registry.py — Phase 3.

Registration procedure for a real startup:
  1. Run the Phase 2 swarm audit on their compliance document
  2. Extract a capability profile from their plain-English description
  3. Store both in the startup vector store, ready for matchmaking

This is the bridge between Phase 2 (audit one document) and
Phase 3 (search across many audited startups).
"""

import re
import os
from datetime import datetime, timezone
# pyrefly: ignore [missing-import]
from rich import print

from models import StartupProfile, BadgeStatus
from orchestrator import run_swarm
from agents.intake_agent import extract_capability_profile
from startup_store import store_startup

TRUST_THRESHOLD = 80.0   # GuardPulse score needed to surface in matchmaking


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or "startup"


def register_startup(
    startup_name: str,
    doc_path:     str,
    description:  str,
    asset_paths:  list[str] | None = None,
) -> StartupProfile:
    """
    MAIN REGISTRATION FUNCTION.

    Args:
        startup_name: Display name, e.g. "Acme Fintech"
        doc_path:     Path to their compliance document (privacy policy etc.)
        description:  Plain English — what problem do they solve? Who do
                      they sell to? This is what CEOs will be matched against.
        asset_paths:  Optional extra technical docs for the Tech Architect Agent

    Returns:
        StartupProfile — also persisted to the startup vector store.
    """
    print(f"\n[bold green]{'━'*54}[/bold green]")
    print(f"[bold green]  Registering: {startup_name}[/bold green]")
    print(f"[bold green]{'━'*54}[/bold green]")

    # ── Step 1: run the Phase 2 swarm audit ──────────────────────────────────
    report = run_swarm(
        startup_name = startup_name,
        doc_path     = doc_path,
        asset_paths  = asset_paths,
    )

    # ── Step 2: extract capability profile from description ─────────────────
    print(f"\n  [bold cyan]Extracting capability profile...[/bold cyan]")
    capability_data = extract_capability_profile(description)
    print(f"  Category     : {capability_data['category']}")
    print(f"  Capabilities : {capability_data['capabilities']}")

    # ── Step 3: build and store profile ──────────────────────────────────────
    profile = StartupProfile(
        startup_id        = _slugify(startup_name),
        startup_name       = startup_name,
        description         = description,
        category            = capability_data["category"],
        capabilities         = capability_data["capabilities"],
        guardpulse_score     = report.guardpulse_score,
        badge                = report.badge,
        legal_score          = report.legal_score,
        tech_score           = report.tech_score,
        document_audited     = report.document_audited,
        registered_at         = datetime.now(timezone.utc).isoformat(),
    )

    store_startup(profile)

    # ── Trust filter eligibility notice ──────────────────────────────────────
    print(f"\n[bold]{'─'*54}[/bold]")
    if profile.guardpulse_score >= TRUST_THRESHOLD:
        print(f"  [bold green]✓ Eligible for matchmaking[/bold green] "
              f"(score {profile.guardpulse_score} ≥ {TRUST_THRESHOLD} threshold)")
    else:
        gap = round(TRUST_THRESHOLD - profile.guardpulse_score, 1)
        print(f"  [bold yellow]⚠ Registered but BELOW trust threshold[/bold yellow]")
        print(f"  [yellow]Score {profile.guardpulse_score} is {gap} points below "
              f"the {TRUST_THRESHOLD} minimum for matchmaking.[/yellow]")
        print(f"  [yellow]The startup is stored, but won't appear in CEO match "
              f"results until their score improves.[/yellow]")
    print(f"[bold]{'─'*54}[/bold]\n")

    return profile