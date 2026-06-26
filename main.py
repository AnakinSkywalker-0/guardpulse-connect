"""
main.py
GuardPulse CLI — Phase 1 + Phase 2 + Phase 3

Commands:
  python main.py ingest                            Fetch laws, build ChromaDB
  python main.py audit <file>                      Phase 1 single-agent audit
  python main.py swarm <startup> <file>             Phase 2 multi-agent swarm
  python main.py stats                              Show ChromaDB info

  python main.py register <name> <doc> --description "..."   Phase 3: register a startup
  python main.py match "<ceo problem text>"                    Phase 3: find top matches
  python main.py startups                                       Phase 3: list all registered
"""

import os
import sys
import json
# pyrefly: ignore [missing-import]
from rich import print
# pyrefly: ignore [missing-import]
from rich.console import Console
# pyrefly: ignore [missing-import]
from rich.table import Table

console = Console()


# ── Phase 1 commands ──────────────────────────────────────────────────────────

def cmd_ingest(law_ids: list[str] | None = None):
    from fetcher import fetch_document, LEGAL_SOURCES
    from chunker import chunk_document
    from vector_store import store_chunks

    targets = law_ids or list(LEGAL_SOURCES.keys())
    total   = 0
    for law_id in targets:
        doc = fetch_document(law_id)
        if not doc:
            print(f"[red]Skipping {law_id} — fetch failed[/red]")
            continue
        chunks = chunk_document(doc)
        added  = store_chunks(chunks)
        total += added
    print(f"\n[bold green]Ingestion complete — {total} new vectors stored[/bold green]")


def cmd_audit(document_path: str, law_id: str = "DPDP_2023"):
    if not os.path.exists(document_path):
        print(f"[red]File not found: {document_path}[/red]")
        sys.exit(1)
    from compliance_agent import audit_document
    sc = audit_document(document_path, law_id)
    print(f"\n[bold]Score: {sc.score}/100 — {sc.overall_verdict.value}[/bold]")
    print(f"Summary: {sc.summary}")


def cmd_stats():
    from vector_store import get_stats
    stats = get_stats()
    print(f"\n[bold]ChromaDB Stats — Legal Knowledge Base[/bold]")
    print(f"  Vectors    : {stats['total_vectors']}")
    print(f"  Collection : {stats['collection']}")
    print(f"  Path       : {stats['db_path']}")

    from startup_store import get_stats as startup_stats
    sstats = startup_stats()
    print(f"\n[bold]ChromaDB Stats — Startup Registry[/bold]")
    print(f"  Startups   : {sstats['total_startups']}")
    print(f"  Collection : {sstats['collection']}")


# ── Phase 2 command ───────────────────────────────────────────────────────────

def cmd_swarm(startup_name: str, doc_path: str, asset_paths: list[str] | None, save_json: bool):
    from orchestrator import run_swarm, print_report
    report = run_swarm(startup_name=startup_name, doc_path=doc_path, asset_paths=asset_paths)
    print_report(report)
    if save_json:
        out = doc_path.replace(".txt", "").replace(".pdf", "") + "_guardpulse_report.json"
        with open(out, "w") as f:
            json.dump(report.model_dump(), f, indent=2)
        print(f"\n[dim]Full report saved -> {out}[/dim]")


# ── Phase 3 commands ──────────────────────────────────────────────────────────

def cmd_register(
    startup_name: str,
    doc_path:     str,
    description:  str,
    asset_paths:  list[str] | None,
):
    """Register a real startup — runs the swarm, then stores a searchable profile."""
    if not os.path.exists(doc_path):
        print(f"[red]File not found: {doc_path}[/red]")
        sys.exit(1)
    if not description or len(description.strip()) < 10:
        print(f"[red]--description is required and should be a real sentence "
              f"describing what the startup does (used for matching).[/red]")
        sys.exit(1)

    from startup_registry import register_startup
    profile = register_startup(
        startup_name = startup_name,
        doc_path     = doc_path,
        description  = description,
        asset_paths  = asset_paths,
    )

    print(f"[bold]Registered:[/bold] {profile.startup_name}")
    print(f"[bold]ID:[/bold] {profile.startup_id}")
    print(f"[bold]Category:[/bold] {profile.category}")
    print(f"[bold]Capabilities:[/bold] {', '.join(profile.capabilities)}")
    print(f"[bold]GuardPulse Score:[/bold] {profile.guardpulse_score}/100 ({profile.badge.value})")


