#!/usr/bin/env python3
"""Probe Codex's *actual prompt assembly* for explicit-only skills (issue #433).

This does not make API/model calls and does not write invocation policies to ARIS.
The experiment uses two disposable scratch skills and Codex's debug surface.
"""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path


def run_codex(project: Path, home: Path, prompt: str) -> tuple[int, str, str]:
    env = {**os.environ, "CODEX_HOME": str(home)}
    result = subprocess.run(
        ["codex", "debug", "prompt-input", prompt],
        cwd=project,
        env=env,
        capture_output=True,
        text=True,
        timeout=90,
        check=False,
    )
    return result.returncode, result.stdout, result.stderr


def main() -> int:
    version = subprocess.run(["codex", "--version"], capture_output=True, text=True, check=True)
    print("Codex version:", version.stdout.strip())
    with tempfile.TemporaryDirectory(prefix="aris-codex-skill-probe-") as tmp:
        root = Path(tmp)
        project = root / "project"
        home = root / "codex-home"
        skills = project / ".agents" / "skills"
        home.mkdir()
        skills.mkdir(parents=True)
        # Codex project-scoped skill discovery requires a project trust context.
        subprocess.run(["git", "init", "-q"], cwd=project, check=True)
        for name in ("plain-probe", "policy-probe"):
            skill_dir = skills / name
            skill_dir.mkdir()
            marker = name.upper().replace("-", "_") + "_BODY_MARKER"
            (skill_dir / "SKILL.md").write_text(
                f"---\nname: {name}\ndescription: Test explicit invocation of {name}.\n---\n\n"
                f"Read and follow this unique instruction: {marker}\n",
                encoding="utf-8",
            )
            if name == "policy-probe":
                metadata = skill_dir / "agents"
                metadata.mkdir()
                (metadata / "openai.yaml").write_text(
                    "policy:\n  allow_implicit_invocation: false\n", encoding="utf-8"
                )
        visibility = {}
        for skill in ("plain-probe", "policy-probe"):
            rc, stdout, stderr = run_codex(project, home, f"${skill} confirm discovery")
            if rc:
                print(f"{skill}: debug command failed rc={rc}; stderr={stderr[-1100:]!r}")
                return 2
            try:
                payload = json.loads(stdout)
            except json.JSONDecodeError:
                print(f"{skill}: debug output not JSON; snippet={stdout[:1000]!r}")
                return 2
            # Inspect only the actual developer-visible skill catalog. A name in
            # the user's literal '$skill' prompt is NOT proof of discovery.
            catalogs = [
                block.get("text", "")
                for item in payload if isinstance(item, dict) and item.get("role") == "developer"
                for block in item.get("content", []) if isinstance(block, dict)
                if "<skills_instructions>" in block.get("text", "")
            ]
            if not catalogs:
                print(f"{skill}: no <skills_instructions> catalog in Codex debug output")
                return 2
            visible = any(f"- {skill}:" in catalog for catalog in catalogs)
            visibility[skill] = visible
            print(f"{skill}: included in model-visible catalog={visible}")
        print("Observed skill metadata filtering:", json.dumps(visibility, sort_keys=True))
        if not visibility["plain-probe"]:
            print("INCONCLUSIVE: control skill not discovered")
            return 2
        if visibility["policy-probe"]:
            print("FAIL: explicit-only policy did not hide skill from implicit catalog")
            return 3
        print("PASS: policy suppresses implicit skill metadata in actual Codex CLI")
        print("LIMITATION: explicit parent-to-child invocation is not tested by debug prompt-input")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
