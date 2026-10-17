# Codex skill invocation audit (#433)

Run `python tools/audit_codex_invocation.py --root skills/skills-codex > codex-policy-report.json`.

The report inventories the Codex mirror, detects malformed/duplicate opt-in invocation policies and lists skills referenced by other skills. A reference is a **conservative warning**, not evidence of a successful runtime sub-skill invocation.

The audit is read-only. It never sets `allow_implicit_invocation: false`, because a maintainer raised a risk that explicit-only configuration may disable parent-to-child skill calls. Before changing policies, verify actual `$child-skill` invocation with the installed Codex CLI and record its version. Run `python tools/audit_codex_invocation.py --fail-on-referenced-explicit` to fail closed for any potentially blocked references.
