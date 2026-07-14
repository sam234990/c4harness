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

A cost-aware multi-agent coding orchestration system for decomposing bounded work from a main Codex session, delegating it to specialized harnesses, verifying the results, and learning from execution history.

> [!IMPORTANT]
> **C4Harness is experimental.** Claude CLI delegation, read-only Codex
> subagents, bounded patch proposals, shared-memory persistence, and the local
> dashboard work today. Generic asynchronous workloads can also be monitored by
> a resumable Claude session; significant and terminal events are stored in the
> durable C4 Inbox and surfaced by the Dashboard. Explainable decomposition and
> public `graph-run` CLI now executes compiled plans with dependency-aware,
> bounded parallelism, structured verification failures, and at most two
> attempts per node. Automatic capability learning and broader harness support
> remain roadmap items.

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
| Graph runtime | **Prototype** | Public `graph-run`, dependency scheduling, bounded parallel batches, node verification, History outcomes, and root verification |
| Graph-scoped integration workspace | **Prototype** | Git-independent snapshot, transactional patch apply/verify/commit, shared canonical workspace per task graph |
| Structured verifier phases | **Prototype** | Proposal-phase and post-integration-phase checks with structured failure classification |
| Retry and fallback execution | **Prototype** | At most two total attempts; retryable failures use the same worker or next eligible fallback; env/policy/conflict failures do not retry |
| Graph-run CLI | **Working** | Compiles a version-1 proposal and executes its assigned graph; dry-run is the default |
| Bounded parallel execution | **Prototype** | Independent ready nodes run concurrently; overlapping write sets serialize; integration stays isolated from the source repo |
| Capability-based graph routing | **Prototype** | Compiled assignments and eligible fallback workers drive graph execution; single-task `run` remains explicit |
| OpenCode / other harnesses | **Planned** | Dashboard schema is ready; runtime adapter is not |

## Target Architecture

C4Harness is organized around four core modules: **Decompose**, **Delegator**, **Verifier**, and **Memory**. A Codex main session remains the private orchestrator. C4Harness turns the main session's structured plan into bounded worker assignments, dispatches work to supported harnesses, validates the returned evidence, and records reusable history for future routing.

![C4Harness overall flow](assets/c4harness-overall-flow.png)

The overall workflow is:

1. **Decompose** converts a grounded user request into a contract-aware plan, including task nodes, worker requirements, verifier plans, and assignment decisions.
2. **Delegator** sends each assigned task to the selected harness with only the approved context, file visibility, and write scope.
3. **Verifier** checks worker results against deterministic templates, artifacts, path constraints, and root-level acceptance requirements.
4. **Memory** maintains runtime collaboration state and cross-task capability evidence without exposing unrelated history to workers.

Workers propose patches, facts, and summaries. The verifier commits only validated evidence. Codex integrates the accepted result and makes the final user-facing decision.

**Harness direction:**

| Harness | Role | Status |
|---|---|---|
| Claude Worker | analysis / patch / review | Working |
| Codex Subagent | read-only delegated work | Working |
| OpenCode Worker | search / summarize / alternate harness | Planned |
| Other (Aider, Roo, Custom) | adapter-based extension | Research |

### C4-ACD planning pipeline

C4-ACD is the planning stage that turns a Codex semantic proposal into an executable, verifiable, and assignable contract graph. Codex uses the full conversation, skill workflow, repository context, and user constraints to emit a structured `CodexTaskProposal`. C4Harness then validates and compiles that proposal instead of calling another planning model to reinterpret the raw prompt.

![C4-ACD planning pipeline](assets/c4-acd-contract-planning.png)

The pipeline has three tightly connected responsibilities:

- **Decomposition and contract preparation** validates the proposal, checks requirement coverage, prepares the root contract, and normalizes the plan into either a single-node path or a task graph.
- **Contract graph and worker assignment** compiles `TaskNodeContract`s, filters workers by hard capabilities, scores soft capabilities with user preferences and history evidence, and chooses primary and fallback workers.
- **Verifier plan design** prepares per-node verifier plans, template checks, evidence requirements, and compile-time constraints so verification is designed before execution starts.

