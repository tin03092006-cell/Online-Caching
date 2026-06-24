from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class NormalizedTraceStats:
    path: str
    num_requests: int
    num_unique_items: int
    sha256: str
    has_empty_lines: bool
    has_multitoken_lines: bool


def normalize_item_token(raw_token: str) -> str:
    """Normalize one parsed request item into the canonical internal form."""
    return raw_token.strip()


def read_normalized_trace(trace_path: Path) -> list[str]:
    """Read a prepared one-item-per-line trace.

    Prepared benchmark traces should already have exactly one request item per
    line. This reader strips whitespace and drops empty lines so downstream
    algorithms consume the same canonical item IDs.
    """
    if not trace_path.exists():
        raise FileNotFoundError(f"Trace file not found: {trace_path}")

    request_items: list[str] = []
    with trace_path.open("r", encoding="utf-8") as trace_file:
        for line in trace_file:
            item = normalize_item_token(line)
            if item:
                request_items.append(item)

    if not request_items:
        raise ValueError(f"Trace file is empty after normalization: {trace_path}")

    return request_items


def trace_sha256(request_trace: list[str]) -> str:
    """Hash the canonical item sequence, independent of platform newlines."""
    hasher = hashlib.sha256()
    for item in request_trace:
        hasher.update(item.encode("utf-8"))
        hasher.update(b"\n")
    return hasher.hexdigest()


def inspect_prepared_trace(trace_path: Path) -> NormalizedTraceStats:
    """Validate and summarize a prepared trace file."""
    has_empty_lines = False
    has_multitoken_lines = False
    request_items: list[str] = []

    if not trace_path.exists():
        raise FileNotFoundError(f"Trace file not found: {trace_path}")

    with trace_path.open("r", encoding="utf-8") as trace_file:
        for raw_line in trace_file:
            stripped_line = raw_line.strip()
            if not stripped_line:
                has_empty_lines = True
                continue
            if len(stripped_line.split()) != 1:
                has_multitoken_lines = True
            request_items.append(normalize_item_token(stripped_line))

    if not request_items:
        raise ValueError(f"Trace file is empty after normalization: {trace_path}")

    return NormalizedTraceStats(
        path=str(trace_path),
        num_requests=len(request_items),
        num_unique_items=len(set(request_items)),
        sha256=trace_sha256(request_items),
        has_empty_lines=has_empty_lines,
        has_multitoken_lines=has_multitoken_lines,
    )


def write_trace_manifest(trace_paths: list[Path], output_path: Path) -> list[NormalizedTraceStats]:
    """Write a JSON manifest for prepared raw/official split traces."""
    stats = [inspect_prepared_trace(trace_path) for trace_path in trace_paths if trace_path.exists()]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps([asdict(item) for item in stats], indent=2),
        encoding="utf-8",
    )
    return stats
