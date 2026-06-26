"""
matchmaking_engine.py — Phase 3.

Takes a CEO's natural language problem and returns the top 3 verified
startups, using hybrid search:
  - Semantic search: cosine similarity between problem and startup
    descriptions (ChromaDB, via startup_store.search_startups)
  - Keyword search: overlap between required_capabilities and the
    startup's own capability tags
  - Trust Filter: only startups with guardpulse_score >= TRUST_THRESHOLD
    are eligible, applied AFTER scoring so we can report how many were
    filtered out

relevance_score = semantic_score * 0.6 + keyword_score * 0.4
                  (+0.1 bonus if categories match exactly, capped at 1.0)
"""

# pyrefly: ignore [missing-import]
from rich import print
# pyrefly: ignore [missing-import]
from rich.console import Console
# pyrefly: ignore [missing-import]
from rich.table import Table

from models import MatchmakingResult, StartupMatch, ProblemRequirements
from agents.intake_agent import ProblemIntakeAgent
from startup_store import search_startups

console = Console()

TRUST_THRESHOLD       = 80.0
SEMANTIC_WEIGHT       = 0.6
KEYWORD_WEIGHT        = 0.4
CATEGORY_MATCH_BONUS  = 0.1
CANDIDATE_POOL_SIZE   = 10


def _keyword_overlap_score(required: list[str], offered: list[str]) -> float:
    """
    What fraction of the CEO's required capabilities does this startup cover?
    Recall-oriented — we care about meeting the CEO's needs.
    """
    if not required:
        return 0.0
    required_set = set(required)
    offered_set  = set(offered)
    overlap      = required_set & offered_set
    return round(len(overlap) / len(required_set), 3)


def _build_match_reason(
    startup_name: str,
    matched_caps: set,
    same_category: bool,
    score: float,
) -> str:
    """Template-based reason — fast, deterministic, no extra LLM call."""
    parts = []
    if same_category:
        parts.append("same industry focus")
    if matched_caps:
        cap_list = ", ".join(sorted(matched_caps)[:3])
        parts.append(f"covers {cap_list}")
    if not parts:
        parts.append("strong semantic match to the problem description")
    return f"{startup_name}: " + "; ".join(parts) + f" (relevance {score:.0%})"


def find_matches(
    problem_text:    str,
    top_k:           int   = 3,
    trust_threshold: float = TRUST_THRESHOLD,
) -> MatchmakingResult:
    """
    MAIN MATCHING FUNCTION.

    Args:
        problem_text:    CEO's problem in plain English
        top_k:           how many matches to return (default 3)
        trust_threshold: minimum GuardPulse score to be eligible (default 80)

    Returns:
        MatchmakingResult with up to top_k StartupMatch objects,
        sorted by relevance_score descending.
    """
    print(f"\n[bold green]{'━'*54}[/bold green]")
    print(f"[bold green]  GuardPulse Matchmaking Engine[/bold green]")
    print(f"[bold green]{'━'*54}[/bold green]")
    print(f"  Problem: {problem_text}\n")

    requirements = ProblemIntakeAgent().run(problem_text)

    print(f"\n  [bold cyan]Searching startup registry...[/bold cyan]")
    candidates = search_startups(requirements.semantic_query, top_k=CANDIDATE_POOL_SIZE)
    print(f"  Found {len(candidates)} semantic candidates")

    if not candidates:
        print(f"  [yellow]No startups registered yet. Use 'python main.py register' first.[/yellow]")
        return MatchmakingResult(
            problem=problem_text, requirements=requirements, matches=[],
            total_candidates=0, total_after_trust_filter=0,
            trust_threshold=trust_threshold,
        )

    scored_matches = []
    for profile, semantic_score in candidates:
        keyword_score  = _keyword_overlap_score(requirements.required_capabilities, profile.capabilities)
        same_category  = (profile.category == requirements.category)
        category_bonus = CATEGORY_MATCH_BONUS if same_category else 0.0

        relevance = round(
            min(1.0, semantic_score * SEMANTIC_WEIGHT + keyword_score * KEYWORD_WEIGHT + category_bonus),
            3,
        )

        matched_caps = set(requirements.required_capabilities) & set(profile.capabilities)
        reason = _build_match_reason(profile.startup_name, matched_caps, same_category, relevance)

        scored_matches.append(StartupMatch(
            startup=profile, relevance_score=relevance,
            keyword_match_score=keyword_score, semantic_match_score=semantic_score,
            match_reason=reason,
        ))

    trusted = [m for m in scored_matches if m.startup.guardpulse_score >= trust_threshold]
    filtered_out = len(scored_matches) - len(trusted)
    print(f"  Trust Filter: {len(trusted)}/{len(scored_matches)} candidates "
          f"meet the {trust_threshold} score threshold ({filtered_out} filtered out)")

    trusted.sort(key=lambda m: m.relevance_score, reverse=True)
    top_matches = trusted[:top_k]

    print(f"  [bold green]✓ Returning top {len(top_matches)} match(es)[/bold green]")

    return MatchmakingResult(
        problem=problem_text, requirements=requirements, matches=top_matches,
        total_candidates=len(scored_matches), total_after_trust_filter=len(trusted),
        trust_threshold=trust_threshold,
    )


def print_match_report(result: MatchmakingResult):
    """Pretty-print a MatchmakingResult to the terminal."""
    print(f"\n[bold]{'━'*54}[/bold]")
    print(f"[bold]     GUARDPULSE MATCHMAKING REPORT[/bold]")
    print(f"[bold]{'━'*54}[/bold]")
    print(f"  Problem    : {result.problem}")
    print(f"  Category   : {result.requirements.category}")
    print(f"  Looking for: {', '.join(result.requirements.required_capabilities)}")
    print(f"  Candidates : {result.total_candidates} found, "
          f"{result.total_after_trust_filter} passed trust filter "
          f"(score >= {result.trust_threshold})")

    if not result.matches:
        print(f"\n  [yellow]No matches found.[/yellow]")
        if result.total_candidates > 0 and result.total_after_trust_filter == 0:
            print(f"  [yellow]Candidates exist but none meet the trust threshold. "
                  f"Lower it with --threshold or improve startup scores.[/yellow]")
        return

    print(f"\n[bold cyan]Top {len(result.matches)} Match(es)[/bold cyan]")
    t = Table(show_header=True, header_style="bold", box=None)
    t.add_column("Rank", width=5)
    t.add_column("Startup", width=22)
    t.add_column("Score", width=8)
    t.add_column("Relevance", width=10)
    t.add_column("Badge", width=18)

    for i, m in enumerate(result.matches, 1):
        badge_color = (
            "green"  if m.startup.badge.value == "ENTERPRISE_READY" else
            "yellow" if m.startup.badge.value == "CONDITIONAL" else "red"
        )
        t.add_row(
            str(i), m.startup.startup_name, f"{m.startup.guardpulse_score}/100",
            f"{m.relevance_score:.0%}", f"[{badge_color}]{m.startup.badge.value}[/{badge_color}]",
        )
    console.print(t)

    for i, m in enumerate(result.matches, 1):
        print(f"\n  [bold]{i}. {m.startup.startup_name}[/bold]")
        print(f"     {m.match_reason}")
        print(f"     Semantic: {m.semantic_match_score:.0%}  |  "
              f"Keyword: {m.keyword_match_score:.0%}  |  "
              f"Category: {m.startup.category}")