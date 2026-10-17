# Codex skill invocation audit (#433)

Run `python tools/audit_codex_invocation.py --root skills/skills-codex > codex-policy-report.json`.

The report inventories the Codex mirror, detects malformed/duplicate opt-in invocation policies and lists skills referenced by other skills. A reference is a **conservative warning**, not evidence of a successful runtime sub-skill invocation.

The audit is read-only. It never sets `allow_implicit_invocation: false`, because a maintainer raised a risk that explicit-only configuration may disable parent-to-child skill calls. Before changing policies, verify actual `$child-skill` invocation with the installed Codex CLI and record its version. Run `python tools/audit_codex_invocation.py --fail-on-referenced-explicit` to fail closed for any potentially blocked references.

## Runtime diagnostic with real Codex CLI

Run `python tools/probe_codex_invocation.py` with an installed `codex` executable. The script initializes a disposable Git project with two control skills and calls `codex debug prompt-input` (no model requests or credentials needed).

Verified on GitHub-hosted Ubuntu with **codex-cli 0.163.0**:

- Default skill: present in model-visible `<skills_instructions>` metadata.
- Skill with `policy.allow_implicit_invocation: false`: absent from the implicit catalog.
- This verifies discovery/context filtering **only**. It does not establish that a parent ARIS Skill can invoke an explicit-only child. The debug surface does not expose the selected Skill's complete body in either control.

CI evidence: https://github.com/SiyuanChenToDo/Auto-claude-code-research-in-sleep/actions/runs/39044605650

Before any shipping policy changes, exercise a real parent-to-child workflow through Codex CLI in the relevant execution mode, and ensure the child Skill body and artifacts are actually produced. Upstream Codex has an open report that `allow_implicit_invocation: false` can suppress explicit `$skill` expansion in some surfaces: https://github.com/openai/codex/issues/40600 . Keep current defaults until that compatibility gate is satisfied.
