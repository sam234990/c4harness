---
name: cost-router
description: Decompose long or context-heavy coding tasks, delegate verifiable analysis or bounded patches to lower-cost Codex or Claude CLI workers, and launch asynchronous workloads monitored by a resumable Claude session that stores significant and terminal events in a durable local Inbox. Use for broad investigations, debugging, reviews, migrations, repository understanding, test-failure analysis, separable implementation, or long-running training, evaluation, build, test, data, and deployment commands. Do not use for short tasks whose delegation overhead exceeds the work.
---

# Cost Router

Use the main Codex session as orchestrator. Delegate read-only investigation or isolated patch proposals with explicit write allowlists.

## External Delegation Policy

Treat user intent and host enforcement as separate layers. The user decides whether C4Harness may attempt a bounded transfer; Codex sandbox, approval, organization, or data-egress policy still makes the final enforcement decision.

- A request to use Claude or another external worker expresses delegation intent, but it is not informed consent unless the user has also been told what private data leaves the machine and what the worker may do. Before the first private transfer, provide the bounded risk summary below and pause for explicit confirmation. After confirmation, pass `--external-policy allow --data-classification private`, include only necessary paths, and describe the confirmed scope accurately in any approval justification.
- When the user requests delegation or cost routing but does not name an external provider, do not infer permission to send private repository content. Prefer a Codex subagent or local provider; ask before selecting Claude for private content.
- For public or synthetic inputs, pass `--external-policy ask` with `--data-classification public` or `synthetic`.
- When the user prohibits external transfer, pass `--external-policy never` or avoid the external backend entirely.
- Never include credentials, secret files, private keys, access tokens, or unrelated repository content, even under `allow`.
- `allow` records explicit user authorization; it does not override host policy.

### Risk Disclosure and Consent

For private external delegation, state all applicable risks in one concise summary:

- external destination/provider and whether it is authenticated by a local CLI;
- exact files, directories, log snapshots, prompts, or artifacts that may be transmitted;
- whether the worker is read-only or may edit an isolated copy, plus the complete write allowlist;
- possible exposure of proprietary code, paths, test names, runtime metadata, errors, or user content;
- provider-side processing, retention, logging, and policy risks that C4Harness cannot control;
- local side effects: staged copies, patch artifacts, SQLite ledger entries, and subprocesses;
- for async work, repeated snapshots, resumable Claude session state, durable Inbox events, and the fact that Codex is not automatically awakened;
- confirmation that credentials and unrelated files are excluded, and that host policy may still deny the operation.

Ask the user to approve this exact bounded transfer. Do not execute while confirmation is pending. A prior confirmation remains valid only for the same parent task, provider, data classification, path set, operation mode, and async/Inbox behavior; broadened scope requires a new summary.

If the host rejects an attempted external call:

1. Do not retry immediately and do not use an indirect command, alternate path, or subprocess to bypass the rejection.
2. Explain the rejection and present one consolidated risk summary for the exact retry, including any risk newly revealed by the host.
3. Wait for explicit user approval after that disclosure.
4. Retry the same bounded operation once. If it is rejected again, stop external delegation for that subtask and offer a permitted local/Codex backend or main-agent execution.
5. Never describe a blocked call as a worker failure, and never substitute synthetic data while claiming the private task succeeded.

## Workflow

1. Restate the user's final objective and identify the decisions or edits that must remain with the main agent.
2. Decide whether delegation is worthwhile. Delegate when at least one subtask is independently answerable, has bounded inputs, produces verifiable evidence, and removes substantial reading or analysis from the main context.
3. Create a small task plan. Prefer 2-5 meaningful subtasks over many fragments. Choose one concise parent task label and reuse it for every delegated call in this user task.
4. Give each subtask one concrete goal, only the necessary read paths, optional context packs, and an expected evidence-based result. For editing, name every allowed write path explicitly.
5. Before any private external transfer, present the exact bounded risk summary and wait for informed consent unless that identical scope was already confirmed for this parent task.
6. Invoke Cost Router from the repository being examined. Prefer Claude CLI when the user requests it, when a patch proposal is needed, or when no Codex provider is configured. For analysis:

```bash
cost-router run \
  --backend claude-cli \
  --external-policy allow \
  --data-classification private \
  --parent-task-label "<concise parent task>" \
  --goal "<one bounded read-only subtask>" \
  --repo "$PWD" \
  --path <relevant-path> \
  --context-pack <optional-background-file> \
  --execute \
  --json
```

