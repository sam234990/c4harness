# C4Harness Code Structure

**Status**: target architecture draft  
**Date**: 2026-07-03  
**Scope**: C4Harness 的模块边界、目录布局、依赖规则与后续重构顺序

## 1. 设计目标

C4 的代码结构应直接反映项目的四个核心方法模块：

1. **Decompose**：理解完整任务，生成可验证任务契约图，并进行能力约束下的 worker 分配。
2. **Memory**：保存 Private Orchestrator State、Worker Task、Context Pack、File/Artifact、事件和执行历史。
3. **Verifier**：在节点创建时定义验证契约，并对 worker 结果、patch、策略和 Root Contract 进行独立验收。
4. **Delegator**：连接 Codex、Claude CLI、OpenCode 等 harness，执行单节点或异步任务，并返回统一结果。

这四个模块不能直接堆在 CLI 中，也不应互相随意调用。项目还需要：

- `core`：稳定的数据契约、枚举、协议和错误类型。
- `application`：组合四个模块，承载九步主流程和 graph execution。
- `cli`：命令行解析及命令适配，不承载业务规则。
- `usage`：Token、延迟、路由事件和能力画像统计。
- `dashboard`：本地只读 API 与网页控制台。
- `integrations`：Codex Skill、MCP 和未来其他宿主接入。

总体原则是：**领域模块表达方法，application 负责组合，CLI 和网页只是入口，backend 只是适配器。**

## 2. Directory Layout

