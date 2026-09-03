import re
from typing import Optional

from app.models import (
    AclRule,
    Interface,
    LineVtySettings,
    NormalizedConfig,
    UnmappedLine,
)
from app.parsers.base_parser import BaseParser


class JuniperSRXParser(BaseParser):
    """Regex-based parser for Juniper SRX (set-format) configuration files.

    Implements the same BaseParser interface as the Cisco parser; output is
    the same NormalizedConfig, proving the schema generalizes across vendors.
    Handles 'set ...' hierarchical syntax. Depth over breadth: only the
    constructs needed for a small rule subset are extracted; everything else
    lands in unmapped_lines for the training loop.
    """

    vendor_name = "juniper_srx"

    def can_parse(self, config_text: str) -> bool:
        set_lines = sum(1 for l in config_text.splitlines() if l.strip().startswith("set "))
        return set_lines >= 5

    def parse(self, config_text: str, source_file: Optional[str] = None) -> NormalizedConfig:
        cfg = NormalizedConfig(device_type=self.vendor_name, source_file=source_file)
        vty = LineVtySettings()
        system_services: list[str] = []
        mgmt_hosts: list[str] = []
        deny_log_missing = 0
        deny_total = 0
        seen_rule_names: set[str] = set()

        for idx, raw in enumerate(config_text.splitlines(), start=1):
            line = raw.strip()
            if not line or line.startswith("#"):
                continue

            # set system host-name X
            m = re.match(r"^set system host-name (\S+)$", line)
            if m:
                cfg.hostname = m.group(1)
                continue

            # ssh-specific settings (must precede generic services match)
            m = re.match(r"^set system services ssh (.*)$", line)
            if m:
                tm = re.search(r"idle-timeout (\d+)", m.group(1))
                if tm:
                    vty.exec_timeout_minutes = int(tm.group(1))
                continue

            # set system services <svc> ... (enabled protocols)
            m = re.match(r"^set system services (\S+)", line)
            if m:
                svc = m.group(1)
                system_services.append(svc)
                if svc == "ssh":
                    vty.transport_input.append("ssh")
                elif svc == "telnet":
                    vty.transport_input.append("telnet")
                elif svc == "http" or svc == "web-management":
                    cfg.enabled_protocols.append("http")
                elif svc == "ftp":
                    cfg.enabled_protocols.append("ftp")
                elif svc == "finger":
                    cfg.enabled_protocols.append("finger")
                continue

            # ssh settings consumed above
            # root-authentication / auth
            m = re.match(r"^set system root-authentication (.*)$", line)
            if m:
                cfg.auth_settings.enable_password_hash = m.group(1)
                continue
            m = re.match(r"^set system login user (\S+) (.*)$", line)
            if m:
                cfg.auth_settings.username_secrets.append(m.group(2))
                continue
            m = re.match(r"^set system login password policy minimum-length (\d+)", line)
            if m:
                cfg.auth_settings.password_strength_configured = True
                continue
            if re.match(r"^set system login password policy", line):
                cfg.auth_settings.password_strength_configured = True
                continue
            m = re.match(r"^set system accounting", line)
            if m:
                cfg.auth_settings.aaa_new_model = True
                continue

            # syslog
            m = re.match(r"^set system syslog host (\S+) (.*)$", line)
            if m:
                cfg.logging_settings.setdefault("hosts", []).append(m.group(1))
                continue
            m = re.match(r"^set system syslog file", line)
            if m:
                cfg.logging_settings.setdefault("files", []).append(line)
                continue

            # ntp
            m = re.match(r"^set system ntp server (\S+)", line)
            if m:
                cfg.ntp_settings.setdefault("servers", []).append(m.group(1))
                continue

            # banner
            if line.startswith("set system login message"):
                cfg.banner_settings["present"] = True
                continue

            # snmp
            m = re.match(r"^set snmp community (\S+)", line)
            if m:
                cfg.snmp_settings.setdefault("communities", []).append(
                    {"community": m.group(1), "mode": "unknown"}
                )
                continue
            if line.startswith("set snmp "):
                cfg.snmp_settings.setdefault("misc", []).append(line)
                continue

            # interfaces
            m = re.match(r"^set interfaces (\S+) (.*)$", line)
            if m:
                ifname, rest = m.group(1), m.group(2)
                iface = next((i for i in cfg.interfaces if i.name == ifname), None)
                if iface is None:
                    iface = Interface(name=ifname)
                    cfg.interfaces.append(iface)
                dm = re.match(r"description \"?(.*?)\"?$", rest)
                if dm:
                    iface.description = dm.group(1)
                    continue
                am = re.match(r"unit \d+ family inet address (\d+\.\d+\.\d+\.\d+/\d+)", rest)
                if am:
                    iface.ip_address = am.group(1).split("/")[0]
                    iface.subnet_mask = am.group(1)
                    continue
                if rest == "disable":
                    iface.shutdown = True
                    continue
                iface.extra_lines.append(rest)
                continue

            # security policies -> acl_rules (subset)
            m = re.match(r"^set security policies from-zone (\S+) to-zone (\S+) policy (\S+) match (.*)$", line)
            if m:
                if m.group(3) not in seen_rule_names:
                    seen_rule_names.add(m.group(3))
                parts = m.group(4).split()
                # e.g. "source-address any destination-address any application junos-https"
                src = parts[1] if len(parts) > 1 and parts[0] == "source-address" else "any"
                dst = parts[3] if len(parts) > 3 and parts[2] == "destination-address" else "any"
                cfg.acl_rules.append(
                    AclRule(
                        acl_id=f"{m.group(1)}->{m.group(2)}:{m.group(3)}",
                        action="permit",
                        protocol=None,
                        source=src,
                        destination=dst,
                        raw_line=line,
                    )
                )
                continue
            m = re.match(r"^set security policies from-zone (\S+) to-zone (\S+) policy (\S+) then (.*)$", line)
            if m:
                action = m.group(4).split()[0]
                is_deny = action in ("deny", "reject")
                if is_deny:
                    deny_total += 1
                    if "log" not in m.group(4):
                        deny_log_missing += 1
                if cfg.acl_rules:
                    last = cfg.acl_rules[-1]
                    if last.acl_id.endswith(m.group(3)) and last.action == "permit":
                        last.action = action
                continue

            # default-deny style global policies
            if line.startswith("set security policies default-policy"):
                deny_total += 1
                if "log" not in line:
                    deny_log_missing += 1
                cfg.acl_rules.append(
                    AclRule(acl_id="default-policy", action="deny", source="any",
                            destination="any", raw_line=line)
                )
                continue

            # zone address-books (kept out of unmapped, informational)
            if line.startswith("set security zones "):
                cfg.service_settings.setdefault("zones", []).append(line)
                continue

            # routing
            if line.startswith("set routing-options "):
                cfg.service_settings.setdefault("routing", []).append(line)
                continue

            # everything else -> training loop
            cfg.unmapped_lines.append(UnmappedLine(raw_line=line, line_number=idx))

        cfg.line_vty_settings = vty
        if deny_total:
            cfg.service_settings["deny_total"] = deny_total
            cfg.service_settings["deny_log_missing"] = deny_log_missing
        return cfg
