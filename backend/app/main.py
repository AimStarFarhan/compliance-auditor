"""Quantum Forgers — Compliance Auditor API (SIH26155 prototype).

File-upload only. No live device polling. AI suggestions are advisory only;
compliance verdicts for previously-unmapped constructs require human confirmation.
"""
import io
import json
import os
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from app.models import AuditReport, Finding, NormalizedConfig, UnmappedStatus
from app.parsers.base_parser import detect_vendor
from app.parsers.cisco_ios import CiscoIOSParser
from app.parsers.juniper_srx import JuniperSRXParser
from app.report_generator import generate_pdf
from app.rule_engine import load_rules, run_audit
from app import training_loop

app = FastAPI(title="Quantum Forgers — Compliance Auditor", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

PARSERS = [CiscoIOSParser(), JuniperSRXParser()]


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/api/ai/status")
def ai_status() -> dict:
    """Check whether LM Studio (local OpenAI-compatible server) is reachable."""
    import httpx

    try:
        r = httpx.get("http://localhost:1234/v1/models", timeout=3.0)
        models = [m.get("id") for m in r.json().get("data", [])]
        return {"online": True, "models": models}
    except Exception:
        return {"online": False, "models": []}


SAMPLES_DIR = Path(__file__).parent.parent / "sample_configs"

SAMPLE_DESCRIPTIONS = {
    "cisco_ios_sample_1.cfg": "Cisco IOS — hardened device (expect all-pass)",
    "cisco_ios_sample_2.cfg": "Cisco IOS — deliberately non-compliant (Telnet, weak auth, HTTP)",
    "juniper_srx_sample.cfg": "Juniper SRX — second vendor, end-to-end audit",
    "unknown_vendor_sample.cfg": "NOVUS-OS — synthetic unknown vendor (training-loop demo)",
}


@app.get("/api/samples")
def list_samples() -> dict:
    items = []
    for f in sorted(SAMPLES_DIR.glob("*.cfg")):
        items.append({
            "name": f.name,
            "description": SAMPLE_DESCRIPTIONS.get(f.name, "sample config"),
            "size": f.stat().st_size,
        })
    return {"samples": items}


@app.get("/api/samples/{name}/download")
def download_sample(name: str) -> StreamingResponse:
    if "/" in name or "\\" in name or ".." in name:
        raise HTTPException(400, "invalid sample name")
    p = SAMPLES_DIR / name
    if not p.exists():
        raise HTTPException(404, "sample not found")
    return StreamingResponse(
        io.BytesIO(p.read_bytes()),
        media_type="text/plain",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )


@app.get("/api/cache/patterns")
def cache_patterns() -> dict:
    """List all human-confirmed command patterns (rule cache contents)."""
    from app.training_loop import _connect

    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT pattern, category, confirmed_by, confirmed_at, example_line FROM command_patterns ORDER BY confirmed_at DESC"
        ).fetchall()
        patterns = [
            {
                "pattern": r[0],
                "category": r[1],
                "confirmed_by": r[2],
                "confirmed_at": r[3],
                "example_line": r[4],
            }
            for r in rows
        ]
        return {"patterns": patterns}
    finally:
        conn.close()


@app.get("/api/categories")
def categories() -> dict:
    return {"categories": training_loop.CATEGORIES}


@app.get("/api/cache/stats")
def cache_stats() -> dict:
    return training_loop.get_cache_stats()


def _generic_parse(text: str, source_file: str | None) -> NormalizedConfig:
    """No parser recognized this format: surface every line for the training loop.

    This is the live-learning path — the operator teaches the system the new
    vendor's constructs via human-confirmed mappings.
    """
    from app.models import UnmappedLine

    cfg = NormalizedConfig(device_type="unknown", source_file=source_file)
    for idx, raw in enumerate(text.splitlines(), start=1):
        s = raw.strip()
        if not s or s.startswith("!") or s.startswith("#"):
            continue
        if len(cfg.unmapped_lines) >= 300:
            break
        cfg.unmapped_lines.append(UnmappedLine(raw_line=s, line_number=idx))
    return cfg


@app.post("/api/audit")
async def audit(file: UploadFile, use_ai: bool = True) -> AuditReport:
    """Upload .cfg/.txt -> parse -> resolve unmapped (cache/AI) -> run rules."""
    raw = await file.read()
    try:
        text = raw.decode("utf-8", errors="replace")
    except Exception:
        raise HTTPException(400, "could not decode file")

    parser = detect_vendor(text, PARSERS)

    if parser is None:
        # Unknown vendor -> teaching mode: every line goes to the training loop
        cfg = _generic_parse(text, source_file=file.filename)
        rules = []
    else:
        cfg = parser.parse(text, source_file=file.filename)
        rules = load_rules(parser.vendor_name)

    # resolve unmapped lines: confirmed cache first, then AI suggestions
    training_loop.enrich_unmapped_lines(cfg, use_ai=use_ai)
    flags = training_loop.load_cache_flags(cfg)

    findings = run_audit(cfg, rules, cache_flags=flags) if rules else []

    passed = sum(1 for f in findings if f.status == "pass")
    failed = sum(1 for f in findings if f.status == "fail")
    review = sum(1 for f in findings if f.status == "needs_review")

    return AuditReport(
        source_file=file.filename or "unknown",
        device_type=cfg.device_type,
        hostname=cfg.hostname,
        total_rules=len(rules),
        passed=passed,
        failed=failed,
        needs_review=review,
        findings=findings,
        unmapped_lines=cfg.unmapped_lines,
        rule_cache_stats=training_loop.get_cache_stats(),
    )


@app.post("/api/train/confirm")
def confirm_mapping(body: dict) -> dict:
    """Human confirms/edits a suggested category -> pattern cached for future parses."""
    raw_line = body.get("raw_line")
    category = body.get("category")
    if not raw_line or not category:
        raise HTTPException(400, "raw_line and category required")
    if category not in training_loop.CATEGORIES:
        raise HTTPException(400, f"unknown category: {category}")
    pattern = training_loop.confirm_line(raw_line, category, body.get("confirmed_by", "admin"))
    return {"status": "cached", "pattern": pattern}


@app.post("/api/train/reject")
def reject_mapping(body: dict) -> dict:
    """Reject an AI suggestion: logged for audit, nothing cached."""
    training_loop.reject_suggestion(
        body.get("raw_line", ""),
        body.get("suggested_category"),
        body.get("confidence"),
    )
    return {"status": "rejected"}


@app.post("/api/audit/report/pdf")
async def audit_pdf(file: UploadFile, use_ai: bool = True) -> StreamingResponse:
    """Run the full audit and stream back the PDF report."""
    report = await audit(file, use_ai=use_ai)
    pdf_bytes = generate_pdf(report)
    fname = Path(report.source_file).stem or "audit"
    headers = {"Content-Disposition": f'attachment; filename="{fname}_compliance_report.pdf"'}
    return StreamingResponse(io.BytesIO(pdf_bytes), media_type="application/pdf", headers=headers)


# ─── Production: serve the built frontend (single-service deploy) ───
FRONTEND_DIST = Path(__file__).parent.parent.parent / "frontend" / "dist"

if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

    @app.get("/", include_in_schema=False)
    async def serve_index() -> FileResponse:
        return FileResponse(FRONTEND_DIST / "index.html")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_spa(full_path: str) -> FileResponse:
        """Serve index.html for any non-API path (SPA fallback)."""
        f = FRONTEND_DIST / full_path
        if f.is_file():
            return FileResponse(f)
        return FileResponse(FRONTEND_DIST / "index.html")
