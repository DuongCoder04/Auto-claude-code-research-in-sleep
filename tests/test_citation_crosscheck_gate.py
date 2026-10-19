"""CI guard for the /citation-crosscheck deterministic verifier gate (cx_verify.py).

cx_verify.py is a load-bearing gate: it decides which citations reach MATCH/MINOR without a
main-agent fetch. Its correctness is covered by an in-script ``--selftest`` battery, and the
skill ships two byte-identical host copies (Claude Code mainline + Codex mirror). This test
runs both — pre-merge, in the normal ``pytest tests/`` suite — so a regression in the gate or a
drift between the two copies fails CI instead of being discovered on a live run.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
MAIN_GATE = REPO_ROOT / "skills" / "citation-crosscheck" / "scripts" / "cx_verify.py"
CODEX_GATE = REPO_ROOT / "skills" / "skills-codex" / "citation-crosscheck" / "scripts" / "cx_verify.py"


def test_gate_scripts_exist() -> None:
    assert MAIN_GATE.is_file(), f"missing {MAIN_GATE}"
    assert CODEX_GATE.is_file(), f"missing {CODEX_GATE}"


def test_mirror_copies_are_byte_identical() -> None:
    # A fix applied to one host copy must be applied to the other, verbatim; otherwise the
    # two hosts silently run different gates.
    assert MAIN_GATE.read_bytes() == CODEX_GATE.read_bytes(), (
        "cx_verify.py mainline and Codex-mirror copies differ — re-sync them byte-for-byte "
        "(cp skills/citation-crosscheck/scripts/cx_verify.py "
        "skills/skills-codex/citation-crosscheck/scripts/cx_verify.py)"
    )


def _run_selftest(path: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(path), "--selftest"],
        capture_output=True,
        text=True,
    )


def test_selftest_passes_mainline() -> None:
    result = _run_selftest(MAIN_GATE)
    assert result.returncode == 0, (
        f"cx_verify.py --selftest failed (exit {result.returncode}):\n"
        f"{result.stdout}\n{result.stderr}"
    )
    # Require an "N/N passed" summary (all cases), not just the substring "passed" — a
    # partial-failure run prints e.g. "94/107 passed" and must not read as success.
    assert re.search(r"\b(\d+)/\1 passed\b", result.stdout), result.stdout


def test_selftest_passes_codex_mirror() -> None:
    result = _run_selftest(CODEX_GATE)
    assert result.returncode == 0, (
        f"Codex-mirror cx_verify.py --selftest failed (exit {result.returncode}):\n"
        f"{result.stdout}\n{result.stderr}"
    )
    # Require an "N/N passed" summary (all cases), not just the substring "passed" — a
    # partial-failure run prints e.g. "94/107 passed" and must not read as success.
    assert re.search(r"\b(\d+)/\1 passed\b", result.stdout), result.stdout


def test_manifest_cli_covers_the_documented_workflow(tmp_path: Path) -> None:
    """Build the coverage root from a real .bib, then run the A/B/C gate."""
    record = "@article{paper, title={Deep Nets}, author={Smith, Alice}, year={2020}, journal={ICML}, doi={10.1/example}}"
    bib = tmp_path / "refs.bib"
    bib.write_text(record, encoding="utf-8")
    keymap = tmp_path / "keymap.tsv"
    keymap.write_text("01\tpaper\n", encoding="utf-8")
    manifest = tmp_path / "manifest.tsv"
    built = subprocess.run(
        [sys.executable, str(MAIN_GATE), "--build-manifest", "--bib", str(bib),
         "--keymap", str(keymap), "--out-manifest", str(manifest)],
        capture_output=True, text=True,
    )
    assert built.returncode == 0, built.stderr
    a = {"shard_id": "A", "entries": [{"dedup_key": "01", "key": "paper", "bibtex": record}]}
    b = {"shard_id": "B", "blind": True, "entries": [{"dedup_key": "01", "found": True,
         "bibtex": record, "sources_tried": ["crossref"]}]}
    c = {"shard_id": "C", "entries": [{"dedup_key": "01", "flags": []}]}
    paths = [tmp_path / f"{label}.json" for label in ("a", "b", "c")]
    output = tmp_path / "gate.json"

    def run_gate():
        for path, value in zip(paths, (a, b, c)):
            path.write_text(json.dumps(value), encoding="utf-8")
        return subprocess.run(
            [sys.executable, str(MAIN_GATE), "--a", str(paths[0]), "--b", str(paths[1]),
             "--c", str(paths[2]), "--expect", "1", "--expect-manifest", str(manifest),
             "--json", str(output)], capture_output=True, text=True,
        )

    clean = run_gate()
    assert clean.returncode == 0, clean.stderr
    assert json.loads(output.read_text())["counts"] == {"MATCH": 1, "MINOR": 0, "ESCALATE": 0}

    b["blind"] = False
    heuristic = run_gate()
    assert heuristic.returncode == 0, heuristic.stderr
    assert json.loads(output.read_text())["entries"][0]["verdict"] == "ESCALATE"

    b["blind"] = True
    b["entries"][0]["sources_tried"] = ["crossref(429)"]
    degraded = run_gate()
    assert degraded.returncode == 0, degraded.stderr
    assert json.loads(output.read_text())["entries"][0]["verdict"] == "ESCALATE"

    # A keeps the same ordinal and title but substitutes another cite key.
    a["entries"][0]["key"] = "substituted"
    substituted = run_gate()
    assert substituted.returncode == 1
    assert "coverage manifest mismatch" in substituted.stderr