```text
c4harness/
├── pyproject.toml                         # package metadata and CLI entry point
├── README.md                              # English quick start and project overview
├── README_zh.md                           # Chinese quick start and project overview
├── cost_router/                           # Python package; public name may later migrate to c4harness
│   ├── __init__.py
│   ├── __main__.py                        # python -m cost_router entry
│   │
│   ├── core/                              # stable contracts shared across modules
│   │   ├── __init__.py
│   │   ├── contracts.py                   # Task, TaskNodeContract, RootContract, WorkerResult
│   │   ├── graph.py                       # TaskContractGraph, GraphEdge, graph states
│   │   ├── capabilities.py                # capability types, WorkerArm and policy types
│   │   ├── events.py                      # lifecycle and audit event contracts
│   │   ├── enums.py                       # modes, node kinds, statuses, risks
│   │   ├── protocols.py                   # narrow interfaces between core modules
│   │   └── errors.py                      # typed domain/application errors
│   │
│   ├── decompose/                         # task understanding and contract planning
│   │   ├── __init__.py
│   │   ├── situation.py                   # TaskSituation and minimal grounding builder
│   │   ├── requirements.py                # Requirement Ledger and Root Contract builder
│   │   ├── planner.py                     # fast path / graph path planning
│   │   ├── operators.py                   # deliverable/workflow/evidence/capability splits
│   │   ├── atomicity.py                   # split triggers and stop conditions
│   │   ├── capabilities.py                # hard filtering and soft capability scoring
│   │   ├── assignment.py                  # explainable WorkerArm assignment
│   │   ├── replan.py                      # bounded graph revision decisions
│   │   └── service.py                     # decompose module facade
│   │
│   ├── memory/                            # shared memory graph and durable ledger
│   │   ├── __init__.py
│   │   ├── store.py                       # MemoryStore public facade
│   │   ├── schema.py                      # SQLite schema declarations
│   │   ├── migrations.py                  # backward-compatible schema migrations
│   │   ├── task_graph.py                  # persist/load contracts, nodes and edges
│   │   ├── context.py                     # Context Pack metadata and visibility rules
│   │   ├── artifacts.py                   # file, patch, output and provenance records
│   │   ├── events.py                      # worker/replan/verifier event persistence
│   │   ├── locks.py                       # bounded file-lock and write ownership policy
│   │   └── queries.py                     # reusable read queries for CLI/dashboard
│   │
│   ├── verifier/                          # verifier-by-construction and root acceptance
│   │   ├── __init__.py
│   │   ├── contracts.py                   # VerifierContract and verification outcomes
│   │   ├── structural.py                  # output/schema/artifact checks
│   │   ├── policy.py                      # path, permission, sandbox and secret checks
│   │   ├── grounding.py                   # evidence-to-source consistency checks
│   │   ├── executable.py                  # patch apply, syntax, lint, test and build checks
│   │   ├── semantic.py                    # optional model-assisted semantic review
│   │   ├── integration.py                 # cross-node consistency and patch conflicts
│   │   ├── root.py                        # Requirement Ledger and Root Contract verifier
│   │   ├── attribution.py                 # failure attribution classification
│   │   └── service.py                     # verifier module facade
│   │
│   ├── delegator/                         # worker execution and harness adaptation
│   │   ├── __init__.py
│   │   ├── runtime.py                     # one-node delegate/execute/result lifecycle
│   │   ├── scheduler.py                   # ready-frontier and bounded graph scheduling
│   │   ├── workspace.py                   # staged copy/worktree preparation
│   │   ├── sessions.py                    # persistent harness sessions
│   │   ├── async_runtime.py               # long-running workload monitoring
│   │   ├── callbacks.py                   # Codex resume and terminal event delivery
│   │   └── backends/
│   │       ├── __init__.py
│   │       ├── base.py                    # backend protocol and PreparedWorker
│   │       ├── codex_subagent.py          # Responses-compatible Codex worker
│   │       ├── claude_cli.py              # Claude CLI adapter
│   │       ├── opencode_cli.py             # future OpenCode adapter
│   │       └── registry.py                # enabled backend/harness registry
│   │
│   ├── application/                       # composes the four core modules
│   │   ├── __init__.py
│   │   ├── prepare_task.py                # grounding + root contract + decomposition
│   │   ├── run_node.py                    # assignment + delegation + local verification
│   │   ├── run_graph.py                   # nine-step task orchestration loop
│   │   ├── replan_task.py                 # failure handling and graph revision
│   │   ├── verify_root.py                 # merge and final acceptance use case
│   │   └── inspect_task.py                # status/detail read model
│   │
│   ├── hooks/                             # built-in lifecycle event mechanism
│   │   ├── __init__.py
│   │   ├── events.py                      # pre/post ground, route, delegate, verify
│   │   ├── dispatcher.py                  # deterministic hook dispatch
│   │   └── policies.py                    # built-in safety and visibility policies
│   │
│   ├── usage/                             # observability and online capability evidence
│   │   ├── __init__.py
│   │   ├── tokens.py                      # actual and estimated Token extraction
│   │   ├── recorder.py                    # route/execution/verification usage events
│   │   ├── aggregation.py                 # daily/monthly/backend summaries
│   │   ├── profiles.py                    # per WorkerArm capability statistics
│   │   ├── confidence.py                  # decomposition/routing/result confidence
│   │   └── feedback.py                    # user override and explicit feedback records
│   │
│   ├── cli/                               # thin command-line interface
│   │   ├── __init__.py
│   │   ├── main.py                        # parser construction and command dispatch
│   │   ├── common.py                      # shared CLI argument/path/output helpers
│   │   └── commands/
│   │       ├── run.py                     # one task or graph execution command
│   │       ├── decompose.py               # inspect generated TaskSituation/contract graph
│   │       ├── memory.py                  # ledger and memory inspection
│   │       ├── async_task.py              # async start/status/events/stop commands
│   │       ├── dashboard.py               # local dashboard launcher
│   │       └── setup.py                   # global storage and user Skill setup
│   │
│   ├── dashboard/                         # local console server and read models
│   │   ├── __init__.py
│   │   ├── server.py                      # standard-library HTTP server
│   │   ├── api.py                         # overview/timeseries/calls/detail endpoints
│   │   ├── queries.py                     # dashboard-specific projections
│   │   └── web/
│   │       ├── index.html
│   │       ├── styles.css
│   │       └── app.js
│   │
│   ├── config/                            # configuration and path resolution
│   │   ├── __init__.py
│   │   ├── settings.py                    # application settings
│   │   ├── providers.py                   # provider configuration and validation
│   │   ├── workers.py                     # WorkerArm manifests and user preferences
│   │   └── paths.py                       # global data/Skill/runtime paths
│   │
│   ├── integrations/                      # user-facing host integrations
│   │   ├── __init__.py
│   │   ├── codex/
│   │   │   ├── setup.py                   # Codex-specific setup hints
│   │   │   └── callbacks.py               # thread resume integration
│   │   └── mcp/                           # future MCP server surface
│   │       ├── __init__.py
│   │       ├── server.py
│   │       └── tools.py
│   │
│   └── bundled_skill/                     # canonical user-level Codex Skill source
│       ├── __init__.py
│       ├── SKILL.md
│       └── agents/
│           └── openai.yaml
│
├── tests/                                 # tracked deterministic unit/integration tests
│   ├── unit/
│   │   ├── decompose/
│   │   ├── memory/
│   │   ├── verifier/
│   │   ├── delegator/
│   │   └── usage/
│   ├── integration/
│   │   ├── test_cli_run.py
│   │   ├── test_contract_graph.py
│   │   ├── test_claude_staging.py
│   │   └── test_dashboard_api.py
│   └── fixtures/                          # small, secret-free deterministic fixtures
│
├── docs/                                  # method and architecture documents
│   ├── code-structure.md                  # this document
│   ├── decompose.md                       # task decomposition method
│   ├── memory.md                          # shared memory method
│   ├── verifier.md                        # future verifier method
│   ├── delegator.md                       # future delegation method
│   ├── implementation.md                  # implementation history/blueprint
│   └── background/                        # explored papers and prior systems
│
├── scripts/                               # reproducible setup/demo/release helpers
│   ├── install-user-skill.sh
│   ├── run-dashboard.sh
│   └── smoke-test.sh
│
├── examples/                              # small end-to-end public examples
│   ├── log-analysis/
│   ├── bounded-patch/
│   └── async-monitor/
│
├── test/                                  # ignored local scratch scripts/notebooks
├── outputs/                               # ignored generated research outputs
└── .cost-router/                          # ignored per-project runtime staging artifacts
```

