# GuardPulse — Docker + n8n Setup

## What changed (files in this drop)

| File | Change |
|---|---|
| `api.py` | Added `POST /webhook/audit` (multipart file upload — this is what n8n actually calls) and `GET /api/reports/{id}`. Updated root endpoint list. |
| `run_api.py` | Host binding fixed: `127.0.0.1` → `0.0.0.0` (required for Docker), reload now toggled by `API_RELOAD` env var instead of hardcoded `True`. |
| `n8n_guardpulse.json` | URL changed from `http://localhost:8000/webhook/audit` → `http://api:8000/webhook/audit` (service name, required once n8n and the API are separate containers on the same Docker network). |
| `Dockerfile.api` | New. Builds the FastAPI backend. |
| `Dockerfile.streamlit` | New — **unverified**, since I don't have `app.py`. Assumes `streamlit run app.py`. |
| `docker-compose.yml` | New. Wires `api` + `ui` + `n8n` on one network. |

## Why `/webhook/audit` had to be added

Your `n8n_guardpulse.json` workflow uploads a file (`multipart-form-data`, `document` as `formBinaryData`) straight from the intake form. The old `/api/audit` endpoint expects a `document_path` string — a path on the **server's own disk** — which n8n has no way to provide, since the file lives in n8n's workflow execution, not on your API server. The new endpoint accepts the actual upload, saves it server-side, then runs `orchestrator.run_swarm()` directly (not `register_startup()`, see caveat below) and returns the exact fields your Slack/email/Notion nodes already reference: `guardpulse_score`, `badge`, `is_enterprise_ready`, `legal_score`, `tech_score`, `hallucination_rate`, `executive_summary`, `next_steps`, `contact_email`, `report_id`, `report_url`, `submitted_at`.

## Known gaps — flagging rather than guessing

1. **Startup registration not wired into `/webhook/audit`.** I didn't call `register_startup()` there because I don't have `startup_registry.py` or `models.py`, so I can't confirm the exact `StartupProfile` fields/signature without guessing. Today, an audit run via the n8n flow won't show up in `/api/match` results. Send `startup_registry.py` and `models.py` and I'll wire it in properly.
2. **`Dockerfile.streamlit` is unverified.** If `app.py` calls `orchestrator`/`matchmaking_engine` functions directly (in-process) rather than hitting the API over HTTP, it'll still run fine in its own container, but you won't actually be testing the "live API" path you asked about. Send `app.py` and I'll confirm or rewrite the relevant calls to go through `http://api:8000/...`.
3. **Badge naming inconsistency.** Your README documents badges as `ENTERPRISE_READY` / `CONDITIONAL` / `NOT_READY`, but `orchestrator.py` actually uses `BadgeStatus.AWARDED` / `CONDITIONAL` / `NOT_AWARDED`. Not a bug, just means your n8n Slack/email text will show "AWARDED" not "ENTERPRISE_READY" unless you want me to rename the enum.
4. **`n8n.json` (the older matchmaking workflow) has its own mismatches** — it expects `match_reasons` (plural array), `contact_email`, and `website` on each match object, but `/api/match` in `api.py` only returns `match_reason` (singular) and no `contact_email`/`website`. I left this file untouched since `n8n_guardpulse.json` is the one your README's Phase 5 plan describes — let me know if you still need `n8n.json` working too.

## How to run it

```bash
cd guardpulse
cp .env.example .env   # fill in GROQ_API_KEY etc.
docker compose build
docker compose up -d
```

- API: http://localhost:8000/docs
- Streamlit UI: http://localhost:8501
- n8n: http://localhost:5678 (first run asks you to create an owner account)

### Import the workflow into n8n
1. Open http://localhost:5678
2. Menu → **Import from File** → select `n8n_guardpulse.json`
3. Add credentials for Slack / Gmail / Notion nodes (or delete those nodes if you just want to test the core audit call for now)
4. Activate the workflow, copy the webhook's **Production URL**

### Test it without filling in Slack/Gmail/Notion creds
```bash
curl -X POST http://localhost:8000/webhook/audit \
  -F "startup_name=TestCo" \
  -F "contact_email=test@example.com" \
  -F "document=@sample_docs/sample_policy.txt"
```
This hits your new endpoint directly — confirms the swarm + response shape work before you debug n8n credentials on top.

### Logs / rebuild after edits
```bash
docker compose logs -f api
docker compose up -d --build api   # rebuild just one service
```