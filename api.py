# api.py
"""
Phase 3 REST API for n8n integration.

Endpoints:
- POST /api/match — Find startups for a CEO problem
- POST /api/audit — Trigger a new audit (calls orchestrator)
- GET /api/startups — List all verified startups
- GET /api/startups/{id} — Get startup details
- GET /api/stats — System statistics
"""

import os
import sys
import json
import shutil
import uuid
from typing import Optional, List
from pathlib import Path
from datetime import datetime

# Add the current directory to path for local imports
sys.path.insert(0, str(Path(__file__).parent))

# Try to import fastapi, but give helpful error if missing
try:
    # pyrefly: ignore [missing-import]
    from fastapi import FastAPI, HTTPException, BackgroundTasks, UploadFile, File, Form
    # pyrefly: ignore [missing-import]
    from fastapi.middleware.cors import CORSMiddleware
    # pyrefly: ignore [missing-import]
    from pydantic import BaseModel, Field
except ImportError as e:
    print(f"\n[red]Missing dependency: {e}[/red]")
    print("[yellow]Run: pip install fastapi uvicorn httpx pydantic[/yellow]")
    sys.exit(1)

# pyrefly: ignore [missing-import]
from rich import print

# Import local modules — use actual exports from the codebase
from matchmaking_engine import find_matches, print_match_report
from models import MatchmakingResult, GuardPulseReport, StartupProfile
from startup_registry import register_startup
from startup_store import search_startups, list_all_startups, store_startup, get_stats as startup_store_stats
from orchestrator import run_swarm
from models import BadgeStatus

app = FastAPI(title="GuardPulse Matchmaking API", version="3.0.0")

# Directories for the webhook flow (uploaded docs + saved JSON reports)
DATA_DIR = Path(__file__).parent / "data"
UPLOAD_DIR = DATA_DIR / "uploads"
REPORTS_DIR = DATA_DIR / "reports"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

# CORS for n8n and frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, restrict to n8n and your domains
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Request/Response Models ──────────────────────────────────────────────────

class MatchRequest(BaseModel):
    problem_text: str = Field(..., description="CEO's problem description")
    top_k: int = Field(5, ge=1, le=20, description="Number of matches to return")
    trust_threshold: Optional[float] = Field(None, ge=0, le=100, description="Override trust threshold")

class MatchResponse(BaseModel):
    success: bool
    matches: List[dict]
    summary: str
    problem_extracted: dict


class AuditRequest(BaseModel):
    startup_name: str = Field(..., description="Startup name")
    document_path: str = Field(..., description="Path to document to audit")
    description: str = Field(..., description="What the startup does (used for matchmaking)")
    asset_paths: Optional[List[str]] = Field(None, description="Additional assets (API docs, etc.)")


class AuditResponse(BaseModel):
    success: bool
    startup_id: str
    report: Optional[dict]
    registered: bool
    message: str


class StartupResponse(BaseModel):
    id: str
    name: str
    description: str
    guardpulse_score: float
    badge: str
    category: str
    capabilities: List[str]
    registered_at: str


# ── API Endpoints ────────────────────────────────────────────────────────────

@app.post("/webhook/audit")
async def webhook_audit(
    startup_name: str = Form(...),
    contact_email: str = Form(...),
    document: UploadFile = File(...),
):
    """
    This is what n8n_guardpulse.json actually calls (n8n uploads the form's
    file directly — it has no access to a path on this server's disk, which
    is why /api/audit's document_path approach doesn't work for the n8n flow).

    Runs the full swarm synchronously. n8n's HTTP node already has a 300s
    timeout set, which covers the ~2 min swarm runtime — but if your audits
    start taking longer, this should move to BackgroundTasks + a polling
    /api/reports/{id} endpoint instead of a blocking request.
    """
    try:
        # Save the uploaded file to disk so orchestrator.run_swarm (which
        # expects a path) can read it.
        ext = Path(document.filename or "upload.txt").suffix or ".txt"
        safe_name = f"{uuid.uuid4().hex}{ext}"
        doc_path = UPLOAD_DIR / safe_name
        with open(doc_path, "wb") as f:
            shutil.copyfileobj(document.file, f)

        report = run_swarm(startup_name=startup_name, doc_path=str(doc_path))

        report_id = uuid.uuid4().hex[:10]
        report_dict = report.model_dump(mode="json")
        report_dict["contact_email"] = contact_email
        report_dict["submitted_at"] = datetime.utcnow().isoformat()
        report_dict["report_id"] = report_id
        report_dict["is_enterprise_ready"] = report.badge == BadgeStatus.AWARDED
        report_dict["hallucination_rate"] = report.critic_result.hallucination_rate
        report_dict["report_url"] = f"/api/reports/{report_id}"

        with open(REPORTS_DIR / f"{report_id}.json", "w") as f:
            json.dump(report_dict, f, indent=2, default=str)

        # NOTE: this does not call register_startup(), so the audited
        # startup won't show up in /api/match results yet. I don't have
        # startup_registry.py's signature to wire that safely — flagging
        # rather than guessing. Easy to add once you share that file.
        return report_dict

    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/reports/{report_id}")