The output is a `DecompositionPlan` containing the `RootContract`, `TaskContractGraph`, `WorkerAssignmentPlan`, `VerifierPlan`s, `SecurityRiskManifest`, and `PlanValidationReport`. Decompose is preview-only: it does not execute workers, run verifiers, or write the runtime shared-memory graph.

### Memory design

C4Harness separates runtime collaboration memory from historical capability evidence. **Shared Task Memory** is the current task's context-artifact graph: it controls what each worker can read, which context packs it receives, and what patches or outputs it may propose. **Execution History** is a cross-task evidence store: it records plan snapshots, verified outcomes, failure attribution, token and latency usage, and derived capability profiles.

![Shared Task Memory with bounded worker access](assets/shared-task-memory-bounded-access.png)

This separation keeps the access boundary clear:

- Workers read only approved task nodes, context packs, and file/artifact references.
- Workers do not directly edit shared facts or real repository files; they propose outputs or patch artifacts.
- Verifier and Codex decide which worker outputs become committed evidence.
- History is not worker-visible by default; Decompose reads only controlled capability summaries for future assignment.

Core invariant: **Workers propose → Verifier commits → Codex integrates.**

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

## Quick Start

### Prerequisites

- Python 3.11+
- At least one implemented worker backend configured (Codex subagent or Claude CLI)

### Install

```bash
git clone https://github.com/sam234990/c4harness.git
cd c4harness
python3 -m pip install -e .
c4harness setup
```

`setup` creates the personal ledger at `$XDG_DATA_HOME/c4harness/memory.sqlite3`
(or `~/.local/share/c4harness/memory.sqlite3`) and installs the skill at
`$HOME/.agents/skills/c4harness`. It prints the exact writable root to add to
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
c4harness setup
```

This is a user-level registration, so the skill is available from every Codex
session and project. Existing installations are kept; run `c4harness setup
--force` to update the installed copy.

### Use in Codex

Restart Codex, verify the skill appears in `/skills`, then use it directly in a Codex chat:

```text
$c4harness Investigate this long coding task, delegate suitable exploratory work, then implement and verify the result.
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
c4harness decompose \
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
capabilities are loaded from `~/.config/c4harness/workers.json` (or
`C4HARNESS_WORKERS`). The same manifest can be edited on the Dashboard's
**Worker Configuration** page.

Each Worker keeps the actual upstream model separate from the CLI alias used by
its harness. For example, a Claude Code configuration may declare
`model=mimo-v2.5-pro` and `model_alias=opus`; C4Harness passes `opus` to
`claude --model`, allowing Claude Code's `ANTHROPIC_DEFAULT_OPUS_MODEL` mapping
to select the custom model. Execute a configured entry with:

```bash
c4harness run --worker-id claude-mimo-pro --goal "review this module" --path src/ --json
```

The Worker editor presents hard capabilities as checkboxes, switches, selects,
and context limits, while soft capabilities use 0–1 sliders. Backend/adapter is
derived from the selected Harness instead of being a duplicate user setting.

### Execute a task graph

`graph-run` compiles the same version-1 proposal as `decompose`, then executes
the assigned nodes. It defaults to a safe preview and does not invoke a worker
unless `--execute` is present.

```bash
# Preview dependency order, assignments, and graph shape.
c4harness graph-run \
  --plan-file .c4harness/proposals/task.json \
  --repo "$PWD" \
  --max-parallel 2 \
  --json

# Execute after reviewing risk manifests and external-transfer consent.
c4harness graph-run \
  --plan-file .c4harness/proposals/task.json \
  --repo "$PWD" \
  --max-parallel 2 \
  --external-policy allow \
  --data-classification private \
  --execute \
  --json
```

`max-parallel=1` is the conservative default. Ready nodes may share a batch
only after dependencies succeed and only when declared write sets do not
overlap. Worker calls can overlap, while patch integration, post-integration
verification, and commit use short serialized transactions in the graph
workspace. The source repository is never modified automatically.

### Open the dashboard

```bash
c4harness dashboard
```

The local console opens at `http://127.0.0.1:8765`. It summarizes calls and
delegated tokens across Codex sessions and repositories, and includes a
filterable call log. Use `--no-open` to start without opening a browser or
`--port PORT` to select another port.