def cmd_match(problem_text: str, top_k: int, threshold: float, save_json: bool):
    """Find the top startups matching a CEO's problem statement."""
    from matchmaking_engine import find_matches, print_match_report
    result = find_matches(problem_text, top_k=top_k, trust_threshold=threshold)
    print_match_report(result)

    if save_json:
        out = "match_result.json"
        with open(out, "w") as f:
            json.dump(result.model_dump(), f, indent=2)
        print(f"\n[dim]Full match result saved -> {out}[/dim]")


def cmd_startups():
    """List every registered startup."""
    from startup_store import list_all_startups
    startups = list_all_startups()

    if not startups:
        print("[yellow]No startups registered yet. Use 'python main.py register' to add one.[/yellow]")
        return

    print(f"\n[bold]Registered Startups ({len(startups)})[/bold]")
    t = Table(show_header=True, header_style="bold")
    t.add_column("Name",     width=22)
    t.add_column("Category", width=16)
    t.add_column("Score",    width=8)
    t.add_column("Badge",    width=18)
    t.add_column("Registered", width=12)

    for s in sorted(startups, key=lambda x: x.guardpulse_score, reverse=True):
        badge_color = (
            "green"  if s.badge.value == "ENTERPRISE_READY" else
            "yellow" if s.badge.value == "CONDITIONAL" else "red"
        )
        t.add_row(
            s.startup_name, s.category, f"{s.guardpulse_score}/100",
            f"[{badge_color}]{s.badge.value}[/{badge_color}]",
            s.registered_at[:10] if s.registered_at else "-",
        )
    console.print(t)


# ── CLI dispatcher ────────────────────────────────────────────────────────────

def main():
    args = sys.argv[1:]

    if not args or args[0] == "help":
        print("""
[bold]GuardPulse CLI[/bold]

Phase 1:
  python main.py ingest
  python main.py audit sample_docs/sample_policy.txt

Phase 2:
  python main.py swarm "MyStartup" sample_docs/sample_policy.txt
  python main.py swarm "MyStartup" sample_docs/sample_policy.txt --assets README.md --json

Phase 3:
  python main.py register "Acme Fintech" docs/policy.txt --description "We provide AI fraud detection APIs for payment processors"
  python main.py register "Acme Fintech" docs/policy.txt --description "..." --assets api_docs.md
  python main.py match "I need a vendor for fraud detection in our payments platform"
  python main.py match "..." --top 5 --threshold 70
  python main.py startups
""")
        return

    cmd = args[0]

    if cmd == "ingest":
        law_ids = [a for a in args[1:] if not a.startswith("--")]
        cmd_ingest(law_ids or None)

    elif cmd == "audit":
        if len(args) < 2:
            print("[red]Usage: python main.py audit <file_path>[/red]")
            sys.exit(1)
        doc_path = args[1]
        law_id   = "DPDP_2023"
        if "--law" in args:
            idx = args.index("--law")
            law_id = args[idx + 1]
        cmd_audit(doc_path, law_id)

    elif cmd == "stats":
        cmd_stats()

    elif cmd == "swarm":
        if len(args) < 3:
            print("[red]Usage: python main.py swarm <startup_name> <doc_path> [--assets f1 f2] [--json][/red]")
            sys.exit(1)
        startup   = args[1]
        doc       = args[2]
        assets    = None
        save_json = "--json" in args
        if "--assets" in args:
            idx    = args.index("--assets")
            assets = [a for a in args[idx + 1:] if not a.startswith("--")]
        cmd_swarm(startup, doc, assets, save_json)

    elif cmd == "register":
        if len(args) < 3:
            print('[red]Usage: python main.py register "<name>" <doc_path> --description "..." [--assets f1 f2][/red]')
            sys.exit(1)
        startup_name = args[1]
        doc_path     = args[2]
        description  = ""
        assets       = None
        if "--description" in args:
            idx = args.index("--description")
            description = args[idx + 1]
        if "--assets" in args:
            idx    = args.index("--assets")
            assets = [a for a in args[idx + 1:] if not a.startswith("--")]
        cmd_register(startup_name, doc_path, description, assets)

    elif cmd == "match":
        if len(args) < 2:
            print('[red]Usage: python main.py match "<problem text>" [--top 3] [--threshold 80] [--json][/red]')
            sys.exit(1)
        problem_text = args[1]
        top_k        = 3
        threshold    = 80.0
        save_json    = "--json" in args
        if "--top" in args:
            idx   = args.index("--top")
            top_k = int(args[idx + 1])
        if "--threshold" in args:
            idx       = args.index("--threshold")
            threshold = float(args[idx + 1])
        cmd_match(problem_text, top_k, threshold, save_json)

    elif cmd == "startups":
        cmd_startups()

    else:
        print(f"[red]Unknown command: {cmd}[/red]")
        print("Run [bold]python main.py help[/bold] for usage.")


if __name__ == "__main__":
    main()