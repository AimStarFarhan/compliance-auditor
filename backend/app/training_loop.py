"""Training loop: unmapped-line detection, LLM suggestion (via LM Studio),
human confirmation, and SQLite rule-cache persistence.

The LLM's output is ALWAYS a suggestion only. Nothing is auto-applied to a
compliance verdict; a human must confirm before a cached pattern is used
to classify future lines.
"""
import json
import os
import re
import sqlite3
import time
from pathlib import Path
from typing import Optional

import httpx

from app.models import NormalizedConfig, UnmappedLine, UnmappedStatus

DB_PATH = Path(__file__).parent / "rule_cache.db"
LM_STUDIO_BASE_URL = os.environ.get("LM_STUDIO_BASE_URL", "http://localhost:1234/v1")
# If LM_STUDIO_MODEL is unset, the first available model is auto-detected at request time.
LM_STUDIO_MODEL = os.environ.get("LM_STUDIO_MODEL", "")

CATEGORIES = [
    "auth_settings",
    "routing_protocol",
    "interface_config",
    "acl_rule",
    "snmp_config",
    "logging_config",
    "ntp_config",
    "vty_line_config",
    "banner_config",
    "service_config",
    "qos_config",
    "vpn_config",
    "management_access",
    "other",
]

FEW_SHOT_EXAMPLES = [
    ("enable password 7 $1$abc", "auth_settings"),
    ("router ospf 1", "routing_protocol"),
    ("network 10.0.0.0 0.0.0.255 area 0", "routing_protocol"),
    ("spanning-tree mode rapid-pvst", "service_config"),
    ("ip scp server enable", "management_access"),
    ("crypto isakmp policy 10", "vpn_config"),
    ("logging trap warnings", "logging_config"),
    ("snmp-server location HQ", "snmp_config"),
    ("banner login ^CAuthorized only^C", "banner_config"),
    ("vtp mode transparent", "service_config"),
]


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS command_patterns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pattern TEXT UNIQUE NOT NULL,
            category TEXT NOT NULL,
            confirmed_by TEXT NOT NULL DEFAULT 'admin',
            confirmed_at REAL NOT NULL,
            example_line TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS suggestions_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            raw_line TEXT NOT NULL,
            suggested_category TEXT,
            confidence REAL,
            accepted INTEGER NOT NULL DEFAULT 0,
            created_at REAL NOT NULL
        )
        """
    )
    conn.commit()
    return conn


def make_command_pattern(raw_line: str) -> str:
    """Convert a raw line into a matching pattern.

    Strategy:
      - numeric tokens -> '#'
      - tokens with mixed alphanumerics (hashes, secrets, IPs w/ text) -> '#'
      - last token -> '#' if the command looks like '<keywords> <value>'
        (heuristic: previous token is a known value-taking keyword) else kept
    e.g. 'ntp server 10.10.50.1'      -> 'ntp server #'
         'vtp mode transparent'       -> 'vtp mode #'
         'login password secretx9'     -> 'login password #'
    """
    VALUE_KEYWORDS = {
        "server", "mode", "password", "host", "community", "banner", "secret",
        "description", "timeout", "address", "port", "level", "location", "route",
        "policy", "domain", "interface", "user", "role", "action", "permit",
        "deny", "source", "destination", "via", "next-hop", "permit-source",
        "key", "name", "id", "vlan", "pool", "group", "rule", "class",
    }
    STRUCTURAL = {"in", "out", "any", "log", "all"}
    tokens = raw_line.split()
    out: list[str] = []
    for i, t in enumerate(tokens):
        if re.fullmatch(r"[\d.:/]+", t) or re.search(r"\d", t) and re.search(r"[a-zA-Z]", t):
            out.append("#")
        elif (
            i > 0
            and tokens[i - 1].lower() in VALUE_KEYWORDS
            and t.lower() not in STRUCTURAL
            and t.lower() not in VALUE_KEYWORDS
        ):
            out.append("#")
        else:
            out.append(t)
    return " ".join(out)[:120]


def pattern_matches(pattern: str, raw_line: str) -> bool:
    """Check whether raw_line matches a cached pattern.

    '#' is a wildcard for a single value token (numbers, IPs, hashes, word
    values like mode names). Token count and all non-'#' tokens must match
    exactly.
    """
    pat_tokens = pattern.split()
    line_tokens = raw_line.split()
    if len(pat_tokens) != len(line_tokens):
        return False
    for p, l in zip(pat_tokens, line_tokens):
        if p == "#":
            continue
        if p != l:
            return False
    return True


def lookup_cache(raw_line: str) -> Optional[tuple[str, str]]:
    """Return (category, pattern) if a confirmed cached pattern matches this line."""
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT pattern, category FROM command_patterns"
        ).fetchall()
        for pattern, category in rows:
            if pattern_matches(pattern, raw_line):
                return category, pattern
        return None
    finally:
        conn.close()


def get_cache_stats() -> dict[str, int]:
    conn = _connect()
    try:
        total = conn.execute("SELECT COUNT(*) FROM command_patterns").fetchone()[0]
        by_cat = conn.execute(
            "SELECT category, COUNT(*) FROM command_patterns GROUP BY category"
        ).fetchall()
        return {"total_patterns": total, "by_category": dict(by_cat)}
    finally:
        conn.close()


def save_confirmation(raw_line: str, category: str, confirmed_by: str = "admin") -> str:
    """Persist a human-confirmed command_pattern -> category mapping."""
    pattern = make_command_pattern(raw_line)
    conn = _connect()
    try:
        conn.execute(
            """
            INSERT INTO command_patterns (pattern, category, confirmed_by, confirmed_at, example_line)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(pattern) DO UPDATE SET category=excluded.category, confirmed_at=excluded.confirmed_at
            """,
            (pattern, category, confirmed_by, time.time(), raw_line),
        )
        conn.commit()
        return pattern
    finally:
        conn.close()


def reject_suggestion(raw_line: str, suggested_category: Optional[str], confidence: Optional[float]) -> None:
    """Log a rejected AI suggestion (audit trail; nothing cached)."""
    conn = _connect()
    try:
        conn.execute(
            "INSERT INTO suggestions_log (raw_line, suggested_category, confidence, accepted, created_at) VALUES (?, ?, ?, 0, ?)",
            (raw_line, suggested_category, confidence, time.time()),
        )
        conn.commit()
    finally:
        conn.close()


def _build_prompt(raw_line: str) -> list[dict]:
    sys_prompt = (
        "You are a network device configuration classifier. Given a single line "
        "from a network device configuration file, classify it into exactly one "
        "of these categories:\n" + "\n".join(f"- {c}" for c in CATEGORIES) +
        "\n\nRespond ONLY with JSON: {\"category\": \"<one of the categories>\", \"confidence\": <0.0-1.0>}. "
        "If the line is ambiguous, pick 'other' with low confidence."
    )
    shots = []
    for ex_line, ex_cat in FEW_SHOT_EXAMPLES:
        shots.append({
            "role": "user",
            "content": f"Classify this config line:\n{ex_line}",
        })
        shots.append({
            "role": "assistant",
            "content": json.dumps({"category": ex_cat, "confidence": 0.95}),
        })
    shots.append({
        "role": "user",
        "content": f"Classify this config line:\n{raw_line}",
    })
    return [{"role": "system", "content": sys_prompt}] + shots


def _detect_model() -> Optional[str]:
    """Ask the OpenAI-compatible server which model to use (cached per process)."""
    global LM_STUDIO_MODEL
    if LM_STUDIO_MODEL:
        return LM_STUDIO_MODEL
    if _detect_model._cached:
        return _detect_model._cached
    try:
        r = httpx.get(f"{LM_STUDIO_BASE_URL}/models", timeout=5.0)
        data = r.json().get("data", [])
        # prefer a chat-capable model (skip embedding-only models)
        for m in data:
            mid = m.get("id", "")
            if "embed" not in mid.lower():
                _detect_model._cached = mid
                return mid
    except Exception:
        return None
    return None

_detect_model._cached = None


def suggest_category(raw_line: str) -> tuple[Optional[str], Optional[float]]:
    """Call the OpenAI-compatible server (LM Studio etc.) for a category suggestion.
    Suggestion only — never a verdict. Returns (None, None) if the server is
    unavailable, so the app degrades gracefully without any AI."""
    model = _detect_model()
    if not model:
        return None, None
    payload = {
        "model": model,
        "messages": _build_prompt(raw_line),
        "temperature": 0.1,
        "max_tokens": 2000,
    }
    try:
        resp = httpx.post(
            f"{LM_STUDIO_BASE_URL}/chat/completions",
            json=payload,
            timeout=60.0,
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
    except Exception:
        return None, None

    m = re.search(r"\{[^{}]*\"category\"[^{}]*\}", content, re.DOTALL)
    if not m:
        return None, None
    try:
        data = json.loads(m.group(0))
        cat = data.get("category")
        conf = data.get("confidence")
        if cat in CATEGORIES and isinstance(conf, (int, float)):
            return cat, float(conf)
        return None, None
    except (json.JSONDecodeError, TypeError):
        return None, None


def enrich_unmapped_lines(cfg: NormalizedConfig, use_ai: bool = True) -> None:
    """Resolve unmapped lines: first via confirmed cache, then optionally via AI suggestion.

    Mutates cfg.unmapped_lines in place:
      - cache hit  -> status becomes human_confirmed (pattern from earlier confirmation)
      - AI suggest -> status becomes ai_suggested (NEVER applied to compliance verdicts)
    """
    for u in cfg.unmapped_lines:
        if u.status == UnmappedStatus.human_confirmed:
            continue
        cached = lookup_cache(u.raw_line)
        if cached:
            category, pattern = cached
            u.suggested_category = category
            u.confidence = 1.0
            u.status = UnmappedStatus.human_confirmed
            u.command_pattern = pattern
            continue
        if use_ai:
            cat, conf = suggest_category(u.raw_line)
            if cat:
                u.suggested_category = cat
                u.confidence = conf
                u.status = UnmappedStatus.ai_suggested
                u.suggested_by_ai = True


def confirm_line(raw_line: str, category: str, confirmed_by: str = "admin") -> str:
    """Human confirms (or edits) a suggested category -> write to cache."""
    pattern = save_confirmation(raw_line, category, confirmed_by)
    return pattern


def load_cache_flags(cfg: NormalizedConfig) -> dict[str, bool]:
    """Flags used by rule_engine to mark findings influenced by AI/confirmed mappings."""
    ai = any(u.status == UnmappedStatus.ai_suggested for u in cfg.unmapped_lines)
    confirmed = any(
        u.status == UnmappedStatus.human_confirmed and u.suggested_by_ai
        for u in cfg.unmapped_lines
    )
    return {"ai_influenced": ai, "confirmed_influenced": confirmed}