async def get_report(report_id: str):
    """Fetch a previously generated audit report by id (used as report_url)."""
    report_path = REPORTS_DIR / f"{report_id}.json"
    if not report_path.exists():
        raise HTTPException(status_code=404, detail="Report not found")
    with open(report_path) as f:
        return json.load(f)


@app.get("/")
async def root():
    return {
        "service": "GuardPulse Matchmaking Engine",
        "version": "3.0.0",
        "endpoints": [
            "POST /api/match",
            "POST /api/audit",
            "POST /webhook/audit",
            "GET /api/reports/{report_id}",
            "GET /api/startups",
            "GET /api/startups/{id}",
            "GET /api/stats",
        ]
    }


@app.post("/api/match", response_model=MatchResponse)
async def match(request: MatchRequest):
    """Match startups to a CEO's problem."""
    try:
        threshold = request.trust_threshold if request.trust_threshold is not None else 80.0
        result = find_matches(
            problem_text=request.problem_text,
            top_k=request.top_k,
            trust_threshold=threshold,
        )

        matches_data = []
        for m in result.matches:
            matches_data.append({
                "startup": {
                    "id": m.startup.startup_id,
                    "name": m.startup.startup_name,
                    "description": m.startup.description[:200],
                    "guardpulse_score": m.startup.guardpulse_score,
                    "badge": m.startup.badge.value,
                    "category": m.startup.category,
                    "capabilities": m.startup.capabilities[:5],
                },
                "relevance_score": m.relevance_score,
                "semantic_match_score": m.semantic_match_score,
                "keyword_match_score": m.keyword_match_score,
                "match_reason": m.match_reason,
            })

        problem_extracted = {
            "category": result.requirements.category,
            "required_capabilities": result.requirements.required_capabilities,
            "semantic_query": result.requirements.semantic_query,
        }

        summary = (
            f"Found {len(result.matches)} match(es) out of "
            f"{result.total_candidates} candidates "
            f"({result.total_after_trust_filter} passed trust filter >= {result.trust_threshold})."
        )

        return MatchResponse(
            success=True,
            matches=matches_data,
            summary=summary,
            problem_extracted=problem_extracted,
        )

    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/audit", response_model=AuditResponse)
async def audit(request: AuditRequest, background_tasks: BackgroundTasks):
    """
    Trigger a new audit for a startup.
    Runs the swarm, then registers the startup for matchmaking.
    """
    try:
        # Check if file exists
        if not os.path.exists(request.document_path):
            raise HTTPException(status_code=404, detail=f"Document not found: {request.document_path}")

        # Run the full registration flow (swarm audit + capability extraction + store)
        profile = register_startup(
            startup_name=request.startup_name,
            doc_path=request.document_path,
            description=request.description,
            asset_paths=request.asset_paths,
        )

        return AuditResponse(
            success=True,
            startup_id=profile.startup_id,
            report=None,  # Full report is large; omit from API response
            registered=True,
            message=(
                f"Audit complete. Score: {profile.guardpulse_score}/100. "
                f"Badge: {profile.badge.value}"
            ),
        )

    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/startups", response_model=List[StartupResponse])
async def get_startups(
    min_score: float = 0,
    badge: Optional[str] = None,
    category: Optional[str] = None,
    limit: int = 50,
):
    """List all verified startups with filters."""
    try:
        startups = list_all_startups()

        # Apply filters
        if min_score > 0:
            startups = [s for s in startups if s.guardpulse_score >= min_score]
        if badge:
            startups = [s for s in startups if s.badge.value == badge]
        if category:
            startups = [s for s in startups if s.category.lower() == category.lower()]

        # Sort by score descending
        startups.sort(key=lambda s: s.guardpulse_score, reverse=True)
        startups = startups[:limit]

        return [
            StartupResponse(
                id=s.startup_id,
                name=s.startup_name,
                description=s.description[:300],
                guardpulse_score=s.guardpulse_score,
                badge=s.badge.value,
                category=s.category,
                capabilities=s.capabilities[:10],
                registered_at=s.registered_at or "",
            )
            for s in startups
        ]
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/startups/{startup_id}")
async def get_startup(startup_id: str):
    """Get detailed startup information."""
    try:
        startups = list_all_startups()
        match = next((s for s in startups if s.startup_id == startup_id), None)
        if not match:
            raise HTTPException(status_code=404, detail="Startup not found")

        return {
            "id": match.startup_id,
            "name": match.startup_name,
            "description": match.description,
            "guardpulse_score": match.guardpulse_score,
            "badge": match.badge.value,
            "category": match.category,
            "capabilities": match.capabilities,
            "legal_score": match.legal_score,
            "tech_score": match.tech_score,
            "document_audited": match.document_audited,
            "registered_at": match.registered_at,
        }
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/stats")
async def stats():
    """Get system statistics."""
    try:
        s = startup_store_stats()
        return {
            "startup_registry": s,
            "status": "healthy",
            "version": "3.0.0",
        }
    except Exception as e:
        return {
            "error": str(e),
            "status": "error",
        }


if __name__ == "__main__":
    # pyrefly: ignore [missing-import]
    import uvicorn
    print("\n[bold green]🚀 GuardPulse Matchmaking API Starting...[/bold green]")
    print("  API Docs: http://localhost:8000/docs")
    print("  Endpoint: http://localhost:8000/api/match")
    print("  Press Ctrl+C to stop\n")
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)