For a remote development server, prefer IDE/SSH port forwarding. To expose the
console on the server network explicitly, use `c4harness dashboard --host
0.0.0.0`; the dashboard has no authentication, so do not expose it to an
untrusted network.

## CLI Reference

The Python CLI is for development, testing, and debugging. In normal use, invoke the skill inside Codex as shown in Quick Start above.

### Dry Run

Generate the route decision without invoking any backend:

```bash
python3 -m c4harness run \
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
python3 -m c4harness run \
  --backend claude-cli \
  --claude-model sonnet \
  --goal "analyze synthetic SkillOpt failure log" \
  --path experiments/sample-skillopt-run.log \
  --json
```

With a context pack:

```bash
python3 -m c4harness run \
  --backend claude-cli \
  --claude-model sonnet \
  --external-policy allow \
  --data-classification private \
  --goal "review the implementation against the memory design" \
  --context-pack docs/memory.md \
  --path c4harness/memory.py \
  --execute
```

### Execute

```bash
python3 -m c4harness run \
  --env-file /path/to/provider.env \
  --goal "analyze synthetic SkillOpt failure log" \
  --path experiments/sample-skillopt-run.log \
  --execute
```

Claude CLI execution uses `claude -p --output-format json` by default:

```bash
python3 -m c4harness run \
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
c4harness async-task start \
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
c4harness async-task status async_123456789abc
c4harness async-task events async_123456789abc
c4harness async-task inbox --unread-only
c4harness async-task ack 42
c4harness async-task stop async_123456789abc
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
c4harness run \
  --backend claude-cli \
  --external-policy allow \
  --data-classification private \
  --mode patch \
  --parent-task-label "Router validation improvements" \
  --goal "add validation for empty task goals" \
  --repo . \
  --path c4harness/schemas.py \
  --write-path c4harness/router.py \
  --write-path tests/test_core.py \
  --execute \
  --json
```

`--path` inputs are read-only. `--write-path` entries form the complete write allowlist. The worker receives `Edit/Write` tools only inside that run. C4Harness compares the workspace with its baseline, rejects out-of-scope changes, and emits `proposed.patch`; it never applies the patch automatically.

### Inspect Memory

Route decisions, subtask results, verification status, and verified facts are stored in the personal SQLite ledger:

```bash
python3 -m c4harness memory --json
```

All commands use the global ledger by default. Set `C4HARNESS_MEMORY` or use
`--memory /path/to/memory.sqlite3` to inspect a specific ledger, including a
project-local ledger such as `.c4harness/memory.sqlite3`.

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
- [x] Execute a task-contract graph sequentially with dependency-aware blocking, node verification, History outcomes, and root verification.
- [x] Add a public proposal graph runner and bounded parallel execution for independent ready nodes.
- [ ] Connect capability, preference, History, context-size, risk, and policy scoring to automatic runtime Worker selection.
- [x] Connect structured verifier failures to a two-attempt retry budget, fallback chain, and bounded replanning decisions.
- [ ] Define Inbox retention and attention policies.

**Shared memory and files**

- [ ] Complete worker context refresh for long-running tasks.
- [ ] Enforce concurrent file leases and conflict-aware patch merging.
- [ ] Add compact task summaries with drill-down context and artifacts.
- [ ] Evaluate retrieval and memory policies against long-horizon coding tasks.

**Verification and safety**

- [x] Add deterministic contract-aware node verification and root-contract verification.
- [x] Add explainable assignment confidence from capability match, History evidence, verifier availability, and candidate margin.
- [ ] Add pluggable test, lint, type-check, and patch-applicability verifiers.
- [x] Add verifier-driven rework and escalation loops.

**Harness ecosystem**

- [ ] Detect installed harnesses, configured model aliases, effective tools, modalities, context limits, and network policy; propose Worker profiles for user approval.
- [ ] Separate declared model capabilities from capabilities actually delivered by the harness and C4 policy, then verify them with safe probes.
- [ ] Implement the OpenCode adapter and cross-harness context contract.
- [ ] Add writable Codex subagents with the same bounded-patch policy.
- [ ] Package the project as a versioned Codex plugin for easier distribution.
