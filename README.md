# Quantum Forgers — Compliance Auditor

**SIH26155 (NTRO · Blockchain & Cybersecurity) prototype.**
AI-augmented, vendor-agnostic network configuration compliance auditor.

**Differentiator vs Tufin / FireMon / Titania Nipper:** it can flag and learn to
parse configuration constructs from a vendor it has never seen, live, via a
human-confirmed training loop — no code redeploy, no engineering ticket.

## What it does

1. **Upload** a device config file (`.cfg` / `.txt`) — no live device polling.
2. **Normalize** it into a vendor-agnostic `NormalizedConfig` schema
   (interfaces, ACLs, auth settings, protocols, VTY lines, …).
3. **Audit** against hand-encoded CIS Benchmark rules → pass / fail / needs-review
   findings with exact remediation CLI (advisory text only).
4. **Learn:** any line the parser can't classify lands in the *unmapped lines*
   panel. An LLM (LM Studio, local) **suggests** a category — advisory only.
   A human confirms/edits/rejects in one click; confirmed patterns are cached
   in SQLite and **immediately** resolve the same construct in future audits,
   even from new configs — without any code change.
5. **Report:** one-click PDF with findings, severities, remediation CLI, and a
   visible AI-suggested vs human-confirmed audit trail.

## Tech stack

| Layer | Choice |
|---|---|
| Backend | Python 3.11+ · FastAPI · Pydantic |
| Parsers | Regex-based, per-vendor, shared `BaseParser` interface |
| Rules | CIS-inspired JSON (Cisco IOS: 22 rules · Juniper SRX: 6 rules) |
| Rule cache | SQLite (`rule_cache.db`, inspectable) |
| AI layer | LM Studio (OpenAI-compatible, localhost:1234) — few-shot suggestion only |
| Frontend | React + Vite + Tailwind CSS |
| Reporting | ReportLab (PDF) |

## Run it

```bash
# 1) Backend
cd backend
pip install -r requirements.txt
uvicorn app.main:app --port 8000

# 2) Frontend (new terminal)
cd frontend
npm install
npm run dev          # http://localhost:5173 (proxies /api -> :8000)
```

Optional (AI suggestions): start **LM Studio**, load a model (e.g.
`google/gemma-4-e4b`), keep the server on port 1234. If LM Studio is off or no
model is loaded, audits still work — unmapped lines simply stay `unmapped`
until a human categorizes them manually.

## Demo script (the money shot)

1. Upload `backend/sample_configs/unknown_vendor_sample.cfg` — a **synthetic
   vendor** ("NOVUS-OS") whose syntax is hardcoded nowhere in the codebase.
   → API returns 422: *"No parser recognized this config format."*
2. Upload the Juniper SRX sample → full audit works end-to-end (schema proves
   it generalizes across vendor syntaxes).
3. Upload `cisco_ios_sample_2.cfg` (deliberately non-compliant: Telnet, weak
   auth, HTTP server, default SNMP community) → 19 findings.
4. In the *Unmapped Lines* panel, confirm an AI-suggested (or pick manually)
   category for e.g. `enable password weakpassword123`.
5. Click **Re-run Audit** (or upload any other config with `enable password …`)
   → the construct is now `human_confirmed` via the cached pattern
   `enable password #` — **learned live, no code touched**.

## Scope guarantees

- File upload only — **no SSH/Netmiko/NAPALM** live device polling.
- **No auto-remediation / config push** — remediation output is advisory text.
- UI copy never claims "supports all vendors" — it is *extensible to new
  vendors via human-in-the-loop mapping*.

## Repo layout

```
backend/
  app/
    main.py              FastAPI endpoints (audit, train confirm/reject, PDF)
    models.py            Pydantic: NormalizedConfig, Rule, Finding, UnmappedLine
    parsers/
      base_parser.py     shared interface + vendor autodetection
      cisco_ios.py       Cisco IOS parser
      juniper_srx.py     Juniper SRX (set-format) parser
    rules/
      cis_cisco_ios.json  22 CIS-inspired rules
      cis_juniper_srx.json
    rule_engine.py       runs NormalizedConfig against rule JSON
    training_loop.py     unmapped detection, LM Studio suggestion, SQLite cache
    report_generator.py  ReportLab PDF builder
  sample_configs/        compliant / non-compliant / unknown-vendor samples
frontend/                React + Vite + Tailwind (upload, findings, training UI)
ARCHITECTURE.md
```

## Note on CIS citations

Rule section titles use real CIS Cisco IOS Benchmark language; entries flagged
`"citation_confidence": "verify"` in `cis_cisco_ios.json` must be checked
against the exact Benchmark PDF version before competition submission.
