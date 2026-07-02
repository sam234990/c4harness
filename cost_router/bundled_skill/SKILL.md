---
name: cost-router
description: Decompose long or context-heavy coding tasks, delegate verifiable analysis or bounded patches to lower-cost Codex or Claude CLI workers, and launch asynchronous workloads monitored by a resumable Claude session that returns significant and terminal events to Codex. Use for broad investigations, debugging, reviews, migrations, repository understanding, test-failure analysis, separable implementation, or long-running training, evaluation, build, test, data, and deployment commands. Do not use for short tasks whose delegation overhead exceeds the work.
---

# Cost Router

Use the main Codex session as orchestrator. Delegate read-only investigation or isolated patch proposals with explicit write allowlists.

## Workflow

1. Restate the user's final objective and identify the decisions or edits that must remain with the main agent.
2. Decide whether delegation is worthwhile. Delegate when at least one subtask is independently answerable, has bounded inputs, produces verifiable evidence, and removes substantial reading or analysis from the main context.
3. Create a small task plan. Prefer 2-5 meaningful subtasks over many fragments. Choose one concise parent task label and reuse it for every delegated call in this user task.
4. Give each subtask one concrete goal, only the necessary read paths, optional context packs, and an expected evidence-based result. For editing, name every allowed write path explicitly.
5. Invoke Cost Router from the repository being examined. Prefer Claude CLI when the user requests it, when a patch proposal is needed, or when no Codex provider is configured. For analysis:

```bash
cost-router run \
  --backend claude-cli \
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
  --mode patch \
  --parent-task-label "<same concise parent task>" \
  --goal "<one bounded implementation subtask>" \
  --repo "$PWD" \
  --path <read-only-context-path> \
  --write-path <allowed-file-to-change> \
  --execute \
  --json
```

6. For a configured Responses-compatible Codex worker, omit `--backend claude-cli` and provide the appropriate `--env-file` when it is not `.env`.
7. Inspect `verification`, evidence, risks, and the raw output path. Treat worker conclusions as proposals. Check important claims against repository files or tests before relying on them.
8. If a worker lacks context, rerun a narrower subtask with an additional context pack. If it fails verification twice, stop delegating that subtask and handle it in the main session.
9. Inspect an accepted `proposed_patch_path` before applying it. Apply or reproduce the change in the main workspace, then run the relevant tests in the main session.
10. Report which work was delegated and distinguish worker findings from conclusions independently verified by the main agent. The global ledger automatically associates calls with the current Codex thread when `CODEX_THREAD_ID` is available.

## Asynchronous Workflow

Use an asynchronous task when the user asks Codex to start a long-running command and have a worker monitor it after the current turn. This is suitable for training, evaluation, builds, test suites, data processing, deployments, and other workloads with observable logs or process completion.

1. Confirm the exact workload command, working directory, relevant logs, and any success or failure marker files. Do not invent or silently broaden a destructive command.
2. Start the generic runtime from the workload repository:

```bash
cost-router async-task start \
  --goal "<what the worker should monitor and report>" \
  --repo "$PWD" \
  --command "<long-running command>" \
  --log-path <optional-live-log> \
  --interval 60 \
  --json
```

3. Let `--callback auto` capture `CODEX_THREAD_ID`. Do not pass `--callback none` when the user expects completion or failure to return to this Codex thread.
4. Return the task ID and task directory to the user after the detached controller starts. Do not block the Codex turn by polling healthy progress.
5. On a callback, inspect `cost-router async-task status <task-id>` and `events <task-id>`, then decide whether to report completion, diagnose, patch, or explicitly start a replacement workload.
6. Use `stop <task-id>` for cancellation and `retry-callbacks <task-id>` when a queued Codex resume failed.

The Python controller owns process exit, timeout, marker files, and cancellation. Claude uses one resumable session for bounded snapshots. Healthy observations stay in memory; completion, failure, timeout, cancellation, stalled work, and requests for input may resume Codex.

## Decomposition Rules

- Decompose by independent questions or outputs, not by arbitrary file counts.
- Include only paths the worker needs. Do not delegate secrets or private data without explicit user approval.
- Use parallel-shaped subtasks for independent review dimensions, subsystem investigations, or alternative hypotheses.
- Use sequential subtasks when one result determines the next task's inputs.
- Use patch mode only when the writable file set is small and explicit. Use read-only mode first when ownership or scope is uncertain.
- Skip delegation for tiny fixes, tightly coupled reasoning that cannot be summarized safely, credential-sensitive work, destructive operations, or tasks where verification would cost as much as doing the work directly.

## Current Boundaries

- The router CLI executes one worker task per invocation. The main Codex session currently performs decomposition and scheduling.
- The async runtime can own one workload per task and resume a Claude monitoring session, but it does not yet recover active workloads after a controller or machine restart.
- Claude CLI supports bounded patch proposals in a staged workspace. Codex subagent delegation remains read-only.
- Patch workers edit copies, never the target repository. The main agent reviews and applies accepted patches.
- Multiple delegated calls are not yet represented as one persisted task DAG.
- Backend selection is explicit rather than learned or automatic.
- Memory and verifier output assist orchestration but do not replace direct validation of high-impact claims.
