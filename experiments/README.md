# Experiments

This directory contains small, sanitized experiments used to validate the project direction.

The current experiments are intentionally minimal:

- `sample-skillopt-run.log`: synthetic SkillOpt-like failure log used to test read-only log analysis without exporting real project data.
- `qwen-explorer.toml`: example Codex custom subagent config that points to a Responses-compatible Qwen provider by provider id only. It does not contain secrets.

Do not commit real API keys, real provider endpoints, raw model responses, or private project logs here.
