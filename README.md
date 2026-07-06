<p align="center">
  <img src="assets/c4.png" width="100" alt="C4Harness logo">
  <br>
  <strong style="font-size: 2em;">C4Harness</strong>
</p>

<p align="center"><em>C4 = Codex · Connect · Claude · Cost-router</em></p>

---

<p align="center">Connecting coding agents. Orchestrating collaboration. Routing by cost.</p>

<p align="center"><a href="README.md">English</a> | <a href="README_zh.md">简体中文</a></p>

<p align="center">
  <img alt="Status: Experimental" src="https://img.shields.io/badge/status-experimental-F59E0B">
  <img alt="Python 3.11+" src="https://img.shields.io/badge/python-3.11%2B-3776AB?logo=python&logoColor=white">
  <img alt="Workers: Claude CLI and Codex Subagent" src="https://img.shields.io/badge/workers-Claude_CLI_%7C_Codex_Subagent-171A1C">
  <img alt="Storage: SQLite" src="https://img.shields.io/badge/storage-SQLite-3B82F6?logo=sqlite&logoColor=white">
</p>

A cost-aware coding-agent router for delegating bounded work from a main Codex session to lower-cost or differently specialized workers.

> [!IMPORTANT]
> **C4Harness is experimental.** Claude CLI delegation, read-only Codex
> subagents, bounded patch proposals, shared-memory persistence, and the local
> dashboard work today. Generic asynchronous workloads can also be monitored by
> a resumable Claude session; significant and terminal events are stored in the
> durable C4 Inbox and surfaced by the Dashboard. Explainable decomposition preview is now available; graph execution,
> automatic scheduling, and fallback remain roadmap items.

## Project Status

| Capability | Status | Current behavior |
|---|---|---|
| Claude CLI worker | **Working** | Read-only analysis and isolated patch proposals |
| Codex subagent | **Working** | Responses-compatible, read-only delegated work |
| Write isolation | **Working** | Staged workspace, explicit write allowlist, patch output |
| Token ledger and dashboard | **Working** | Global SQLite ledger, usage charts, call details |
| Shared memory graph | **Prototype** | Control, worker, context, artifact, event, and lock records |
| Async worker runtime | **Prototype** | Detached workload, resumable Claude checks, durable Inbox notifications |
| Task decomposition | **Prototype** | Contract graph preview, capability assignment, confidence, risk, and history snapshot |
| Automatic routing and fallback | **Planned** | Backend selection is still explicit |
| OpenCode / other harnesses | **Planned** | Dashboard schema is ready; runtime adapter is not |

## Dashboard

Track delegated context, estimated main-agent savings, actual worker usage, and
backend distribution across projects and Codex sessions.

![C4Harness routing overview](assets/dashboard-overview.png)

Inspect each call's parent task, worker task, model, verification result, token
breakdown, raw output, and proposed patch.

![C4Harness call logs and detail drawer](assets/dashboard-call-logs.png)

The Dashboard also acts as the notification surface for asynchronous work. Its
overview highlights unread terminal results and running jobs; the Async Tasks
page groups them by the originating Codex thread and lets the user mark results
as handled.

## Target Architecture

![Cost-Aware Coding Router — end-to-end flow and multi-layer shared memory graph](assets/router.png)

The system follows a three-stage pipeline — **Task Router → Delegator → Verifier** — orchestrated by a Codex main session. Workers propose patches and facts; the verifier commits only validated results into the shared memory graph.

**Harness direction:**

| Harness | Role | Status |
|---|---|---|
| Claude Worker | analysis / patch / review | Working |
| Codex Subagent | lower-cost internal worker | Read-only working |
| OpenCode Worker | search / summarize / alternate harness | Planned |
| Other (Aider, Roo, Custom) | adapter-based extension | Research |

**Task decomposition (C4-ACD):**

The decomposition module (Adaptive Contract Decomposition) transforms a grounded user task into an executable, verifiable, and replannable plan. Rather than splitting a prompt into fragments, it:

1. **Grounds the task** — collects minimal sufficient context: user goals, skill workflow, repository facts, and worker capabilities.
2. **Defines completion** — constructs a Root Contract specifying what evidence or artifacts must exist for the task to be considered done.
3. **Decides fast vs. graph path** — evaluates whether decomposition actually reduces risk, context pressure, or capability gaps, or whether a single worker suffices.
4. **Generates a contract graph** — produces task nodes with objectives, dependencies, context packs, permissions, and per-node verifier plans.
5. **Assigns workers** — filters by hard capabilities (modalities, tools, write isolation, permissions) then scores soft capabilities, historical evidence, and user preferences.
6. **Replans from feedback** — adjusts the plan based on structured failure signals (missing context, capability mismatch, verification failure) while respecting attempt and token budgets.

