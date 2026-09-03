from abc import ABC, abstractmethod

from app.models import NormalizedConfig


class BaseParser(ABC):
    """Shared interface all vendor parsers implement."""

    vendor_name: str = "unknown"

    @abstractmethod
    def can_parse(self, config_text: str) -> bool:
        """Return True if this parser recognizes the config format."""

    @abstractmethod
    def parse(self, config_text: str, source_file: str | None = None) -> NormalizedConfig:
        """Parse raw config text into a NormalizedConfig."""


def detect_vendor(config_text: str, parsers: list[BaseParser]) -> BaseParser | None:
    """Try each parser in order; return the first that recognizes the format."""
    for parser in parsers:
        if parser.can_parse(config_text):
            return parser
    return None
