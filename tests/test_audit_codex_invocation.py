"""Regression tests for the read-only Codex policy auditor."""
import tempfile
from pathlib import Path

from tools.audit_codex_invocation import audit, policy_state


def test_missing_policy_keeps_default():
    with tempfile.TemporaryDirectory() as tmp:
        assert policy_state(Path(tmp) / "openai.yaml") == ("implicit-default", None)


def test_explicit_only_policy():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "openai.yaml"
        path.write_text("policy:\n  allow_implicit_invocation: false\n")
        assert policy_state(path) == ("explicit-only", None)


def test_duplicate_policy_is_rejected():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "openai.yaml"
        path.write_text("policy:\n  allow_implicit_invocation: false\n  allow_implicit_invocation: true\n")
        assert policy_state(path)[0] == "invalid"


def test_referenced_explicit_child_is_reported_without_editing():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        parent, child = root / "parent", root / "child"
        parent.mkdir()
        (child / "agents").mkdir(parents=True)
        (parent / "SKILL.md").write_text("invoke /child, or ../child/SKILL.md")
        (child / "SKILL.md").write_text("child instructions")
        (child / "agents" / "openai.yaml").write_text("policy:\n  allow_implicit_invocation: false\n")
        report = audit(root)
        assert report["skill_count"] == 2
        assert report["referenced_explicit_only"] == ["child"]
        assert report["runtime_verified"] is False


def test_agent_ui_metadata_without_policy_is_valid_default():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "openai.yaml"
        path.write_text('interface:\n  display_name: "Research skill"\n')
        assert policy_state(path) == ("implicit-default", None)
