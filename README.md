# GuardPulse Connect

**Enterprise-Ready AI Compliance Marketplace**

An Agentic RAG system that audits startup documents against Indian and EU data protection laws, scores them on a 0–100 trust scale, and awards an **Enterprise-Ready Badge** to startups that pass. Built as a multi-agent AI swarm in pure Python.

---

## What It Does

A startup uploads their Privacy Policy or technical document. GuardPulse runs three AI agents in sequence:

1. **Auditor Agent** — checks the document against DPDP Act 2023 (8 clauses) and EU AI Act 2024 (4 clauses) using real law text retrieved from ChromaDB
2. **Tech Architect Agent** — scans for security risks, PII exposure, missing auth, encryption gaps
3. **Critic Agent** — verifies every legal citation against the actual law to catch hallucinations

The orchestrator merges all three scores into a final **GuardPulse Score** and awards a badge:

| Score | Badge |
|-------|-------|
| ≥ 80 | `ENTERPRISE_READY` |
| 60–79 | `CONDITIONAL` |
| < 60 | `NOT_READY` |

---

## Current Stack

| Component | Tool | Notes |
|-----------|------|-------|
| LLM | **Groq API** (Llama 3.3 70B) | Free tier · 30 req/min · ~2 min full swarm |
| Embeddings | `sentence-transformers` | `all-MiniLM-L6-v2` · local · no API key |
| Vector DB | **ChromaDB** | Fully local · persists to disk |
| PDF Parsing | `pdfplumber` + `html2text` | PDF and HTML legal docs |
| Validation | `pydantic` | Strict schemas — bad AI output caught immediately |
| CLI | `rich` | Coloured terminal output |
| Orchestration | Pure Python | No LangChain/CrewAI overhead |

> **LLM provider history:** Started with Ollama local (40 min/swarm on CPU) → switched to Gemini Flash (hit 15 req/min free tier limit) → settled on **Groq** (30 req/min free, fastest inference available, ~2 min full swarm).

---

## Project Structure

```
guardpulse/
├── .env                          ← API keys and config (never commit)
├── .env.example                  ← template
├── requirements.txt
│
├── models.py                     ← Pydantic schemas (single source of truth)
├── fetcher.py                    ← downloads DPDP Act + EU AI Act from public URLs
├── chunker.py                    ← splits law by §Section not word count
├── vector_store.py               ← ChromaDB + local sentence-transformer embeddings
├── compliance_agent.py           ← Phase 1 single-agent audit
├── orchestrator.py               ← Phase 2 swarm coordinator + scoring
├── main.py                       ← CLI entry point
│
├── agents/
│   ├── utils.py                  ← shared LLM caller (Groq/OpenRouter/Gemini)
│   ├── auditor_agent.py          ← checks DPDP + EU AI Act via ChromaDB RAG
│   ├── tech_agent.py             ← security risk scanner
│   └── critic_agent.py           ← hallucination checker
│
├── data/
│   └── chroma_db/                ← auto-created · 240 vectors (44 DPDP + 196 EU AI)
│
└── sample_docs/
    ├── sample_policy.txt         ← test privacy policy
    └── reports/                  ← JSON scorecards saved here automatically
```

---

## Setup

