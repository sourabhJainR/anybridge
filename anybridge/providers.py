"""Capability-aware browser provider selection for AnyBridge."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Iterable

@dataclass(frozen=True)
class ProviderProfile:
    name: str
    browsers: tuple[str, ...]
    capabilities: frozenset[str]
    optional: bool = True

PROVIDERS = (
    ProviderProfile("playwright", ("chromium", "firefox", "webkit"),
                    frozenset({"webmcp", "network_interception", "screenshot", "storage_state", "bdd"}), False),
    ProviderProfile("selenium", ("chrome", "firefox", "edge"),
                    frozenset({"webmcp", "network_interception", "screenshot", "storage_state", "bdd"}), True),
)

def provider_profiles() -> tuple[ProviderProfile, ...]:
    return PROVIDERS

def select_provider(required: Iterable[str] = (), preferred: str | None = None,
                    browser: str | None = None, available: Iterable[str] | None = None) -> str:
    required = frozenset(required)
    available_set = frozenset(available or (p.name for p in PROVIDERS))
    candidates = [p for p in PROVIDERS if p.name in available_set and required <= p.capabilities]
    if browser:
        candidates = [p for p in candidates if browser in p.browsers]
    if preferred:
        for p in candidates:
            if p.name == preferred:
                return p.name
    if not candidates:
        raise ValueError(f"No provider satisfies capabilities={sorted(required)!r}, browser={browser!r}")
    return candidates[0].name
