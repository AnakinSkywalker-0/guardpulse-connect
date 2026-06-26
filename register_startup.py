# register_startup.py
"""
CLI to register startups into the matchmaking registry.
Usage:
  python register_startup.py manual --name "Acme AI" --score 85 --badge ENTERPRISE_READY --industry fintech --capabilities "fraud_detection,api_integration" --description "We build AI fraud detection APIs" --doc sample_docs/sample_policy.txt
  python register_startup.py list
  python register_startup.py list --min-score 80
"""

import os
import sys
import argparse
from pathlib import Path
# pyrefly: ignore [missing-import]
from rich import print
# pyrefly: ignore [missing-import]
from rich.table import Table
# pyrefly: ignore [missing-import]
from rich.console import Console

sys.path.insert(0, str(Path(__file__).parent))
from startup_registry import register_startup
from startup_store import list_all_startups, get_stats
from models import BadgeStatus

console = Console()


def cmd_register(
    name: str,
    doc_path: str,
    description: str,
    asset_paths: list[str] | None = None,
):
    """Register a startup through the full audit pipeline."""
    if not os.path.exists(doc_path):
        print(f"[red]File not found: {doc_path}[/red]")
        sys.exit(1)
    if not description or len(description.strip()) < 10:
        print(f"[red]--description is required and should be a real sentence.[/red]")
        sys.exit(1)

    profile = register_startup(
        startup_name=name,
        doc_path=doc_path,
        description=description,
        asset_paths=asset_paths,
    )

    print(f"\n[green]✓ Registered {profile.startup_name}[/green]")
    print(f"  ID       : {profile.startup_id}")
    print(f"  Score    : {profile.guardpulse_score}/100")
    print(f"  Badge    : {profile.badge.value}")
    print(f"  Category : {profile.category}")
    print(f"  Caps     : {', '.join(profile.capabilities)}")


def cmd_list(min_score: float = 0, badge_filter: str | None = None):
    """List all registered startups."""
    startups = list_all_startups()

    if min_score > 0:
        startups = [s for s in startups if s.guardpulse_score >= min_score]
    if badge_filter:
        startups = [s for s in startups if s.badge.value == badge_filter]

    if not startups:
        print("[yellow]No startups match the filter criteria.[/yellow]")
        return

    table = Table(title="Registered Startups")
    table.add_column("Name", style="cyan")
    table.add_column("Score", justify="right")
    table.add_column("Badge")
    table.add_column("Category")
    table.add_column("Capabilities")
    table.add_column("Registered")

    for s in sorted(startups, key=lambda x: x.guardpulse_score, reverse=True):
        caps = ", ".join(s.capabilities[:3])
        if len(s.capabilities) > 3:
            caps += "..."

        badge_color = (
            "green" if s.badge.value == "ENTERPRISE_READY" else
            "yellow" if s.badge.value == "CONDITIONAL" else "red"
        )

        table.add_row(
            s.startup_name,
            f"{s.guardpulse_score}/100",
            f"[{badge_color}]{s.badge.value}[/{badge_color}]",
            s.category,
            caps,
            s.registered_at[:10] if s.registered_at else "-",
        )

    console.print(table)

    stats = get_stats()
    print(f"\n[dim]Total: {stats['total_startups']}[/dim]")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="GuardPulse Startup Registry CLI")
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # List command
    list_parser = subparsers.add_parser("list", help="List registered startups")
    list_parser.add_argument("--min-score", type=float, default=0, help="Minimum score filter")
    list_parser.add_argument("--badge", choices=["ENTERPRISE_READY", "CONDITIONAL", "NOT_READY"], help="Filter by badge")

    # Register command — runs full audit pipeline
    reg_parser = subparsers.add_parser("register", help="Register a startup (runs full audit)")
    reg_parser.add_argument("--name", required=True, help="Startup name")
    reg_parser.add_argument("--doc", required=True, help="Path to compliance document")
    reg_parser.add_argument("--description", required=True, help="What the startup does")
    reg_parser.add_argument("--assets", nargs="*", help="Additional asset files")

    args = parser.parse_args()

    if args.command == "list":
        cmd_list(args.min_score, args.badge)
    elif args.command == "register":
        cmd_register(
            name=args.name,
            doc_path=args.doc,
            description=args.description,
            asset_paths=args.assets,
        )
    else:
        parser.print_help()