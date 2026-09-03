# Architecture — Quantum Forgers Compliance Auditor

*(SIH26155 prototype · max 2 pages)*

## 1. Design goal

Vendor-agnostic compliance auditing with a **live learning loop**: an operator
teaches the tool an unrecognized config construct once, and every future audit
understands it — no code change, no redeploy. AI (local LLM via LM Studio)
participates **only as a suggester**; compliance verdicts are always derived
from human-confirmed mappings or hardcoded vendor parsers.

## 2. Data flow

```
 .cfg/.txt upload ──► vendor autodetect (can_parse probes)
        │                   │ unknown → HTTP 422, surfaced for training loop
        ▼                   ▼
   vendor parser ──► NormalizedConfig (Pydantic)          [Step 1-2]
        │               • interfaces, acl_rules, auth, protocols, vty…
        │               • unmapped_lines[]  ← anything not confidently classified
        ▼
   rule engine ◄── cis_<vendor>.json (CIS Benchmark rules) [Step 3]
        │
        ▼
   AuditReport (findings: pass/fail/needs_review + remediation CLI)
        │
        ├──► PDF report (ReportLab) with AI* / HC* audit flags [Step 5]
        └──► training loop                                    [Step 4]
```

**Training loop (the differentiator):**

1. Parse detects `unmapped_lines` — never silently dropped or guessed.
2. Resolution order per line: **(a)** SQLite rule cache of human-confirmed
   `command_pattern → category` mappings (generalized patterns, e.g.
   `ntp server #`, `enable password #`); **(b)** optional LLM few-shot
   classification → status `ai_suggested` with confidence — *suggestion only*.
3. Admin UI: see raw line + AI suggestion → **confirm / edit category /
   reject** in one click.
4. Confirm → pattern written to `rule_cache.db`, status `human_confirmed`.
5. Re-running the parser (same **or new** config) resolves matching lines via
   the cache — proved by the synthetic `unknown_vendor_sample.cfg`, whose
   syntax exists nowhere in the codebase.

## 3. Why the schema generalizes

`NormalizedConfig` models firewall/router/switch **semantics** (auth settings,
enabled protocols, ACL intent, management-line policy), not vendor syntax.
Cisco IOS (context-block, indentation) and Juniper SRX (flat `set` hierarchy)
parsers both emit the identical model through a shared `BaseParser` interface,
which is all a new vendor needs to implement. Unrecognized constructs are a
first-class citizen (`unmapped_lines`) rather than an error.

## 4. Trust boundaries (auditability)

- LLM output is never applied to a verdict; it only annotates a suggestion.
- Findings touched by AI-suggested vs human-confirmed mappings carry visible
  `AI*` / `HC*` flags in the PDF and API response.
- Rejected AI suggestions are logged (`suggestions_log`) — a full audit trail.
- Rule cache is plain SQLite — inspectable, exportable, portable.

## 5. Deliberate scope cuts

- No live device polling (SSH/Netmiko/NAPALM) — file upload only.
- No auto-remediation: remediation CLI is advisory text, nothing is pushed.
- No "supports all vendors" claims: *extensible via human-in-the-loop mapping*.

## 6. Components

| Component | File(s) | Responsibility |
|---|---|---|
| Schema | `app/models.py` | Pydantic models shared by every layer |
| Parsers | `app/parsers/` | Vendor-specific text → NormalizedConfig |
| Rule engine | `app/rule_engine.py` + `app/rules/*.json` | CIS-style checks → Findings |
| Training loop | `app/training_loop.py` + `rule_cache.db` | Pattern learning & caching |
| API | `app/main.py` | FastAPI: audit, train/confirm, train/reject, PDF |
| Reports | `app/report_generator.py` | ReportLab PDF with audit flags |
| Frontend | `frontend/src/` | Upload, findings table, training UI, PDF download |