Each node is a contract: it declares goals, inputs, artifacts, capabilities, permissions, and how success will be verified. Decomposition does not execute workers or write shared memory — it produces a plan consumed by the Delegator and Verifier.

**Multi-layer shared memory graph** (4 layers):

- **Main layer** — Main Private State: routing policy, private plan, final decisions.
- **Worker layer** — one Task Node per harness (Claude, Subagent, OpenCode, Other).
- **Context layer** — Context Packs A–D: read-only background material the main agent assigns to each worker.
- **File / Artifact layer** — shared artifacts (repo map, build log, test report, design notes) and private artifacts (scratchpad, trace, patch proposal, transcript).

Dependency types: **solid** = shared across workers, **dashed** = private to one worker, **dotted** = context reference.

Core invariant: **Workers propose → Verifier commits → Codex integrates.**

## Quick Start

### Prerequisites

- Python 3.11+
- At least one implemented worker backend configured (Codex subagent or Claude CLI)

### Install

```bash
git clone https://github.com/sam234990/c4harness.git
cd c4harness
python3 -m pip install -e .
cost-router setup
```

`setup` creates the personal ledger at `$XDG_DATA_HOME/cost-router/memory.sqlite3`
(or `~/.local/share/cost-router/memory.sqlite3`) and installs the skill at
`$HOME/.agents/skills/cost-router`. It prints the exact writable root to add to
`~/.codex/config.toml`; add it and restart Codex so every project can write to
the shared ledger without repeated approval prompts.

### Codex setup

```bash
codex login
codex login status
```

### Claude CLI setup

```bash
npm install -g @anthropic-ai/claude-code
claude auth login
claude auth status
```

### Personal Codex skill

```bash
cost-router setup
```

This is a user-level registration, so the skill is available from every Codex
session and project. Existing installations are kept; run `cost-router setup
--force` to update the installed copy.

### Use in Codex

Restart Codex, verify the skill appears in `/skills`, then use it directly in a Codex chat:

```text
$cost-router Investigate this long coding task, delegate suitable exploratory work, then implement and verify the result.
```

Codex may also select the skill implicitly for decomposable, context-heavy coding work. Explicit invocation is preferable while the workflow is being tested.

### External worker policy

C4Harness separates user authorization from host enforcement:

| Policy | Behavior |
|---|---|
| `never` | Never execute an external worker |
| `ask` | Permit public/synthetic data; private data requires explicit authorization |
| `allow` | Record that the user explicitly authorized this bounded external transfer |

Repository inputs default to `private`. When a user explicitly asks Codex to use
Claude on named repository files, the Skill passes `--external-policy allow
--data-classification private`. This avoids treating an explicit request as
missing consent.

Before a blocked or potentially sensitive external delegation is retried, the
installed Skill requires Codex to summarize the task-specific risks for the
user. The summary should identify, as applicable:

- which source files, logs, context packs, or generated artifacts may leave the
  local environment;
- which external provider and model will receive them;
- whether the worker receives read, shell, network, or staged-write access;
- possible exposure of secrets, personal data, proprietary code, or unrelated
  repository content;
- the write allowlist, expected outputs, Inbox behavior, and the practical
  impact of a compromised or incorrect worker.

Codex should then wait for explicit confirmation. After confirmation, it may
retry the same bounded operation once with `allow/private`, using only the
approved paths and permissions. It must not silently broaden the transfer,
change providers, or route around a second rejection.

> [!WARNING]
> **Codex may still refuse the operation after the user consents.** `allow`
> records the user's authorization inside C4Harness; it does not override the
> Codex sandbox, command approval, organization policy, secret detection, or
> data-egress controls. A host-policy rejection should be reported as such and
> must not be counted as a worker capability failure.

> [!CAUTION]
> **Full Access is an optional, high-risk troubleshooting choice.** If the user
> understands the consequences, they may try running Codex with Full Access to
> reduce filesystem, network, or command-approval friction. This gives Codex and
> invoked tools substantially broader access to the machine and repository, so
> use it only in a trusted workspace, review the exact transfer scope, exclude
> credentials and unrelated files, and prefer a disposable environment. Full
> Access still may not bypass independent organization or data-egress policy.

