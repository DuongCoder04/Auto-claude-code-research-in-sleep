#!/usr/bin/env python3
"""Read-only Codex skill policy audit for ARIS issue #433.

References are conservative warnings, not proof that a child skill cannot
be invoked. No policies are modified and no runtime compatibility is assumed.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

INVOKE = re.compile(r"(?<![\w/])(?:/|\$)([a-z][a-z0-9-]*)\b")
LINK = re.compile(r"\.\./([a-z][a-z0-9-]*)/SKILL\.md\b")
POLICY = re.compile(r"(?m)^policy:\s*\n((?:[ \t]+[^\n]*\n|\s*\n)*)")
FLAG = re.compile(r"(?m)^[ \t]+allow_implicit_invocation:[ \t]*(true|false)[ \t]*(?:#.*)?$")


def policy_state(file: Path) -> tuple[str, str | None]:
    if not file.exists():
        return "implicit-default", None
    raw = file.read_text(encoding="utf-8")
    blocks = POLICY.findall(raw)
    if not blocks:
        # Codex agent UI metadata may exist without an invocation policy.
        return "implicit-default", None
    if len(blocks) != 1:
        return "invalid", "expected exactly one policy: mapping"
    values = FLAG.findall(blocks[0])
    if len(values) != 1:
        return "invalid", "expected exactly one boolean allow_implicit_invocation"
    return ("implicit-allowed" if values[0] == "true" else "explicit-only"), None


def audit(root: Path) -> dict:
    skills = {p.parent.name: p for p in sorted(root.glob("*/SKILL.md"))}
    if not skills:
        raise ValueError(f"Missing skills in {root}")
    referenced_by = {name: set() for name in skills}
    for parent, path in skills.items():
        body = path.read_text(encoding="utf-8")
        for child in (set(INVOKE.findall(body)) | set(LINK.findall(body))) & skills.keys():
            if child != parent:
                referenced_by[child].add(parent)
    rows, errors = [], []
    for name, path in skills.items():
        policy = path.parent / "agents" / "openai.yaml"
        state, error = policy_state(policy)
        if error:
            errors.append(f"{policy}: {error}")
        rows.append({"skill": name, "invocation": state, "referenced_by": sorted(referenced_by[name])})
    return {"skill_count": len(skills), "explicit_only_count": sum(x["invocation"] == "explicit-only" for x in rows), "referenced_explicit_only": [x["skill"] for x in rows if x["invocation"] == "explicit-only" and x["referenced_by"]], "invalid_policies": errors, "runtime_verified": False, "skills": rows}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1] / "skills" / "skills-codex")
    parser.add_argument("--fail-on-referenced-explicit", action="store_true")
    options = parser.parse_args()
    result = audit(options.root)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return int(bool(result["invalid_policies"] or (options.fail_on_referenced_explicit and result["referenced_explicit_only"])))


if __name__ == "__main__":
    raise SystemExit(main())
