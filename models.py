"""
models.py — GuardPulse Phase 1 + Phase 2 + Phase 3 schemas.
Single source of truth. No duplicate class definitions.
"""

from enum import Enum
from typing import Optional
# pyrefly: ignore [missing-import]
from pydantic import BaseModel, Field


# ── Enums ─────────────────────────────────────────────────────────────────────

class ComplianceVerdict(str, Enum):
    PASS         = "PASS"
    FAIL         = "FAIL"
    PARTIAL      = "PARTIAL"
    INCONCLUSIVE = "INCONCLUSIVE"

class RiskLevel(str, Enum):
    LOW      = "LOW"
    MEDIUM   = "MEDIUM"
    HIGH     = "HIGH"
    CRITICAL = "CRITICAL"

class ChunkType(str, Enum):
    SECTION    = "section"
    CLAUSE     = "clause"
    DEFINITION = "definition"
    PREAMBLE   = "preamble"
    SCHEDULE   = "schedule"
    UNKNOWN    = "unknown"

class BadgeStatus(str, Enum):
    AWARDED     = "ENTERPRISE_READY"
    NOT_AWARDED = "NOT_READY"
    CONDITIONAL = "CONDITIONAL"


# ── Phase 1 — Ingestion ───────────────────────────────────────────────────────

class LegalChunk(BaseModel):
    chunk_id:       str
    law_id:         str
    law_name:       str
    jurisdiction:   str
    year:           int
    chunk_type:     ChunkType
    section_number: Optional[str] = None
    section_title:  Optional[str] = None
    text:           str
    token_count:    int
    tags:           list[str] = Field(default_factory=list)
    source_url:     str

class RetrievedContext(BaseModel):
    chunk_id:       str
    law_id:         str
    section_number: Optional[str]
    section_title:  Optional[str]
    text:           str
    score:          float
    tags:           list[str]


# ── Phase 1 — Audit ───────────────────────────────────────────────────────────

class PIIFinding(BaseModel):
    pii_type:        str
    context_snippet: str
    risk_level:      RiskLevel
    relevant_law:    str
    recommendation:  str

class ComplianceClause(BaseModel):
    clause_ref:     str
    clause_summary: str
    verdict:        ComplianceVerdict
    evidence:       str
    confidence:     float = Field(ge=0.0, le=1.0)

class ComplianceScorecard(BaseModel):
    target_document: str
    law_ids_checked: list[str]
    overall_verdict: ComplianceVerdict
    score:           float = Field(ge=0.0, le=100.0)
    clauses:         list[ComplianceClause]
    pii_findings:    list[PIIFinding]
    summary:         str
    recommendations: list[str]
    audited_by:      str = "GuardPulse Compliance Agent v1.0"


# ── Phase 2 — Auditor Agent ───────────────────────────────────────────────────

class LegalAuditResult(BaseModel):
    target_document: str
    laws_checked:    list[str]
    clauses:         list[ComplianceClause]
    pii_findings:    list[PIIFinding]
    legal_score:     float = Field(ge=0.0, le=100.0)
    overall_verdict: ComplianceVerdict
    summary:         str
    recommendations: list[str]


# ── Phase 2 — Tech Architect Agent ───────────────────────────────────────────

class SecurityFinding(BaseModel):
    finding_type:   str
    severity:       RiskLevel
    location:       str
    description:    str
    recommendation: str

class TechAuditResult(BaseModel):
    target_document:    str
    security_findings:  list[SecurityFinding]
    tech_score:         float = Field(ge=0.0, le=100.0)
    api_documented:     bool
    encryption_present: bool
    auth_present:       bool
    data_minimisation:  bool
    summary:            str
    recommendations:    list[str]


# ── Phase 2 — Critic Agent ────────────────────────────────────────────────────

class CitationCheck(BaseModel):
    original_claim: str
    citation_ref:   str
    is_valid:       bool
    correction:     Optional[str] = None
    confidence:     float = Field(ge=0.0, le=1.0)

class CriticResult(BaseModel):
    total_claims_checked: int
    valid_claims:         int
    invalid_claims:       int
    citation_checks:      list[CitationCheck]
    hallucination_rate:   float = Field(ge=0.0, le=1.0)
    critic_verdict:       str
    notes:                str


# ── Phase 2 — Final Report ────────────────────────────────────────────────────

class GuardPulseReport(BaseModel):
    startup_name:      str
    document_audited:  str
    legal_score:       float = Field(ge=0.0, le=100.0)
    tech_score:        float = Field(ge=0.0, le=100.0)
    critic_penalty:    float = Field(ge=0.0, le=100.0)
    guardpulse_score:  float = Field(ge=0.0, le=100.0)
    badge:             BadgeStatus
    legal_audit:       LegalAuditResult
    tech_audit:        TechAuditResult
    critic_result:     CriticResult
    executive_summary: str
    top_risks:         list[str]
    top_strengths:     list[str]
    next_steps:        list[str]
    audited_by:        str = "GuardPulse Swarm v2.0"


# ── Phase 3 — Startup Registry ────────────────────────────────────────────────

class StartupProfile(BaseModel):
    """
    A registered, audited startup eligible to appear in matchmaking results.
    Created by startup_registry.register_startup() after running the
    Phase 2 swarm and extracting a capability profile from the description.
    """
    startup_id:        str                    # slug, e.g. "acme-fintech"
    startup_name:       str
    description:        str                    # what they do, plain English
    category:           str                    # e.g. "fintech", "healthtech"
    capabilities:        list[str] = Field(default_factory=list)
    guardpulse_score:    float = Field(ge=0.0, le=100.0)
    badge:               BadgeStatus
    legal_score:         float = Field(ge=0.0, le=100.0)
    tech_score:          float = Field(ge=0.0, le=100.0)
    document_audited:    str
    registered_at:       str                   # ISO timestamp


# ── Phase 3 — Problem Intake ──────────────────────────────────────────────────

class ProblemRequirements(BaseModel):
    """Structured output of the Problem Intake Agent."""
    original_problem:       str
    category:                str
    required_capabilities:    list[str] = Field(default_factory=list)
    semantic_query:           str


# ── Phase 3 — Matchmaking ─────────────────────────────────────────────────────

class StartupMatch(BaseModel):
    startup:              StartupProfile
    relevance_score:       float = Field(ge=0.0, le=1.0)
    keyword_match_score:    float = Field(ge=0.0, le=1.0)
    semantic_match_score:   float = Field(ge=0.0, le=1.0)
    match_reason:           str

class MatchmakingResult(BaseModel):
    problem:                   str
    requirements:               ProblemRequirements
    matches:                    list[StartupMatch]
    total_candidates:            int
    total_after_trust_filter:    int
    trust_threshold:             float = 80.0