### Preview decomposition

`decompose` builds a task situation, root contract, fast/graph decision,
capability-aware worker assignments, verifier plans, and security-risk manifests.
It is preview-only: no worker or task graph is executed.

```bash
cost-router decompose \
  --goal "review and document the parser" \
  --requirement "inspect parser behavior" \
  --requirement "produce evidence-backed documentation" \
  --constraint "do not edit source files" \
  --acceptance "all required behavior is linked to file evidence" \
  --active-skill review \
  --skill-step inspect \
  --skill-step document \
  --plan-mode \
  --json
```

Plans and node outcomes use the separate decomposition-history repository; they
are not mixed into the per-task shared context/artifact memory graph. Worker
capabilities are loaded from `~/.config/cost-router/workers.json` (or
`COST_ROUTER_WORKERS`). The same manifest can be edited on the Dashboard's
**Worker Configuration** page.

Each Worker keeps the actual upstream model separate from the CLI alias used by
its harness. For example, a Claude Code configuration may declare
`model=mimo-v2.5-pro` and `model_alias=opus`; C4Harness passes `opus` to
`claude --model`, allowing Claude Code's `ANTHROPIC_DEFAULT_OPUS_MODEL` mapping
to select the custom model. Execute a configured entry with:

```bash
cost-router run --worker-id claude-mimo-pro --goal "review this module" --path src/ --json
```

The Worker editor presents hard capabilities as checkboxes, switches, selects,
and context limits, while soft capabilities use 0–1 sliders. Backend/adapter is
derived from the selected Harness instead of being a duplicate user setting.

### Open the dashboard

```bash
cost-router dashboard
```

The local console opens at `http://127.0.0.1:8765`. It summarizes calls and
delegated tokens across Codex sessions and repositories, and includes a
filterable call log. Use `--no-open` to start without opening a browser or
`--port PORT` to select another port.

For a remote development server, prefer IDE/SSH port forwarding. To expose the
console on the server network explicitly, use `cost-router dashboard --host
0.0.0.0`; the dashboard has no authentication, so do not expose it to an
untrusted network.

## CLI Reference

The Python CLI is for development, testing, and debugging. In normal use, invoke the skill inside Codex as shown in Quick Start above.

### Dry Run

Generate the route decision without invoking any backend:

```bash
python3 -m cost_router run \
  --env-file /path/to/provider.env \
  --goal "analyze synthetic SkillOpt failure log" \
  --path experiments/sample-skillopt-run.log \
  --json
```

The env file should define:

```bash
QWEN_CHAT_BASE_URL=...
QWEN_CHAT_MODEL=...
QWEN_CHAT_API_KEY=...
```

Claude CLI dry-run:

```bash
python3 -m cost_router run \
  --backend claude-cli \
  --claude-model sonnet \
  --goal "analyze synthetic SkillOpt failure log" \
  --path experiments/sample-skillopt-run.log \
  --json
```

With a context pack:

```bash
python3 -m cost_router run \
  --backend claude-cli \
  --claude-model sonnet \
  --external-policy allow \
  --data-classification private \
  --goal "review the implementation against the memory design" \
  --context-pack docs/memory.md \
  --path cost_router/memory.py \
  --execute
```

### Execute

```bash
python3 -m cost_router run \
  --env-file /path/to/provider.env \
  --goal "analyze synthetic SkillOpt failure log" \
  --path experiments/sample-skillopt-run.log \
  --execute
```

Claude CLI execution uses `claude -p --output-format json` by default:

```bash
python3 -m cost_router run \
  --backend claude-cli \
  --claude-command claude \
  --data-classification synthetic \
  --goal "analyze synthetic SkillOpt failure log" \
  --path experiments/sample-skillopt-run.log \
  --execute
```

### Asynchronous Tasks

`async-task` is one optional runtime pattern for long-running workloads; it is
not required for ordinary delegation and is not training-specific. It can own a
workload, periodically send bounded log snapshots to the same resumable Claude
session when those logs change, and persist significant or terminal events in a
durable Codex Inbox.

```bash
cost-router async-task start \
  --external-policy allow \
  --data-classification private \
  --goal "Monitor this long job and return actionable failures or completion" \
  --command "bash scripts/run_job.sh --config configs/job.yaml" \
  --log-path outputs/progress.log \
  --interval 60
```