## 3. 模块职责

### 3.1 Core

`core` 只保存稳定、无副作用的跨模块契约：

- TaskSituation、Requirement、RootContract 和 TaskNodeContract。
- TaskContractGraph、GraphEdge 和状态枚举。
- WorkerArm、capability requirements 和统一 WorkerResult。
- Backend、Memory、Verifier 等窄协议。

`core` 不读取环境变量、不访问 SQLite、不运行 subprocess，也不依赖任何具体 backend。

### 3.2 Decompose

输入：用户任务、Skill/模式信息、必要仓库事实、worker registry 和用户策略。  
输出：经过验证的 `DecompositionPlan`。

它负责：

- 构建 TaskSituation 和 Requirement Ledger。
- 定义 Root Contract。
- 判断 fast path 或 graph path。
- 生成有 verifier contract 的节点。
- 进行 hard capability filter 和 explainable assignment。
- 在失败后提出 bounded graph revision。

它不执行 worker、不写 patch，也不直接操作 SQLite。

### 3.3 Memory

输入：core contracts 和 lifecycle events。  
输出：持久化结果、Context Pack、artifact provenance 和只读查询。

它负责：

- 管理全局 SQLite schema 与 migration。
- 保存 root/task/context/artifact 节点和依赖边。
- 实现 worker 可见与 orchestrator 私有边界。
- 管理基础文件锁、版本和事件历史。
- 为 Dashboard 和 application 提供稳定查询接口。

它不决定任务如何拆解，也不判断 worker 结果是否正确。

### 3.4 Verifier

输入：TaskNodeContract、WorkerResult、artifact 和真实环境证据。  
输出：VerificationResult、Result Confidence 和 Failure Attribution。

它负责结构、策略、grounding、可执行、语义、集成与 root-level verification。Verifier 不应调用具体 backend 执行任务；需要模型复核时，通过抽象 `SemanticReviewer` 接口请求 delegator/application 提供能力。

### 3.5 Delegator

输入：已分配 worker 的 TaskNodeContract 和受限 Context Pack。  
输出：统一 WorkerResult、artifact 和运行事件。

它负责：

