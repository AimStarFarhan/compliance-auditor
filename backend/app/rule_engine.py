"""Rule engine: run NormalizedConfig against CIS rule JSON."""
import json
from functools import reduce
from pathlib import Path
from typing import Any

from app.models import Finding, NormalizedConfig, Rule, RuleCheckType

RULES_DIR = Path(__file__).parent / "rules"


def load_rules(vendor: str = "cisco_ios") -> list[Rule]:
    path = RULES_DIR / f"cis_{vendor}.json"
    if not path.exists():
        return []
    data = json.loads(path.read_text())
    rules = []
    for r in data.get("rules", []):
        r.pop("citation_confidence", None)
        rules.append(Rule(**r))
    return rules


def _get_field(cfg: NormalizedConfig, dotted: str) -> Any:
    """Resolve 'a.b.c' against the Pydantic model via attribute walk.

    If an intermediate value is a list, the remaining path is applied to
    each item (dicts or models) and results are flattened.
    """
    obj: Any = cfg
    parts = dotted.split(".")
    i = 0
    while i < len(parts):
        part = parts[i]
        if obj is None:
            return None
        if isinstance(obj, list):
            remaining = ".".join(parts[i:])
            results = []
            for item in obj:
                if isinstance(item, dict):
                    val = item.get(remaining)
                    if "." in remaining:
                        sub = item
                        ok = True
                        for p in remaining.split("."):
                            if isinstance(sub, dict):
                                sub = sub.get(p)
                            else:
                                ok = False
                                break
                        val = sub if ok else None
                    results.append(val)
                else:
                    results.append(_get_field(item, remaining) if hasattr(item, "__dict__") else None)
            flat: list[Any] = []
            for r in results:
                if isinstance(r, list):
                    flat.extend(r)
                else:
                    flat.append(r)
            return flat
        if hasattr(obj, part):
            obj = getattr(obj, part)
        elif isinstance(obj, dict) and part in obj:
            obj = obj[part]
        else:
            return None
        i += 1
    return obj


def _to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() == "true"
    return bool(value)


def _fmt(value: Any) -> str:
    if value is None:
        return "not configured"
    if isinstance(value, list):
        return ", ".join(str(v) for v in value) or "empty"
    return str(value)


def evaluate_rule(cfg: NormalizedConfig, rule: Rule, cache_flags: dict[str, bool]) -> Finding:
    """Evaluate one rule. cache_flags: {'ai_influenced': bool, 'confirmed_influenced': bool}."""
    field_val = _get_field(cfg, rule.target_field)
    status = "needs_review"
    evidence = ""

    ct = rule.check_type
    if ct == RuleCheckType.field_absent:
        # pass if expected value NOT present in list/field
        if isinstance(field_val, list):
            found = any(str(rule.expected_value).lower() == str(v).lower() for v in field_val)
            status = "fail" if found else "pass"
            evidence = f"found '{rule.expected_value}' in {_fmt(field_val)}" if found else f"'{rule.expected_value}' not present"
        else:
            found = field_val is not None and str(field_val).lower() == str(rule.expected_value).lower()
            status = "fail" if found else "pass"
            evidence = f"'{rule.expected_value}' is set" if found else "not set"
    elif ct == RuleCheckType.field_contains:
        if isinstance(field_val, list):
            found = any(str(rule.expected_value).lower() in str(v).lower() for v in field_val)
            status = "pass" if found else "fail"
            evidence = f"transport includes '{rule.expected_value}'" if found else f"transport = {_fmt(field_val)}"
        else:
            found = field_val is not None and str(rule.expected_value).lower() in str(field_val).lower()
            status = "pass" if found else "fail"
    elif ct == RuleCheckType.field_not_contains:
        if isinstance(field_val, list):
            banned = [b for b in (rule.expected_value or "").split("|") if b]
            hit = next(
                (b for b in banned for v in field_val if str(v).lower() == b.lower()), None
            )
            # empty SNMP config: no communities defined -> rule satisfied trivially
            if not field_val or all(v in (None, "") for v in field_val):
                status, evidence = "pass", "no community strings configured"
            else:
                status = "fail" if hit else "pass"
                evidence = f"default community '{hit}' in use" if hit else f"communities = {_fmt([v for v in field_val if v])}"
        else:
            status = "pass"
    elif ct == RuleCheckType.field_equals:
        expected_true = str(rule.expected_value).lower() == "true"
        actual_true = _to_bool(field_val)
        status = "pass" if actual_true == expected_true else "fail"
        evidence = f"{rule.target_field} = {_fmt(field_val)}"
    elif ct == RuleCheckType.field_not_empty:
        empty = field_val is None or (isinstance(field_val, (list, str)) and len(field_val) == 0)
        status = "fail" if empty else "pass"
        evidence = f"{rule.target_field} = {_fmt(field_val)}"
    elif ct == RuleCheckType.field_empty:
        empty = field_val is None or (isinstance(field_val, (list, str)) and len(field_val) == 0)
        status = "pass" if empty else "fail"
    elif ct == RuleCheckType.numeric_max:
        limit = float(rule.expected_value) if rule.expected_value else None
        if field_val is None:
            status = "fail"
            evidence = "exec-timeout not configured"
        elif limit is not None and float(field_val) <= limit:
            status = "pass"
            evidence = f"exec-timeout = {field_val} min"
        else:
            status = "fail"
            evidence = f"exec-timeout = {field_val} min (> {int(limit)} min)"
    elif ct == RuleCheckType.acl_deny_log:
        denies = [r for r in cfg.acl_rules if r.action == "deny"]
        if not denies:
            status = "pass"
            evidence = "no deny entries present"
        else:
            missing = [r for r in denies if not r.log]
            status = "fail" if missing else "pass"
            evidence = (
                f"{len(missing)} of {len(denies)} deny entries lack 'log'"
                if missing
                else f"all {len(denies)} deny entries have 'log'"
            )
    elif ct == RuleCheckType.deny_log_check:
        deny_total = cfg.service_settings.get("deny_total", 0)
        missing_log = cfg.service_settings.get("deny_log_missing", 0)
        if deny_total == 0:
            status, evidence = "pass", "no deny policies present"
        elif missing_log == 0:
            status, evidence = "pass", f"all {deny_total} deny policies log"
        else:
            status = "fail"
            evidence = f"{missing_log} of {deny_total} deny policies lack logging"
    else:
        status = "needs_review"
        evidence = "unsupported check type"

    return Finding(
        rule_id=rule.rule_id,
        cis_section=rule.cis_section,
        status=status,
        severity=rule.severity,
        remediation_cli=rule.remediation_cli,
        evidence=evidence,
        influenced_by_ai_suggestion=cache_flags.get("ai_influenced", False),
        influenced_by_confirmed_mapping=cache_flags.get("confirmed_influenced", False),
    )


def run_audit(cfg: NormalizedConfig, rules: list[Rule], cache_flags: dict[str, bool] | None = None) -> list[Finding]:
    flags = cache_flags or {}
    return [evaluate_rule(cfg, r, flags) for r in rules]