Inbox delivery is intentionally local and durable. Normal completion,
failure, cancellation, timeout, and requests for input are queued locally and
can be inspected in the Dashboard or acknowledged without starting another Codex model turn.
The Python runtime compares file size and modification time first; unchanged
logs do not call Claude, and repeated idle checks use bounded exponential
backoff.

```bash
cost-router async-task status async_123456789abc
cost-router async-task events async_123456789abc
cost-router async-task inbox --unread-only
cost-router async-task ack 42
cost-router async-task stop async_123456789abc
```

Codex currently exposes no public interface that lets an external worker wake
the currently visible IDE conversation and confirm delivery. C4Harness therefore
does not start a second `codex exec resume` process. Results remain unread in the
Inbox until the user asks Codex to inspect them or marks them handled in the
Dashboard.

The deterministic Python runtime process handles scheduling and decides process
exit, marker files, timeout, and cancellation. It does not use model tokens.
Claude analyzes snapshots but cannot override those facts.

### Bounded Patch Proposal

Use patch mode when a worker may edit a small, explicit file set:

```bash
cost-router run \
  --backend claude-cli \
  --external-policy allow \
  --data-classification private \
  --mode patch \
  --parent-task-label "Router validation improvements" \
  --goal "add validation for empty task goals" \
  --repo . \
  --path cost_router/schemas.py \
  --write-path cost_router/router.py \
  --write-path tests/test_core.py \
  --execute \
  --json
```

`--path` inputs are read-only. `--write-path` entries form the complete write allowlist. The worker receives `Edit/Write` tools only inside that run. Cost Router compares the workspace with its baseline, rejects out-of-scope changes, and emits `proposed.patch`; it never applies the patch automatically.

### Inspect Memory

Route decisions, subtask results, verification status, and verified facts are stored in the personal SQLite ledger:

```bash
python3 -m cost_router memory --json
```

All commands use the global ledger by default. Set `COST_ROUTER_MEMORY` or use
`--memory /path/to/memory.sqlite3` to inspect a specific ledger, including a
legacy project ledger such as `.cost-router/memory.sqlite3`.

## Token Ledger

The token ledger is not a dollar-cost calculator. It tracks:

| Field | Description |
|---|---|
| `actual_worker_tokens` | token usage reported by the worker CLI when available |
| `delegated_context_tokens_estimate` | approximate tokens in the task goal and paths sent to the worker |
| `returned_result_tokens_estimate` | approximate tokens the main agent receives back |
| `estimated_main_tokens_saved` | delegated context minus returned result |

The dashboard reports actual-token coverage separately. A worker call that
does not report usage is shown as **Not reported**, never as zero. Each call
also records `CODEX_THREAD_ID` when available and the Skill supplies a shared
`parent_task_label` for calls derived from the same user task.

Estimates use file byte size / 4 as a rough token proxy. Very small tasks may report `estimated_main_tokens_saved=0` when the worker summary is longer than the delegated input.

> **Privacy:** Do not send private source code, credentials, or logs to an external provider unless that data transfer is approved.

## Roadmap

**Router and orchestration**

- [x] Preview and persist an explainable task-contract graph without executing it.
- [ ] Add dependency-aware parallel and sequential worker scheduling.
- [ ] Route by task difficulty, risk, context size, model capability, and policy.
- [ ] Add retry budgets, fallback chains, and Inbox retention/attention policies.

**Shared memory and files**

- [ ] Complete worker context refresh for long-running tasks.
- [ ] Enforce concurrent file leases and conflict-aware patch merging.
- [ ] Add compact task summaries with drill-down context and artifacts.
- [ ] Evaluate retrieval and memory policies against long-horizon coding tasks.

**Verification and safety**

- [ ] Add pluggable test, lint, type-check, and patch-applicability verifiers.
- [ ] Introduce confidence scoring and verifier-driven rework loops.
- [ ] Add authenticated remote dashboard access and privacy controls.

**Harness ecosystem**

- [ ] Detect installed harnesses, configured model aliases, effective tools, modalities, context limits, and network policy; propose Worker profiles for user approval.
- [ ] Separate declared model capabilities from capabilities actually delivered by the harness and C4 policy, then verify them with safe probes.
- [ ] Implement the OpenCode adapter and cross-harness context contract.
- [ ] Add writable Codex subagents with the same bounded-patch policy.
- [ ] Define an adapter SDK for Aider, Roo, custom CLIs, and MCP delegators.
- [ ] Package the project as a versioned Codex plugin for easier distribution.
