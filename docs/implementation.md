# Implementation Blueprint

日期：2026-06-22

## Purpose

这个文件是后续写代码时的工程蓝图。`claude.md` 负责项目愿景和路线；本文件负责把愿景落到代码结构、模块边界、接口契约和可复用开源组件上。

项目目标暂定为：

> 构建一个 Codex-first、backend 可插拔的 coding-agent task router，用低成本 agent 承担可隔离子任务，用 verifier 和 shared memory 保持质量与上下文稳定。

## Non-Goals

为了避免第一版变成大而全框架，先明确不做什么：

- 不做通用 multi-agent framework。
- 不重写 Codex、Claude Code、OpenCode、Aider、Roo Code。
- 不做完整 IDE。
- 不做模型 API gateway 的底层转发能力，LiteLLM/RouteLLM 已经覆盖这一层。
- 不默认让低成本 agent 修改主工作区。
- 不把完整 transcript 当作 memory 长期塞回上下文。

## Initial Proof Scope

更详细的运行机制、memory 方法、hook 和 verifier 设计见 `methodology.md`。

第一版只验证一个闭环：

1. 用户给一个 coding task。
2. Router 判断它是否适合委托给低成本 worker。
3. Delegator 选择一个 backend 执行子任务。
4. Worker 返回结构化 summary、evidence、risk、next step。
5. Verifier 判断结果是否可接受。
6. Memory/Ledger 记录事实、成本和路由决策。
7. 主 agent 使用精简结果继续推进。

推荐场景：

- 日志失败分析。
- 测试失败初诊。
- 代码库只读搜索。
- PR diff 初步 review。

第一版不处理复杂自动改代码。可写任务放到后续 worktree/patch backend。

## Proposed Repository Layout

```text
.
├── claude.md                  # project vision and roadmap
├── claude-research.md         # research notes and feasibility checks
├── implementation.md          # this implementation blueprint
├── experiments/               # sanitized experiments and demos
├── c4harness/               # main package
│   ├── __init__.py
│   ├── cli.py                 # command line entrypoint
│   ├── config.py              # load env/config/backend definitions
│   ├── schemas.py             # shared typed contracts
│   ├── router.py              # task classification and routing
│   ├── delegator.py           # dispatch tasks to backends
│   ├── verifier.py            # validate worker outputs
│   ├── memory.py              # repo/task memory abstraction
│   ├── ledger.py              # cost and run ledger
│   ├── hooks.py               # pre/post task hook interface
│   └── backends/
│       ├── __init__.py
│       ├── codex_subagent.py  # Codex custom subagent backend
│       ├── external_cli.py    # generic CLI backend
│       ├── claude_cli.py      # Claude Code CLI adapter
│       ├── opencode_cli.py    # OpenCode CLI adapter
│       └── dry_run.py         # local test backend
├── tests/
│   ├── fixtures/
│   ├── test_router.py
│   ├── test_verifier.py
│   └── test_memory.py
└── pyproject.toml
```

第一版可以先用 Python。原因：

- CLI、SQLite、JSON schema、subprocess 管理很顺手。
- 方便以后接 MCP Python SDK、LiteLLM、LangGraph/AutoGen 生态。
- 对研究型原型足够快。

如果后续需要更强分发体验，再考虑 Rust/Go/Node 包装。

## Core Contracts

### Task

```json
{
  "id": "task_...",
  "repo": "/path/to/repo",
  "goal": "analyze test failure",
  "context": {
    "paths": ["..."],
    "diff": null,
    "logs": ["..."]
  },
  "constraints": {
    "mode": "read_only",
    "max_cost_usd": 0.05,
    "max_runtime_sec": 300,
    "allow_network": false
  }
}
```

### RouteDecision

```json
{
  "difficulty": "simple",
  "risk": "read_only",
  "can_delegate": true,
  "backend": "codex_subagent",
  "worker": "qwen_explorer",
  "model": "Qwen3.5-9B-AWQ",
  "reason": "log summarization is low-risk and evidence-based",
  "fallback": {
    "backend": "main_agent",
    "model": "strong"
  }
}
```

### WorkerResult

```json
{
  "status": "success",
  "summary": "evaluation failed due to CUDA OOM",
  "evidence": [
    {
      "path": "runs/train.log",
      "line": 812,
      "observation": "CUDA OOM while allocating 512 MiB"
    }
  ],
  "risks": ["log may be incomplete"],
  "next_steps": ["check GPU memory", "reduce eval batch size"],
  "artifacts": [],
  "cost": {
    "input_tokens": 0,
    "output_tokens": 0,
    "usd": null
  }
}
```

### VerificationResult

```json
{
  "accepted": true,
  "confidence": "medium",
  "needs_escalation": false,
  "issues": [],
  "memory_facts": [
    {
      "kind": "task_fact",
      "text": "Latest synthetic SkillOpt run failed during eval with CUDA OOM.",
      "evidence_ref": "runs/train.log:812"
    }
  ]
}
```

