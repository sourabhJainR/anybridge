"""Structured trust boundaries for page-controlled WebMCP content.

Anything supplied by a web page is data, not an AnyBridge/system instruction.
This module keeps that distinction explicit in machine-readable envelopes and
optionally spotlighted/base64 encoded payloads. It does not attempt to prove
that arbitrary text is non-malicious.
"""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class ContentEnvelope:
    source: str
    content_type: str
    trust: str
    instruction_authority: str
    origin: str
    tool_name: str
    content: Any
    encoding: str = "identity"
    boundary: str | None = None
    content_hash: str = ""

    def to_dict(self) -> dict[str, Any]:
        data = self.__dict__.copy()
        return data


def _stable_json(value: Any) -> str:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    except (TypeError, ValueError, RecursionError):
        return repr(value)


def content_hash(value: Any) -> str:
    return hashlib.sha256(_stable_json(value).encode("utf-8")).hexdigest()[:16]


def _clean_boundary(value: str, boundary: str) -> str:
    return value.replace(boundary, "[BOUNDARY_REMOVED]")


def spotlight(value: Any, boundary: str | None = None) -> tuple[str, str]:
    """Return text with a per-envelope boundary that cannot be injected by payload text."""
    marker = boundary or secrets.token_hex(16)
    text = value if isinstance(value, str) else _stable_json(value)
    text = _clean_boundary(text, marker)
    return f"[UNTRUSTED_WEBMCP:{marker}]\n{text}\n[/UNTRUSTED_WEBMCP:{marker}]", marker


def encode_untrusted(value: Any) -> str:
    """Encode a payload for higher-risk contexts without executing or interpreting it."""
    raw = value if isinstance(value, str) else _stable_json(value)
    return base64.b64encode(raw.encode("utf-8")).decode("ascii")


def wrap_tool_metadata(
    *,
    origin: str,
    name: str,
    description: str,
    schema: Mapping[str, Any],
    annotations: Mapping[str, Any] | None = None,
) -> ContentEnvelope:
    """Represent a page-provided tool definition as data with no instruction authority."""
    annotations = dict(annotations or {})
    payload = {
        "name": name,
        "description": description,
        "inputSchema": dict(schema),
        "annotations": annotations,
    }
    return ContentEnvelope(
        source="webmcp_page",
        content_type="tool_definition",
        trust="untrusted",
        instruction_authority="none",
        origin=origin,
        tool_name=name,
        content=payload,
        content_hash=content_hash(payload),
    )


def wrap_tool_output(
    *,
    origin: str,
    name: str,
    value: Any,
    untrusted: bool,
    high_risk: bool = False,
) -> ContentEnvelope:
    """Wrap a WebMCP result so callers can distinguish data from instructions."""
    if untrusted or high_risk:
        encoded = encode_untrusted(value)
        return ContentEnvelope(
            source="webmcp_tool_output",
            content_type="tool_result",
            trust="untrusted",
            instruction_authority="none",
            origin=origin,
            tool_name=name,
            content=encoded,
            encoding="base64",
            content_hash=content_hash(value),
        )
    marked, boundary = spotlight(value)
    return ContentEnvelope(
        source="webmcp_tool_output",
        content_type="tool_result",
        trust="page_controlled_data",
        instruction_authority="none",
        origin=origin,
        tool_name=name,
        content=marked,
        encoding="spotlight",
        boundary=boundary,
        content_hash=content_hash(value),
    )


def wrap_webmcp_error(
    *,
    origin: str,
    name: str,
    error: str,
) -> ContentEnvelope:
    marked, boundary = spotlight(error)
    return ContentEnvelope(
        source="webmcp_error",
        content_type="error",
        trust="untrusted",
        instruction_authority="none",
        origin=origin,
        tool_name=name,
        content=marked,
        encoding="spotlight",
        boundary=boundary,
        content_hash=content_hash(error),
    )
