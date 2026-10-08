#!/usr/bin/env python3
"""Check that verdict fields are declared after the evidence fields they summarize.

Prompt JSON examples are written in generation order. A verdict written before its
justification gets committed by the model before the justification exists, so the two can
contradict each other -- e.g. ``"result": "FAIL"`` followed by a ``reason`` concluding the
item actually complies. This script walks prompt Markdown files (the fenced JSON examples
inside them) and ``*_spec.json`` contracts, and reports every verdict field that appears
before a justification field in the same object.

Usage:
    python check_verdict_order.py <path> [<path> ...]

    <path> may be a file or a directory; directories are scanned recursively for *.md and
    *.json. Spec files are recognised by their ``*_spec.json`` name or by containing a
    ``properties``/``outputSchema`` field, and any other .json is skipped.

    In Markdown, a fenced ```json block that deliberately shows the anti-pattern opts out
    with a ``check-verdict-order: skip`` marker on the line directly above the fence.

Exit code is 1 when at least one violation is found, 0 otherwise.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

# Fields that state a judgement. Kept in sync with references/prompt-contract.md.
VERDICT_FIELDS = frozenset(
    {
        "result",
        "score",
        "status",
        "level",
        "grade",
        "rating",
        "verdict",
        "decision",
        "conclusion",
        "finalResult",
        "overallResult",
        "judgement",
        "judgment",
        "subjectiveScore",
        "applicability",
        "applicable",
        "requiresHumanReview",
    }
)

# Fields that carry the evidence a verdict is derived from.
JUSTIFICATION_FIELDS = frozenset(
    {
        "reason",
        "analysis",
        "rationale",
        "basis",
        "evidence",
        "objectiveFindings",
        "findings",
        "detail",
        "details",
        "explanation",
        "subjectiveAssessment",
        "comment",
        "comments",
        "opinion",
        "justification",
        "reasoning",
        "note",
        "notes",
        "objectives",
        "sealEvidence",
        "evidenceSummary",
        "supportConditions",
        "uncertainties",
        "scoreBreakdown",
        "arithmeticChecks",
    }
)

# Identity, constant and citation fields imply no judgement, so their position carries no
# information about whether a verdict was committed too early.
STRUCTURAL_FIELDS = frozenset(
    {
        "reviewStatus",
        "taskCode",
        "itemCode",
        "leafId",
        "expertNo",
        "groupType",
        "criterion",
        "code",
        "title",
        "maxScore",
        "materialType",
        "extractIds",
        "confidence",
        "subjectiveEvidenceStatus",
        "sourceInfo",
        "sources",
        "quotes",
        "excerpts",
        "evidenceRefs",
    }
)

VERDICT_SUFFIXES = ("Status", "Match", "Consistent")
JUSTIFICATION_SUFFIXES = (
    "Reason",
    "Evidence",
    "Findings",
    "Analysis",
    "Detail",
    "Opinion",
    "Assessment",
)

JSON_FENCE = re.compile(r"```json\s*\n(.*?)```", re.DOTALL)
SKIP_MARKER = "check-verdict-order: skip"


def is_verdict_field(name: str) -> bool:
    if name in STRUCTURAL_FIELDS:
        return False
    return name in VERDICT_FIELDS or name.endswith(VERDICT_SUFFIXES)


def is_justification_field(name: str) -> bool:
    if name in STRUCTURAL_FIELDS:
        return False
    return name in JUSTIFICATION_FIELDS or name.endswith(JUSTIFICATION_SUFFIXES)


def order_violations(value: Any, path: str = "") -> list[tuple[str, str]]:
    """Return one (path, key) pair per verdict field placed before its justification."""

    violations: list[tuple[str, str]] = []
    if isinstance(value, dict):
        keys = list(value)
        last_justification = max(
            (i for i, key in enumerate(keys) if is_justification_field(key)),
            default=-1,
        )
        for i, key in enumerate(keys):
            if is_verdict_field(key) and last_justification > i:
                violations.append((path or "<root>", key))
        for key, child in value.items():
            violations.extend(order_violations(child, f"{path}.{key}" if path else key))
    elif isinstance(value, list):
        for i, child in enumerate(value):
            violations.extend(order_violations(child, f"{path}[{i}]"))
    return violations


def looks_like_spec(data: Any, name: str) -> bool:
    if name.endswith("_spec.json"):
        return True
    if isinstance(data, dict):
        return any(key in data for key in ("properties", "outputSchema", "output_schema"))
    return False


def check_markdown(path: Path) -> list[tuple[str, str, str]]:
    """Return (location, path_in_json, key) violations from fenced JSON examples."""

    text = path.read_text(encoding="utf-8", errors="replace")
    found: list[tuple[str, str, str]] = []
    for block_no, match in enumerate(JSON_FENCE.finditer(text), start=1):
        # A block that intentionally demonstrates the anti-pattern is opted out with a
        # `check-verdict-order: skip` marker on the line right above the fence.
        preceding = [
            line for line in text[: match.start()].splitlines() if line.strip()
        ]
        if preceding and SKIP_MARKER in preceding[-1]:
            continue
        raw = match.group(1)
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            line_no = text[: match.start()].count("\n") + 1
            found.append((f"{path}:{line_no} (json block #{block_no})", "<parse error>", ""))
            continue
        for json_path, key in order_violations(parsed):
            found.append((str(path), f"block#{block_no} {json_path}", key))
    return found


def check_json(path: Path) -> list[tuple[str, str, str]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except json.JSONDecodeError as exc:
        return [(str(path), f"<invalid json: {exc}>", "")]
    if not looks_like_spec(data, path.name):
        return []
    return [(str(path), json_path, key) for json_path, key in order_violations(data)]


def collect(paths: list[str]) -> tuple[list[tuple[str, str, str]], int]:
    violations: list[tuple[str, str, str]] = []
    scanned = 0
    for raw in paths:
        root = Path(raw)
        if not root.exists():
            print(f"error: path not found: {root}", file=sys.stderr)
            continue
        files = [root] if root.is_file() else sorted(root.rglob("*"))
        for candidate in files:
            if not candidate.is_file():
                continue
            if candidate.suffix == ".md":
                scanned += 1
                violations.extend(check_markdown(candidate))
            elif candidate.suffix == ".json":
                try:
                    data = json.loads(candidate.read_text(encoding="utf-8", errors="replace"))
                except json.JSONDecodeError:
                    continue
                if looks_like_spec(data, candidate.name):
                    scanned += 1
                    violations.extend(check_json(candidate))
    return violations, scanned


def main(argv: list[str]) -> int:
    args = [a for a in argv[1:] if not a.startswith("-")]
    if not args:
        print(__doc__.strip())
        return 2

    violations, scanned = collect(args)
    if violations:
        print(f"verdict-order violations ({len(violations)} in {scanned} files):\n")
        for location, json_path, key in violations:
            print(f"  {location}\n    {json_path}: {key}")
        print(
            "\nA verdict field declared before its evidence lets the model commit a "
            "conclusion before the reasoning exists. Move every verdict field after the "
            "last evidence field in the same object, in both the .md example and the spec."
        )
        return 1

    print(f"ok: no verdict-order violations in {scanned} files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