For an isolated patch proposal:

```bash
cost-router run \
  --backend claude-cli \
  --external-policy allow \
  --data-classification private \
  --mode patch \
  --parent-task-label "<same concise parent task>" \
  --goal "<one bounded implementation subtask>" \
  --repo "$PWD" \
  --path <read-only-context-path> \
  --write-path <allowed-file-to-change> \
  --execute \
  --json
```

7. For a configured Responses-compatible Codex worker, omit `--backend claude-cli` and provide the appropriate `--env-file` when it is not `.env`.
   When the user selected a global Worker entry, prefer `--worker-id <id>` over
   repeating backend/model flags. For Claude Code, C4Harness passes that entry's
   `model_alias` to `claude --model`; the user's Claude environment may map an
   alias such as `opus` to a custom upstream model such as `mimo-v2.5-pro`.
8. Inspect `verification`, evidence, risks, and the raw output path. Treat worker conclusions as proposals. Check important claims against repository files or tests before relying on them.
9. If a worker lacks context, rerun a narrower subtask with an additional context pack. If it fails verification twice, stop delegating that subtask and handle it in the main session.
10. Inspect an accepted `proposed_patch_path` before applying it. Apply or reproduce the change in the main workspace, then run the relevant tests in the main session.
11. Report which work was delegated and distinguish worker findings from conclusions independently verified by the main agent. The global ledger automatically associates calls with the current Codex thread when `CODEX_THREAD_ID` is available.

## Codex-Planned Decomposition

For a multi-deliverable or capability-sensitive task, use the current Codex
thread's complete conversation, active Skill, repository knowledge, user policy,
and Plan Mode state to author a structured task proposal. C4Harness does not call
another planning model. Codex proposes semantic nodes; C4 validates the contracts
and chooses workers from capabilities, preferences, and verified History.

Do not choose a worker or model in the proposal. Describe required capabilities.
Write a version-1 JSON proposal to a local ignored path such as
`.cost-router/proposals/<task>.json` using this shape:

```json
{
  "version": 1,
  "root_goal": "<complete user objective>",
  "requirements": [
    {"id": "R1", "text": "<deliverable>", "kind": "deliverable", "required": true},
    {"id": "C1", "text": "<boundary>", "kind": "constraint", "required": true}
  ],
  "constraints": ["<global execution or safety boundary>"],
  "acceptance_criteria": [
    {"id": "A1", "description": "<root completion condition>", "check": "semantic_review", "requirement_refs": ["R1"]}
  ],
  "interaction_mode": "execute",
  "unresolved_questions": [],
  "nodes": [
    {
      "node_id": "node-1",
      "kind": "work",
      "objective": "<one bounded outcome>",
      "requirement_refs": ["R1", "C1"],
      "dependencies": [],
      "context_packs": [],
      "artifact_inputs": [],
      "allowed_paths": ["<minimum read scope>"],
      "write_paths": [],
      "execution_mode": "read_only",
      "output_type": "report",
      "hard_capabilities": {"modalities": ["text"], "tools": ["read", "grep"]},
      "soft_capability_weights": {"debugging": 0.8, "long_context": 0.4},
      "verifier_plan": {
        "template_checks": ["requirement_coverage"],
        "evidence_requirements": ["Cite inspectable repository evidence"],
        "semantic_criteria": ["<criterion requiring harness judgment>"],
        "root_contribution": "Satisfies R1",
        "inconclusive_policy": "escalate"
      },
      "root_contribution": "Satisfies R1"
    }
  ]
}
```

Valid hard fields are `modalities`, `tools`, `write_isolation`,
`network_required`, `structured_output_required`, `min_context_tokens`,
`persistent_session_required`, `provider_protocols`, and `privacy_zones`.
Valid soft dimensions are `code_implementation`, `debugging`,
`frontend_visual`, `documentation`, `architecture`, `long_context`, and
`test_generation`, with weights from 0 to 1.

Verifier template expressions are `file_exists:<path>`,
`file_contains:<path>`, `command_exit_zero:<command>`,
`output_matches:<regex>`, `json_schema_valid:<path>`, `tests_pass`,
`changed_paths_within_allowlist`, `patch_non_empty`, and
`requirement_coverage`. Patch nodes receive the two patch-safety checks
automatically. Keep semantic criteria separate from deterministic templates.