## Module Responsibilities

### Router

Router 的职责是判断任务适合谁做。

第一版可以用规则，不必马上让模型决策：

- `read_only + logs` -> cheap log summarizer。
- `read_only + code search` -> cheap explorer。
- `patch + small file scope` -> cautious worker or main agent.
- `architecture / credentials / destructive` -> main agent only.

后续再引入 learned policy 或 LLM-based classifier。

### Delegator

Delegator 负责把统一 Task 变成 backend-specific invocation。

第一版需要两个 backend：

- `codex_subagent`：生成 prompt，要求主 Codex spawn 指定 custom agent。
- `external_cli`：调用 Claude Code/OpenCode 等 CLI，并读取最终 structured output。

Delegator 必须控制：

- timeout。
- working directory。
- read-only/write policy。
- output size limit。
- environment allowlist。
- run log path。

### Verifier

Verifier 是质量闸门。

第一版先做结构化检查：

- 是否包含 summary。
- 是否包含 evidence。
- evidence path 是否存在。
- 是否出现越权行为。
- 是否明确标注不确定性。
- 是否建议了可执行 next step。

后续可以加入强模型 review，或抽样升级验证。

### Shared Memory

Shared Memory 只描述一次任务内的 worker/context/artifact 协作图，第一版用 SQLite。

建议表：

- `nodes`：worker task、context pack 和 artifact。
- `edges`：可见性、上下文和 artifact 关系。
- `worker_events`：当前任务中的 proposal、progress 和 final。
- `file_locks`：read 与 patch proposal 协调。

Memory 读取策略要保守：worker 只读取当前任务明确授权的 Context Pack 和 artifact。

跨任务的 `runs/subtasks`、plan snapshot、verified outcome、Token、失败归因和能力画像属于独立的 [Execution History](history.md)，不嵌入 Shared Memory 图。两者可以共用 SQLite 文件，但必须通过不同 repository 管理。

### Hooks

Hook 做成内部接口，不急着暴露插件系统。

第一版 hooks：

- `pre_route(task)`.
- `post_route(task, decision)`.
- `pre_delegate(task, decision)`.
- `post_delegate(task, result)`.
- `post_verify(task, verification)`.

后续可以让用户写 YAML/Python hook。

## Backend Strategy

### Codex Subagent Backend

适合 Responses-compatible provider。

当前已验证：

- Qwen vLLM `/v1/responses` 可作为 Codex custom provider。
- Codex custom agent 可以配置 `model_provider = "qwen_vllm"`。
- 主 Codex 可以 spawn 该 custom agent 并等待结果。

第一版实现思路：

- 生成或引用 custom agent TOML。
- 生成给主 Codex 的 delegation prompt。
- 要求 worker 返回严格 JSON/Markdown。
- 从主 Codex 输出中解析 worker summary。

### External CLI Backend

适合 Chat Completions-only API 或 harness-specific workflow。

目标支持：

- Claude Code: `claude -p`.
- OpenCode: `opencode run`.
- Aider: later.
- Roo/Cline: later, likely through their own CLI/API if available.

第一版先做 generic command adapter：

```yaml
backends:
  cheap_claude:
    type: external_cli
    command: claude
    args: ["-p", "--model", "haiku"]
    output_format: markdown
```

再给 Claude/OpenCode 做专门 adapter。

## Codex Integration Model

最终用户在 Codex 里不应该直接理解 Router、Memory、Verifier 的内部实现。理想使用方式是安装一个轻量 Codex 插件或配置一个 MCP server，然后在 Codex 对话中自然调用。

### Recommended Final Shape: Plugin + MCP + Skill

最终形态建议由三层组成：

1. **Codex plugin**
   - 打包项目。
   - 声明 MCP server。
   - 附带 skill/instructions。
   - 提供默认配置模板和安全说明。

2. **Local MCP server**
   - 暴露 Codex 可调用的工具。
   - 例如 `route_task`、`delegate_task`、`verify_result`、`read_memory`、`write_memory`、`cost_report`。
   - MCP server 内部再调用 Codex subagent、Claude CLI、OpenCode CLI 或 dry-run backend。

3. **Codex skill / instruction layer**
   - 告诉 Codex 什么时候应该使用 router。
   - 例如：日志分析、测试失败、只读搜索、PR review 初诊时，先调用 router，而不是主模型自己吞所有上下文。

用户视角应该像这样：

```text
请用 cost router 分析这个失败日志，便宜 worker 先做，主 Codex 只做验收。
```

或者更自然：

```text
这个任务比较长，尽量用低成本 worker 做只读分析，最后你来汇总和验收。
```

### Minimal Usable Shape: CLI Wrapper

插件和 MCP server 做完前，可以先提供 CLI：