### 1. Get a free Groq API key
Go to [console.groq.com](https://console.groq.com) → sign up → API Keys → Create key. Free, instant, no card needed.

### 2. Install packages
```bash
pip install chromadb sentence-transformers pdfplumber python-dotenv pydantic rich requests html2text groq
```

### 3. Configure `.env`
```env
GROQ_API_KEY=your_groq_key_here
GROQ_MODEL=llama-3.3-70b-versatile
CHROMA_DB_PATH=./data/chroma_db
```

### 4. Ingest legal documents (run once)
```bash
python main.py ingest
```
Downloads DPDP Act 2023 (PDF) and EU AI Act 2024 (HTML from EUR-Lex), chunks by §Section, embeds locally, stores 240 vectors in ChromaDB.

```bash
python main.py ingest DPDP_2023        # ingest one law only
python main.py ingest EU_AI_ACT_2024   # ingest EU Act only
```

### 5. Run the Phase 2 multi-agent swarm
```bash
python main.py swarm "MyStartup" sample_docs/sample_policy.txt
```

### 6. Run a Phase 1 single-agent audit
```bash
python main.py audit sample_docs/sample_policy.txt
python main.py audit myfile.pdf --law EU_AI_ACT_2024
```

### 7. Check database stats
```bash
python main.py stats
```

---

## How the Swarm Works

```
Startup document (PDF or TXT)
           │
           ▼
    orchestrator.py
           │
     ┌─────┴──────────────────────┐
     ▼                            ▼
AuditorAgent              TechArchitectAgent
     │                            │
     ├─ ChromaDB RAG              ├─ Security risk scan
     │  (8 DPDP queries +         ├─ Boolean checks
     │   4 EU AI queries)         │  (encryption, auth,
     ├─ Clause check              │   API docs, data min)
     │  PASS/FAIL/PARTIAL         └─ Dedup findings
     └─ PII detection
           │
           ▼
      CriticAgent
           │
           ├─ Semantic keyword search per clause
           └─ Flags hallucinations (confidence > 0.75)
                      │
                      ▼
             orchestrator.py
                      │
                      ├─ Score formula:
                      │   (legal × 0.50) + (tech × 0.35) + (critic_bonus × 0.15)
                      ├─ Hard cap at 55 if CRITICAL security finding
                      └─ Awards badge + executive summary
                                 │
                                 ▼
                    GuardPulseReport (CLI output + JSON saved)
```

---

## Score Formula

```
GuardPulse Score = (Legal Score  × 0.50)
                 + (Tech Score   × 0.35)
                 + (Critic Bonus × 0.15)

Critic Bonus = 100 × (1 − hallucination_rate)
```

Any **CRITICAL** security finding hard-caps the final score at 55.

---

## Sample Output

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
       GUARDPULSE ENTERPRISE REPORT v2.0
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Startup  : MyStartup
  Score    : 76.4/100
  Badge    : CONDITIONAL

  Legal : 67.5/100  |  Tech : 79.0/100  |  Hallucinations : 0.0%

Legal Clauses (12)
  PASS         DPDP §5    Privacy notice
  PARTIAL      DPDP §6    Valid consent
  PASS         DPDP §8    Data retention
  FAIL         DPDP §16   Data breach notification
  INCONCLUSIVE EU AI Art.9 Risk management

Security Findings (4)
  MEDIUM  BROAD_DATA_COLLECTION  Collects extensive personal data
  HIGH    INSECURE_STORAGE       Backup copies retained 12 months
  MEDIUM  MISSING_CONSENT        No explicit user consent

Critic Report
  Verdict : RELIABLE | Claims : 12 | Hallucination : 0.0%
```

---

## All Changes Made During Development

| # | What changed | Before | After | Why |
|---|---|---|---|---|
| 1 | LLM engine | Ollama local (3B) | Groq API (70B) | 40 min → 2 min swarm |
| 2 | LLM SDK | `ollama` + `google.generativeai` (deprecated) | `groq` OpenAI-compatible | rate limits + deprecation warning |
| 3 | Agent count | 1 agent | 4 agents (Auditor + Tech + Critic + Orchestrator) | Phase 2 multi-agent swarm |
| 4 | Laws audited | DPDP 2023 only | DPDP 2023 + EU AI Act 2024 | broader compliance coverage |
| 5 | EU Act URL | artificialintelligenceact.eu (8K chars, stub page) | eur-lex.europa.eu (597K chars, full law) | was fetching homepage not the actual act |
| 6 | EU Act min_chars | 500 chars | 50,000 chars | stub page passed the old threshold |
| 7 | Vector count | 44 (DPDP only) | 240 (44 DPDP + 196 EU AI Act) | EU Act now properly chunked |
| 8 | Boolean prompt | Returns YES/NO (invalid JSON) | Returns true/false (valid JSON) | Llama 70B returns YES/NO by default |
| 9 | Summary LLM call | `call_llm()` (validates JSON) | `call_llm_text()` (plain text) | summary is prose, not JSON |
| 10 | Critic search query | Clause ref string e.g. "DPDP §5" | Semantic keywords e.g. "privacy notice obligations" | was retrieving wrong ChromaDB sections |
| 11 | Hallucination threshold | 0.60 confidence | 0.75 confidence | too many false positives at 0.6 |
| 12 | Duplicate findings | No dedup | `_dedup_findings()` in tech_agent | NO_RATE_LIMITING appeared twice |
| 13 | Summary prompt | No constraints | 5 strict rules, PASS-list grounded | was inventing strengths not in audit |
| 14 | Multi-provider support | Gemini only | Groq → OpenRouter → Gemini (auto-detect) | flexibility for free tier switching |
| 15 | `call_llm` fallback | Silent `[]` return | Logs raw response preview on failure | invisible failures were hard to debug |

---

## Troubleshooting

**ChromaDB dimension mismatch**
```bash
rmdir /s /q data\chroma_db    # Windows
rm -rf data/chroma_db         # Mac/Linux
python main.py ingest
```

**Groq rate limit errors**
Free tier is 30 req/min. The swarm makes ~12 calls. If you hit limits, wait 60 seconds and re-run.

**EU AI Act fetch fails**
EUR-Lex can be slow. Re-run `python main.py ingest EU_AI_ACT_2024` — the fallback URL kicks in automatically.

**HF_TOKEN warning on every run**
Harmless. Add this to `.env` to silence it:
```env
HF_TOKEN=
```

**0 clauses parsed**
Usually means the LLM returned non-JSON. The raw response preview prints in the terminal. Check `GROQ_API_KEY` is set correctly in `.env`.

---

## Alternative LLM Providers

`agents/utils.py` auto-detects which key is present. Priority: Groq → OpenRouter → Gemini. No code changes needed — just update `.env`.

```env
# Option 1: Groq (recommended — 30 req/min free, fastest inference)
GROQ_API_KEY=your_key
GROQ_MODEL=llama-3.3-70b-versatile

# Option 2: OpenRouter (50+ free models available)
OPENROUTER_API_KEY=your_key
OPENROUTER_MODEL=meta-llama/llama-3.3-70b-instruct:free

# Option 3: Gemini Flash (15 req/min free — hits limits on full swarm)
GEMINI_API_KEY=your_key
GEMINI_MODEL=gemini-1.5-flash
```

---

## Laws Covered

| Law | Jurisdiction | Chunks in DB | Clauses checked |
|-----|-------------|-------------|-----------------|
| Digital Personal Data Protection Act 2023 | India | 44 | §5 §6 §8 §9 §11 §12 §13 §16 |
| EU Artificial Intelligence Act 2024 | European Union | 196 | Art.5 Art.9 Art.13 Art.14 |

---

## Roadmap

### Phase 3 — Matchmaking Engine (next)
- CEO describes a business problem in plain English
- System converts it to structured technical requirements
- Hybrid search (keyword + semantic) over verified startup registry in ChromaDB
- Trust Filter — only returns startups with GuardPulse score > 80
- Backend API returning top 3 verified startups per enterprise problem

### Phase 4 — Enterprise Portal
- Streamlit dashboard with Enterprise-Ready Badge display
- Mock sandbox — CEOs safely test startup APIs
- Automated Pilot Proposal document generation
- NDA + API key handshake flow between CEO and startup

### Phase 5 — Optimization + HITL + n8n
- Human-in-the-Loop dashboard for manual legal overrides by compliance officers
- RAG latency optimization for real-time querying
- **n8n integration** — form submit triggers full GuardPulse swarm automatically

### n8n Integration Plan (Phase 5)

GuardPulse exposes a REST API. n8n sits in front as the workflow trigger layer:

```
Startup submits Google Form / Typeform
           │
           ▼  webhook trigger
       n8n workflow
           │
           ├─► HTTP node → POST /api/audit → GuardPulse swarm
           ├─► Wait for JSON result
           ├─► Gmail node → email scorecard PDF to startup
           ├─► Notion/Airtable node → log to CRM
           └─► Slack node → alert enterprise team if score > 80
```

This uses n8n for what it is best at (triggers, notifications, CRM integration) and GuardPulse for what it is best at (AI reasoning, legal analysis, hallucination checking).

---

## For Prof. Animesh Giri — PES University

GuardPulse Connect is an **agentic AI system** built in the spirit of what you described — AI agents that do real work autonomously. It goes beyond simple n8n/Node-RED workflows:

- **Multi-agent orchestration** in pure Python (Auditor → Tech → Critic → Orchestrator)
- **RAG with legal grounding** — agents retrieve real law text before making claims
- **Hallucination detection** — the Critic agent cross-checks every citation
- **Enterprise-grade schemas** — Pydantic ensures every AI output conforms to a strict legal data model

Phase 5 will add **n8n as the workflow trigger layer** on top of the AI backend — demonstrating exactly the kind of human-AI-automation integration your projects are exploring.