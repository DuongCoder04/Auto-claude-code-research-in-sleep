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
        results = {}
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
            rendered = json.dumps(payload)
            marker = skill.upper().replace("-", "_") + "_BODY_MARKER"
            present = marker in rendered
            results[skill] = present
            print(f"{skill}: explicitly selected body present={present}")
        print("Probe conclusion:", json.dumps(results, sort_keys=True))
        if not results["plain-probe"]:
            print("INCONCLUSIVE: plain skill is not discoverable; cannot test policy behavior")
            return 2
        if not results["policy-probe"]:
            print("RESTRICTION REPRODUCED: explicit-only policy suppressed explicit body injection")
            return 3
        print("EXPLICIT INVOCATION WORKS: both skill bodies appeared in real Codex prompt")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
