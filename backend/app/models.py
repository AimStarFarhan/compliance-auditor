from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class UnmappedStatus(str, Enum):
    unmapped = "unmapped"
    ai_suggested = "ai_suggested"
    human_confirmed = "human_confirmed"
    rejected = "rejected"


class Interface(BaseModel):
    name: str
    description: Optional[str] = None
    ip_address: Optional[str] = None
    subnet_mask: Optional[str] = None
    shutdown: bool = False
    extra_lines: list[str] = Field(default_factory=list)


class AclRule(BaseModel):
    acl_id: str
    action: str
    protocol: Optional[str] = None
    source: str
    destination: str
    destination_port: Optional[str] = None
    log: bool = False
    raw_line: str


class AuthSettings(BaseModel):
    password_encryption: bool = False
    secret_hash: Optional[str] = None
    username_secrets: list[str] = Field(default_factory=list)
    enable_password_hash: Optional[str] = None
    aaa_new_model: bool = False
    aaa_authentication: list[str] = Field(default_factory=list)
    password_strength_configured: bool = False


class LineVtySettings(BaseModel):
    line_range: str = "vty 0 4"
    transport_input: list[str] = Field(default_factory=list)
    exec_timeout_minutes: Optional[int] = None
    access_class: Optional[str] = None
    exec: bool = True


class UnmappedLine(BaseModel):
    raw_line: str
    line_number: int
    suggested_category: Optional[str] = None
    confidence: Optional[float] = None
    status: UnmappedStatus = UnmappedStatus.unmapped
    suggested_by_ai: bool = False
    command_pattern: Optional[str] = None


class NormalizedConfig(BaseModel):
    device_type: str
    hostname: Optional[str] = None
    interfaces: list[Interface] = Field(default_factory=list)
    acl_rules: list[AclRule] = Field(default_factory=list)
    auth_settings: AuthSettings = Field(default_factory=AuthSettings)
    enabled_protocols: list[str] = Field(default_factory=list)
    line_vty_settings: LineVtySettings = Field(default_factory=LineVtySettings)
    snmp_settings: dict[str, Any] = Field(default_factory=dict)
    logging_settings: dict[str, Any] = Field(default_factory=dict)
    ntp_settings: dict[str, Any] = Field(default_factory=dict)
    banner_settings: dict[str, Any] = Field(default_factory=dict)
    service_settings: dict[str, Any] = Field(default_factory=dict)
    unmapped_lines: list[UnmappedLine] = Field(default_factory=list)
    source_file: Optional[str] = None


class RuleCheckType(str, Enum):
    field_absent = "field_absent"
    field_equals = "field_equals"
    field_contains = "field_contains"
    field_not_contains = "field_not_contains"
    field_empty = "field_empty"
    field_not_empty = "field_not_empty"
    numeric_max = "numeric_max"
    acl_deny_log = "all_deny_acl_entries_have_log"
    deny_log_check = "deny_log_check"


class Rule(BaseModel):
    rule_id: str
    cis_section: str
    check_type: RuleCheckType
    target_field: str
    expected_value: Optional[str] = None
    severity: str = Field(pattern="^(high|medium|low)$")
    remediation_cli: str
    vendor: str = "cisco_ios"


class Finding(BaseModel):
    rule_id: str
    cis_section: str
    status: str
    severity: str
    remediation_cli: str
    evidence: Optional[str] = None
    influenced_by_ai_suggestion: bool = False
    influenced_by_confirmed_mapping: bool = False


class AuditReport(BaseModel):
    source_file: str
    device_type: str
    hostname: Optional[str]
    total_rules: int
    passed: int
    failed: int
    needs_review: int
    findings: list[Finding] = Field(default_factory=list)
    unmapped_lines: list[UnmappedLine] = Field(default_factory=list)
    rule_cache_stats: dict[str, Any] = Field(default_factory=dict)