- backend/harness 协议适配。
- staging workspace、命令准备和进程生命周期。
- 同步节点执行、持久 session 和异步 workload 监控。
- Codex callback 等结果交付机制。

它不负责拆解、能力学习或最终验收。Backend 不应直接写 MemoryStore；事件由 application 统一提交。

### 3.6 Application

`application` 是唯一可以按流程组合四大模块的层：

```text
Decompose
  -> Memory.save_plan
  -> Delegator.execute_ready_node
  -> Verifier.verify_node
  -> Memory.commit_result
  -> Decompose.replan_if_needed
  -> Verifier.verify_root
```

这避免 `decompose`、`memory`、`verifier` 和 `delegator` 互相循环依赖，也让 CLI、Skill 和 MCP 复用同一组 use cases。

## 4. 依赖规则

建议依赖方向如下：

```text
CLI / Dashboard / Skill / MCP
              ↓
         Application
       ↙      ↓      ↘
Decompose   Verifier   Delegator
       ↘      ↓      ↙
         Core Contracts
              ↑
            Memory
```

更精确的规则：

1. 所有模块可以依赖 `core`。
2. `core` 不依赖项目内其他模块。
3. `decompose` 不导入具体 backend、SQLite 或 Dashboard。
4. `delegator.backends` 不导入 planner、MemoryStore 或网页代码。
5. `verifier` 不直接选择 worker；语义复核通过协议交给 application。
6. `memory` 只持久化 core contract/event，不承载路由与验证规则。
7. `usage` 订阅结构化事件，不侵入 worker/backend 实现。
8. `cli` 只做参数解析、调用 use case 和格式化输出。
9. `dashboard` 只读取查询模型，不直接修改任务图或能力画像原始结果。
10. 跨模块调用优先使用 protocol/facade，避免导入内部实现文件。

## 5. CLI 与 Backend 的区别

这里需要区分三类概念：

- **C4 CLI**：用户运行的 `cost-router run/decompose/dashboard/...`，位于 `cli/`。
- **Harness backend**：C4 用来执行 worker 的 Codex、Claude CLI、OpenCode，位于 `delegator/backends/`。
- **Model provider**：backend 进一步连接的 OpenAI Responses、Anthropic 或兼容 API，由 `config/providers.py` 描述。

这样可以表达同一模型在不同 harness 中具有不同工具和 memory 行为，也可以表达 Claude CLI 使用 Anthropic-native 协议，而 Qwen worker 使用 Responses-compatible provider。

## 6. Usage 与 Dashboard

Usage 不应继续同时承担 Token 估算、SQLite 查询和网页统计。建议分为：

- `usage/tokens.py`：从 backend 输出提取真实 Token，并估算 delegated/returned/main-saved Token。
- `usage/recorder.py`：把 route、execution、verification、callback 记录成统一 usage event。
- `usage/aggregation.py`：按日、月、backend、model、project 和 task 聚合。
- `usage/profiles.py`：从 verified outcome 形成 WorkerArm 能力统计。
- `dashboard/queries.py`：把 memory/usage 结果投影成网页需要的数据结构。

Dashboard 只展示和筛选，不直接修改历史 outcome。用户偏好和 feedback 通过明确 command/use case 写入，不能覆盖原始执行记录。

## 7. 文件迁移记录

以下迁移已在第一轮重构中完成：

| 原文件 | 迁入位置 | 状态 |
|---|---|---|
| `schemas.py` | `core/contracts.py`、`core/enums.py`、`core/capabilities.py` | ✅ 完成 |
| `decomposition/` | `decompose/` | ✅ 完成，别名已删除 |
| `memory.py` | `memory/store.py` | ✅ 完成 |
| `verifier.py` | `verifier/` 目录 | ✅ 完成 |
| `runtime.py` | `delegator/runtime.py` | ✅ 完成 |
| `backends/` | `delegator/backends/` | ✅ 完成 |
| `async_tasks.py` | `delegator/async_runtime.py` | ✅ 完成 |
| `hooks.py` | `hooks/__init__.py` | ✅ 完成 |
| `usage.py` | `usage/tokens.py` | ✅ 完成 |
| `analytics.py` | `usage/aggregation.py` | ✅ 完成 |
| `dashboard.py` | `dashboard/server.py` | ✅ 完成 |
| `config.py` | `config/providers.py` | ✅ 完成 |
| `paths.py` | `config/paths.py` | ✅ 完成 |
| `cli.py` | `cli/main.py` | ✅ 完成 |

