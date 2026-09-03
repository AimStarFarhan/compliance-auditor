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


class CiscoIOSParser(BaseParser):
    """Regex-based parser for Cisco IOS configuration files.

    Uses indentation to track context blocks: top-level commands start at
    column 0; sub-commands of interfaces / line blocks / named ACLs are
    indented. A new column-0 command closes the previous context.
    """

    vendor_name = "cisco_ios"

    HOSTNAME_RE = re.compile(r"^hostname\s+(\S+)")
    INTERFACE_RE = re.compile(r"^interface\s+(.+)")
    VTY_RE = re.compile(r"^line\s+(\S+)\s+(.+)")
    PROTOCOLS = {
        "ip http server": "http",
        "ip https server": "https",
        "ip ftp server": "ftp",
        "ip finger": "finger",
        "ip domain-lookup": "domain-lookup",
        "ip source-route": "source-route",
        "ip bootp server": "bootp",
        "cdp run": "cdp",
        "lldp run": "lldp",
        "service tcp-small-servers": "tcp-small-servers",
        "service udp-small-servers": "udp-small-servers",
        "service finger": "finger",
        "snmp-server": "snmp",
    }
    NUMBERED_ACL_RE = re.compile(
        r"^access-list (\d+) (permit|deny) (\S+) (\S+) (\S+) (\S+)(?: eq (\S+))?( log)?$"
    )
    ACL_NAMED_HEADER_RE = re.compile(r"^ip access-list (extended|standard) (\S+)")

    @staticmethod
    def _parse_acl_entry(stripped: str, acl_id: str) -> Optional[AclRule]:
        """Token-based parser for ACL entry lines.

        Formats handled:
          permit|deny <proto> any any [eq <port>] [log]
          permit|deny <proto> host <ip> any|host <ip> [eq <port>] [log]
          permit|deny <proto> <net> <mask> <net> <mask> [eq <port>] [log]
        """
        tokens = stripped.split()
        if not tokens or tokens[0] not in ("permit", "deny"):
            return None
        action = tokens[0]
        rest = tokens[1:]

        log = False
        if "log" in rest:
            log = True
            rest = [t for t in rest if t != "log"]

        port = None
        if "eq" in rest:
            i = rest.index("eq")
            if i + 1 < len(rest):
                port = rest[i + 1]
            rest = rest[:i]

        proto = rest[0] if rest else None
        addr = rest[1:]

        # collapse "host <ip>" into "<ip>"
        collapsed: list[str] = []
        i = 0
        while i < len(addr):
            if addr[i] == "host" and i + 1 < len(addr):
                collapsed.append(addr[i + 1])
                i += 2
            else:
                collapsed.append(addr[i])
                i += 1

        if len(collapsed) >= 4:
            source = f"{collapsed[0]} {collapsed[1]}"
            destination = f"{collapsed[2]} {collapsed[3]}"
        elif len(collapsed) == 2:
            source, destination = collapsed[0], collapsed[1]
        elif len(collapsed) == 1:
            source, destination = collapsed[0], "any"
        else:
            return None

        return AclRule(
            acl_id=acl_id,
            action=action,
            protocol=proto,
            source=source,
            destination=destination,
            destination_port=port,
            log=log,
            raw_line=stripped,
        )
    IPADDR_RE = re.compile(r"^\s+ip address\s+(\d+\.\d+\.\d+\.\d+)\s+(\S+)")
    SHUTDOWN_RE = re.compile(r"^\s+shutdown")
    NOSHUTDOWN_RE = re.compile(r"^\s+no shutdown")
    DESCRIPTION_RE = re.compile(r"^\s+description\s+(.*)")
    TRANSPORT_INPUT_RE = re.compile(r"^\s+transport input\s+(.*)")
    EXEC_TIMEOUT_RE = re.compile(r"^\s+exec-timeout\s+(\d+)\s+(\d+)")
    ACCESS_CLASS_RE = re.compile(r"^\s+access-class\s+(\S+)\s+(in|out)")
    NO_EXEC_RE = re.compile(r"^\s+no exec")
    ENABLE_SECRET_RE = re.compile(r"^enable secret\s+(.+)")
    USERNAME_SECRET_RE = re.compile(r"^username\s+(\S+)\s+secret\s+(.+)")
    AAA_AUTH_RE = re.compile(r"^(aaa authentication\S*.*)")
    SNMP_COMMUNITY_RE = re.compile(r"^snmp-server community\s+(\S+)\s*(\S*)")
    NTP_RE = re.compile(r"^ntp server\s+(\S+)")
    LOGGING_HOST_RE = re.compile(r"^logging host\s+(\S+)")
    LOGGING_BUFFERED_RE = re.compile(r"^logging buffered\s+(\S+)")
    LOGGING_CONSOLE_RE = re.compile(r"^logging console\s+(\S+)")
    LOGGING_TRAP_RE = re.compile(r"^logging trap\s+(\S+)")
    BANNER_RE = re.compile(r"^banner\s+(\S+)")

    def can_parse(self, config_text: str) -> bool:
        indicators = [
            "hostname ", "interface ", "ip address", "access-list",
            "line vty", "enable secret", "aaa new-model", "version 15",
            "service password-encryption",
        ]
        hits = sum(1 for ind in indicators if ind in config_text)
        return hits >= 3

    def parse(self, config_text: str, source_file: Optional[str] = None) -> NormalizedConfig:
        lines = config_text.splitlines()
        cfg = NormalizedConfig(
            device_type=self.vendor_name,
            source_file=source_file,
        )

        vty_blocks: list[LineVtySettings] = []

        current_interface: Interface | None = None
        current_line_ctx: str | None = None      # "vty" | "con" | "aux"
        current_vty: LineVtySettings | None = None
        acl_block_name: str | None = None
        acl_block_type: str | None = None

        def close_contexts():
            nonlocal current_interface, current_line_ctx, current_vty, acl_block_name, acl_block_type
            if current_interface is not None:
                cfg.interfaces.append(current_interface)
                current_interface = None
            if current_vty is not None:
                vty_blocks.append(current_vty)
                current_vty = None
            current_line_ctx = None
            acl_block_name = None
            acl_block_type = None

        for idx, raw in enumerate(lines, start=1):
            if not raw.strip() or raw.strip() in ("!", "end"):
                continue
            if raw.strip().startswith(("Building configuration", "Current configuration")):
                continue

            stripped = raw.strip()
            is_top_level = not raw[0].isspace()

            if is_top_level:
                close_contexts()

                if stripped.startswith("version "):
                    continue

                m = self.HOSTNAME_RE.match(stripped)
                if m:
                    cfg.hostname = m.group(1)
                    continue

                m = self.INTERFACE_RE.match(stripped)
                if m:
                    current_interface = Interface(name=m.group(1).strip())
                    continue

                m = self.VTY_RE.match(stripped)
                if m:
                    current_line_ctx = m.group(1)
                    if current_line_ctx == "vty":
                        current_vty = LineVtySettings(
                            line_range=f"vty {m.group(2)}".strip()
                        )
                    continue

                m = self.ACL_NAMED_HEADER_RE.match(stripped)
                if m:
                    acl_block_type = m.group(1)
                    acl_block_name = m.group(2)
                    continue

                # global protocol enables
                matched_proto = None
                for pat, name in self.PROTOCOLS.items():
                    if stripped == pat or stripped.startswith(pat + " ") and name != "snmp":
                        matched_proto = name
                        break
                if matched_proto:
                    if matched_proto not in cfg.enabled_protocols:
                        cfg.enabled_protocols.append(matched_proto)
                    continue

                # explicit "no <protocol>" — consumed, protocol not enabled
                if stripped.startswith("no "):
                    body = stripped[3:]
                    if any(body == p or body.startswith(p + " ") for p in self.PROTOCOLS):
                        continue
                    if body.startswith("ip http") or body.startswith("ip https"):
                        continue
                    if body.startswith("service "):
                        continue

                m = self.NUMBERED_ACL_RE.match(stripped)
                if m:
                    cfg.acl_rules.append(
                        AclRule(
                            acl_id=m.group(1),
                            action=m.group(2),
                            protocol=m.group(3),
                            source=m.group(4),
                            destination=m.group(5),
                            destination_port=m.group(7),
                            log=bool(m.group(8)),
                            raw_line=stripped,
                        )
                    )
                    continue

                m = self.ENABLE_SECRET_RE.match(stripped)
                if m:
                    cfg.auth_settings.enable_password_hash = m.group(1).strip()
                    continue
                m = self.USERNAME_SECRET_RE.match(stripped)
                if m:
                    cfg.auth_settings.username_secrets.append(m.group(2).strip())
                    continue
                if stripped == "aaa new-model":
                    cfg.auth_settings.aaa_new_model = True
                    continue
                m = self.AAA_AUTH_RE.match(stripped)
                if m:
                    cfg.auth_settings.aaa_authentication.append(m.group(1))
                    continue
                if stripped == "service password-encryption":
                    cfg.auth_settings.password_encryption = True
                    continue

                m = self.SNMP_COMMUNITY_RE.match(stripped)
                if m:
                    cfg.snmp_settings.setdefault("communities", []).append(
                        {"community": m.group(1), "mode": m.group(2) or "ro"}
                    )
                    continue
                m = self.NTP_RE.match(stripped)
                if m:
                    cfg.ntp_settings.setdefault("servers", []).append(m.group(1))
                    continue
                m = self.LOGGING_HOST_RE.match(stripped)
                if m:
                    cfg.logging_settings.setdefault("hosts", []).append(m.group(1))
                    continue
                m = self.LOGGING_BUFFERED_RE.match(stripped)
                if m:
                    cfg.logging_settings["buffered"] = m.group(1)
                    continue
                m = self.LOGGING_CONSOLE_RE.match(stripped)
                if m:
                    cfg.logging_settings["console"] = m.group(1)
                    continue
                m = self.LOGGING_TRAP_RE.match(stripped)
                if m:
                    cfg.logging_settings["trap"] = m.group(1)
                    continue
                m = self.BANNER_RE.match(stripped)
                if m:
                    cfg.banner_settings["present"] = True
                    cfg.banner_settings.setdefault("types", []).append(m.group(1))
                    continue
                if re.match(r"^(no )?logging (on|monitor|informational|debug)", stripped):
                    cfg.logging_settings.setdefault("misc", []).append(stripped)
                    continue

                if stripped.startswith("ip route"):
                    cfg.service_settings.setdefault("static_routes", []).append(stripped)
                    continue
                if stripped.startswith("clock timezone"):
                    cfg.service_settings["timezone"] = stripped
                    continue

                cfg.unmapped_lines.append(UnmappedLine(raw_line=stripped, line_number=idx))
                continue

            # ---- indented (sub-command of some context) ----

            if current_interface is not None:
                m = self.IPADDR_RE.match(raw)
                if m:
                    current_interface.ip_address = m.group(1)
                    current_interface.subnet_mask = m.group(2)
                    continue
                if self.NOSHUTDOWN_RE.match(raw):
                    current_interface.shutdown = False
                    continue
                if self.SHUTDOWN_RE.match(raw):
                    current_interface.shutdown = True
                    continue
                m = self.DESCRIPTION_RE.match(raw)
                if m:
                    current_interface.description = m.group(1).strip()
                    continue
                current_interface.extra_lines.append(stripped)
                continue

            if current_vty is not None:
                m = self.TRANSPORT_INPUT_RE.match(raw)
                if m:
                    current_vty.transport_input = [
                        t.strip() for t in m.group(1).split() if t.strip()
                    ]
                    continue
                m = self.EXEC_TIMEOUT_RE.match(raw)
                if m:
                    current_vty.exec_timeout_minutes = int(m.group(1))
                    continue
                m = self.ACCESS_CLASS_RE.match(raw)
                if m:
                    current_vty.access_class = m.group(1)
                    continue
                if self.NO_EXEC_RE.match(raw):
                    current_vty.exec = False
                    continue
                cfg.unmapped_lines.append(UnmappedLine(raw_line=stripped, line_number=idx))
                continue

            if current_line_ctx in ("con", "aux"):
                # console/aux sub-commands: consume known ones, record rest
                m = self.EXEC_TIMEOUT_RE.match(raw)
                if m:
                    cfg.service_settings.setdefault("console_exec_timeout", []).append(
                        int(m.group(1))
                    )
                    continue
                m = self.TRANSPORT_INPUT_RE.match(raw)
                if m:
                    cfg.service_settings.setdefault("console_transport", []).append(
                        m.group(1).strip()
                    )
                    continue
                cfg.unmapped_lines.append(UnmappedLine(raw_line=stripped, line_number=idx))
                continue

            if acl_block_name is not None:
                rule = self._parse_acl_entry(stripped, acl_block_name)
                if rule:
                    cfg.acl_rules.append(rule)
                    continue
                cfg.unmapped_lines.append(UnmappedLine(raw_line=stripped, line_number=idx))
                continue

            cfg.unmapped_lines.append(UnmappedLine(raw_line=stripped, line_number=idx))

        close_contexts()

        if vty_blocks:
            merged = LineVtySettings(line_range="; ".join(b.line_range for b in vty_blocks))
            transports: list[str] = []
            timeouts: list[int] = []
            access_classes: list[str] = []
            exec_flags: list[bool] = []
            for b in vty_blocks:
                transports.extend(b.transport_input)
                if b.exec_timeout_minutes is not None:
                    timeouts.append(b.exec_timeout_minutes)
                if b.access_class:
                    access_classes.append(b.access_class)
                exec_flags.append(b.exec)
            merged.transport_input = transports
            merged.exec_timeout_minutes = min(timeouts) if timeouts else None
            merged.access_class = "; ".join(dict.fromkeys(access_classes)) or None
            merged.exec = all(exec_flags)
            cfg.line_vty_settings = merged

        return cfg