Compile and assign without calling a model or executing a worker:

```bash
cost-router decompose \
  --plan-file .cost-router/proposals/<task>.json \
  --repo "$PWD" \
  --json
```

Inspect schema/coverage errors, graph shape, hard exclusions, score breakdown,
assignment confidence, verifier plan, and risk manifest. Revise the proposal if
C4 rejects it. The legacy `--goal/--requirement/--skill-step` preview remains a
fallback, but new multi-step work should use `--plan-file`. Decomposition does
not grant external-transfer consent and does not execute the graph.

## Asynchronous Workflow

Use an asynchronous task when the user asks Codex to start a long-running command and have a worker monitor it after the current turn. This is suitable for training, evaluation, builds, test suites, data processing, deployments, and other workloads with observable logs or process completion.

1. Confirm the exact workload command, working directory, relevant logs, and any success or failure marker files. Do not invent or silently broaden a destructive command.
2. Identify every repeated snapshot source, the check interval, session persistence, and terminal/significant Inbox events. Present the async risk summary and wait for informed consent.
3. Start the generic runtime from the workload repository:

```bash
cost-router async-task start \
  --external-policy allow \
  --data-classification private \
  --goal "<what the worker should monitor and report>" \
  --repo "$PWD" \
  --command "<long-running command>" \
  --log-path <optional-live-log> \
  --interval 60 \
  --json
```

4. Apply the same external delegation policy before sending log snapshots. Use `allow/private` only for the user-confirmed snapshot and Inbox scope; otherwise ask first or use `--backend none`.
5. Terminal/significant events are always written to the durable local Inbox. Do not claim that this wakes the visible Codex UI. Inspect with `cost-router async-task inbox --unread-only` and acknowledge handled items with `cost-router async-task ack <inbox-id>`.
6. Return the task ID and task directory to the user after the detached runtime process starts. Do not block the Codex turn by polling healthy progress.
7. When the host or user surfaces an Inbox event, inspect `cost-router async-task status <task-id>` and `events <task-id>`, then decide whether to report completion, diagnose, patch, or explicitly start a replacement workload.
8. Use `stop <task-id>` for cancellation.

The Python runtime process owns scheduling, process exit, timeout, marker files, and cancellation without using model tokens. It checks file metadata before invoking Claude, skips unchanged snapshots, and backs off repeated idle checks. Claude uses one resumable session only for changed snapshots and terminal summaries. Completion, failure, timeout, cancellation, stalled work, and requests for input enter the durable Inbox by default.

## Decomposition Rules

- Decompose by independent questions or outputs, not by arbitrary file counts.
- Include only paths the worker needs. Do not delegate secrets or private data without explicit user approval.
- Use parallel-shaped subtasks for independent review dimensions, subsystem investigations, or alternative hypotheses.
- Use sequential subtasks when one result determines the next task's inputs.
- Use patch mode only when the writable file set is small and explicit. Use read-only mode first when ownership or scope is uncertain.
- Skip delegation for tiny fixes, tightly coupled reasoning that cannot be summarized safely, credential-sensitive work, destructive operations, or tasks where verification would cost as much as doing the work directly.

## Current Boundaries

- `cost-router decompose` previews and records a contract graph; this command itself does not execute workers.
- The application API now provides deterministic sequential graph scheduling, per-node delegation, contract-aware verification, History outcomes, and Root Verification. The public `run` CLI still executes one worker task per invocation; a first-class graph-run CLI remains future integration work.
- The async runtime owns one workload per task and uses Claude only for bounded observations and terminal summaries.
- Inbox delivery is durable. Codex currently has no public interface through which an external worker can wake the currently visible IDE conversation and confirm delivery, so C4Harness does not attempt automatic wake-up.
- Claude CLI supports bounded patch proposals in a staged workspace. Codex subagent delegation remains read-only.
- Patch workers edit copies, never the target repository. The main agent reviews and applies accepted patches.
- Graph execution currently consumes an in-memory compiled plan with injected backend factories; restoring and executing a persisted plan snapshot is not yet a public CLI workflow.
- Backend selection is explicit rather than learned or automatic.
- Memory and verifier output assist orchestration but do not replace direct validation of high-impact claims.