```bash
router run --goal "analyze this failure" --path runs/train.log --backend dry-run
router run --goal "analyze this failure" --path runs/train.log --backend codex-subagent
router run --goal "analyze this failure" --path runs/train.log --backend claude-cli
```

Codex 也可以通过 shell 调这个 CLI。

优点：

- 最容易实现。
- 不依赖 Codex plugin packaging。
- 方便调试 memory、ledger 和 verifier。

缺点：

- 用户体验不如 MCP 工具自然。
- Codex 需要通过命令行读写结果。

### Full Codex Workflow

最终在 Codex 中的体验应该是：

1. 用户安装项目插件或配置 MCP server。
2. 用户在 `.env` 或配置文件里声明可用 backends。
3. 用户启动 Codex。
4. Codex 识别到任务适合 router。
5. Codex 调用 MCP tool：`route_task`。
6. Router 返回建议：用 Qwen subagent / Claude CLI / OpenCode。
7. Codex 调用 `delegate_task`。
8. Worker 完成子任务。
9. Router 调用 verifier，写 memory/ledger。
10. Codex 只读取结构化 summary 和 verified facts，继续主任务。

### Why MCP Is The Best Integration Point

MCP 不是项目的核心价值，但它是嵌入 Codex 的最好工程边界：

- Codex 官方支持 MCP。
- MCP tool 可以隐藏复杂 backend。
- 用户不需要把 router 代码直接塞进 Codex prompt。
- router 可以独立迭代。
- Claude/OpenCode external backend 也可以藏在 MCP server 后面。

### Why Plugin Matters Later

只配置 MCP server 也能用，但插件能让开源项目更像一个完整产品：

- 带默认 skill。
- 带推荐配置模板。
- 带默认 agent profiles。
- 带 MCP server manifest。
- 带安全说明和权限声明。

因此路线建议是：

1. 先做 CLI。
2. 再做 MCP server。
3. 最后包装成 Codex plugin。

## Open Source Components To Reuse

### Model/API Layer

- **LiteLLM**：可选，用于把多 provider 暴露成统一 OpenAI-compatible endpoint，或记录成本、fallback、rate limit。
- **RouteLLM**：可参考 strong/weak model routing 的思想，但不直接作为 coding task router。
- **Semantic Router**：可参考快速语义分类，后续用于 task type routing。

### Agent/Harness Layer

- **Codex CLI**：主控和 internal subagent backend。
- **Claude Code CLI / SDK**：external harness backend。
- **OpenCode CLI**：external harness backend，尤其适合多 provider 便宜模型。
- **Aider**：参考 architect/editor 多模型分工。
- **Roo Code Boomerang Tasks**：参考 orchestrator/subtask/mode 设计。
- **tap**：参考跨 agent 文件通信、handoff、receipt、review 留痕。

### Framework/Infra Layer

- **Typer** 或 **Click**：CLI。
- **Pydantic**：schema validation。
- **SQLite**：memory 和 cost ledger。
- **Rich**：本地 CLI 输出。
- **pytest**：测试。
- **jsonschema**：worker structured output 校验。
- **MCP Python SDK**：后续实现 MCP delegate server。

原则：第一版只集成必要依赖。优先通过 CLI/subprocess 连接外部 harness，不急着深度嵌入大型框架。

## Security Principles

- 默认 read-only。
- 默认不发送真实私有目录到外部 provider，除非用户明确允许。
- 默认不把 API key 写入生成文件。
- `.env` 只本地使用并被 `.gitignore` 忽略。
- 可写任务必须在 worktree 或临时目录中执行。
- Worker 输出必须经过 verifier。
- Memory 不存密钥、完整日志、完整 transcript。

## First Implementation Slice

建议第一批代码只做：

1. `schemas.py`：定义 Task、RouteDecision、WorkerResult、VerificationResult。
2. `router.py`：规则路由，只支持 read-only log analysis。
3. `backends/dry_run.py`：不调用模型，用 fixture 模拟 worker result。
4. `verifier.py`：检查 summary/evidence/next_steps。
5. `memory.py`：SQLite 写入 run/subtask/fact/cost。
6. `cli.py`：`router run --task ... --path ... --dry-run`。

等 dry-run 闭环稳定，再接：

- `backends/codex_subagent.py`
- `backends/external_cli.py`

这样第一步可以完全离线测试，不消耗 token，也不碰真实 API。

## Success Criteria

第一版成功不看功能数量，而看是否能稳定回答：

- 这个任务为什么被路由给某个 backend？
- 低成本 worker 做了什么？
- verifier 为什么接受或拒绝？
- 如果拒绝，是否升级到强模型？
- memory 记录了哪些可复用事实？
- 和强模型单独完成相比，主模型 token 是否下降？

如果这些问题能被结构化记录下来，这个项目就有了继续做下去的工程基础。