**尚未迁移**：
- `router.py` → 计划迁入 `application/` 或 `cli/`
- `setup_user.py` → 计划迁入 `cli/commands/setup.py`

## 8. 建议重构顺序

### Phase 1: 稳定 Core Contracts

- 创建 `core/`，迁移无副作用的 dataclass、enum 和 protocol。
- 保留旧 import re-export，避免一次性破坏现有代码和用户接口。
- 固定 TaskSituation、TaskNodeContract、WorkerArm 和 WorkerResult 的序列化格式。

### Phase 2: 分离四大模块

- 将现有 decomposition 包按 situation/planner/assignment 分开。
- 把 `memory.py` 拆成 schema、migration、store 和 query。
- 把单体 verifier 拆成 structural、policy、grounding 和 root verifier。
- 把 runtime、backend staging 和 async runtime 移入 delegator。

### Phase 3: 建立 Application Use Cases

- 用 `prepare_task` 和 `run_node` 替换 CLI 内的业务流程。
- 实现最小顺序 `run_graph`，再考虑有限并行。
- 让 Memory、Verifier 和 Delegator 只通过 core contracts/event 交互。

### Phase 4: 拆分入口与观测

- 将 `cli.py` 拆成独立 commands。
- 将 usage extraction、aggregation 和 capability profile 分开。
- 将 Dashboard server、API query 和静态网页分开。

### Phase 5: Integration 与兼容清理

- 保持 user-level bundled Skill 为唯一 Skill 源。
- 增加 MCP 接入时复用 application use cases，而不是复制 CLI 行为。
- 在兼容周期结束后删除旧模块 re-export 和过渡适配器。

## 9. 测试布局原则

- `tests/` 应当被 Git 追踪，用于确定性单元测试和集成测试。
- `test/` 可作为本地 scratch 目录并保持忽略，避免和正式测试混淆。
- 每个核心模块至少具有 contract、失败边界和持久化兼容测试。
- backend 测试默认使用 fake process/output，不要求真实 API key。
- 真实 Claude/Codex/OpenCode smoke test 单独标记，只有显式启用时运行。
- SQLite migration 必须使用旧 schema fixture 测试，不能只测试新建数据库。

当前仓库的 `.gitignore` 忽略了整个 `tests/` 与 `docs/`，这不适合作为最终开源结构。后续正式执行模块化重构时，应决定哪些方法文档公开，并至少让确定性测试进入版本控制。

## 10. 本轮边界

本文最初只定义目标架构。2026-07-03 已完成第一轮渐进迁移：

- 建立 `core/`，接管稳定 Task/Result 与 task graph contracts。
- 将 task planning 迁入 `decompose/`。
- 将 SQLite store 迁入 `memory/`。
- 将 verifier 拆为 structural、policy、grounding、contracts 与 service。
- 将单节点 runtime、backend adapters 和 async runtime 迁入 `delegator/`。
- 将 CLI 入口迁入 `cli/`，将 Token 与 aggregation 迁入 `usage/`。
- 将 config、paths、hooks、dashboard 迁入对应目录。
- 删除所有兼容别名文件（`schemas.py`、`runtime.py`、`analytics.py`、`async_tasks.py`、`decomposition/` 等）。
- backend 失败和 runtime exception 现在都能写入 ledger，供 Dashboard 展示。

**当前顶层结构**（仅 4 个文件）：
```
cost_router/
├── __init__.py
├── __main__.py
├── router.py
└── setup_user.py
```

尚未完成的结构包括 `application/` use cases、CLI commands 细分、Memory schema/migration/query 细分、Root Verifier 与 graph scheduler。后续继续渐进式迁移，每完成一个阶段运行完整测试，避免”大爆炸式”目录重写。
