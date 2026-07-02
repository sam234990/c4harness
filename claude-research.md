# Codex 调用 Claude / OpenCode 的可行性调研

日期：2026-06-22

## 摘要结论

这个想法有现实基础，但要区分三件事：

1. **换模型 provider**：Codex 可以配置自定义模型 provider，只要目标端支持 OpenAI Responses 或 Chat Completions 兼容接口。Claude 原生 API 通常需要 LiteLLM 这类网关转换。
2. **调用外部 agent 执行子任务**：Claude Code、OpenCode 都有非交互 CLI/SDK/Server 能力，适合被 Codex 通过 shell、脚本或 MCP server 间接调用。
3. **agent-to-agent 协作**：MCP 是工具/上下文协议，不是天然的 agent 委托协议。要让 Codex “委托 Claude agent 做任务”，需要自定义 MCP 工具、CLI 包装器，或使用 tap 这类文件式跨 agent 协作项目。

最推荐的实验路径是：

- 短期优先尝试 Codex custom subagent：为轻量只读任务配置一个便宜模型/provider 的 `explorer-cheap` agent，然后在 prompt 中显式要求 Codex spawn 这个 agent。
- 如果 custom subagent 的 `model_provider` 在本机版本里不可用，再退到 CLI 调 `claude -p` 或 `opencode run` 做只读研究、日志总结、review。
- 中期：做一个本地 MCP server，暴露 `delegate_to_claude`、`delegate_to_opencode` 等工具。
- 长期：评估 `@hua-labs/tap`、`magents`、`Ruflo` 这类跨 agent 协作/编排项目。

## 官方能力现状

### Codex

根据 OpenAI Codex manual，Codex 的关键相关能力包括：

- 支持自定义模型 provider：provider 定义 base URL、wire API、认证和 header；可以指向支持 Chat Completions 或 Responses API 的模型/服务。
- 支持 MCP：CLI 和 IDE extension 支持 stdio server、streamable HTTP server、Bearer/OAuth 认证、工具 allow/deny、超时等配置。
- 支持 `codex exec` 非交互模式：适合脚本、CI、管道、JSONL 事件输出、结构化输出。
- 支持 subagents：可并行运行专门 agent。官方 manual 明确提醒 subagent 自己也会消耗模型和工具 token，所以它不是自动省 token 的办法；只有在给 subagent 指定更便宜模型/provider 或让它处理“会污染主上下文的噪声任务”时，才可能减少主线程 GPT 额度压力。

注意事项：

- Codex 项目级 `.codex/config.toml` 不能覆盖 `model_provider` 和 `model_providers` 等 credential/provider 相关配置；这些要放到用户级 `~/.codex/config.toml`。
- Codex 当前仍支持 Chat Completions provider，但 manual 说明该支持已 deprecated，将来会移除。因此长期方案应优先走 Responses API 或保持可替换网关。
- Codex 不会自动把简单任务分流到其他 provider。Subagent 也需要显式触发；manual 说 Codex 只在你明确要求 subagent/parallel agent work 时才 spawn subagent。

#### Codex custom subagent 指定不同 provider 的可能性

官方 manual 对 custom agents 的描述非常关键：

- custom agent 文件位于 `~/.codex/agents/` 或项目内 `.codex/agents/`。
- 每个 custom agent 文件是一个 TOML 配置层，用于 spawned session。
- 必填字段是 `name`、`description`、`developer_instructions`。
- 可选字段明确包括 `model`、`model_reasoning_effort`、`sandbox_mode`、`mcp_servers`、`skills.config`；manual 还说 custom agent 文件可以包含其他受支持的 `config.toml` keys。

因此理论上可以尝试在 custom agent 文件里写 `model_provider = "cheap_proxy"`，让某类 subagent 使用便宜 provider。但这里有一个需要实测确认的边界：manual 示例没有直接展示 custom agent 内配置 `model_provider`，只明确展示了 `model` 和 `model_reasoning_effort`。我的判断是“值得优先试”，但不应在没有本机验证前当作稳定承诺。

一个可测试配置形态如下：

```toml
# ~/.codex/config.toml
model = "gpt-5.5"
model_provider = "openai"

[model_providers.cheap_proxy]
name = "Cheap Responses-compatible proxy"
base_url = "http://127.0.0.1:4000/v1"
wire_api = "responses"
env_key = "CHEAP_PROXY_API_KEY"
```

```toml
# ~/.codex/agents/cheap-explorer.toml
name = "cheap-explorer"
description = "Read-only exploration agent for logs, repo search, summaries, and low-risk investigation using a cheaper provider."
model = "your-cheap-model"
model_provider = "cheap_proxy"
model_reasoning_effort = "low"
sandbox_mode = "read-only"

developer_instructions = """
You are a low-cost read-only exploration agent.
Use rg/git/read-only shell commands to investigate.
Do not edit files.
Return a concise summary with file paths and evidence.
"""
```

调用方式不是自动路由，而是在 prompt 里明确要求：

```text
Spawn the cheap-explorer subagent to scan logs and related files.
Wait for it to finish, then use its concise findings to decide the fix.
```

如果这个配置在本机 Codex 版本里报错或忽略 `model_provider`，退路是：

- 只在 custom agent 里指定便宜的 OpenAI 内部模型，例如 `gpt-5.4-mini`。
- 用 `codex exec --profile cheap` 单独跑子任务。
- 用 CLI/MCP 委托 Claude/OpenCode。

#### 本机 `.env` API 实测结果

2026-06-22 对当前 `.env` 中的 provider 做了只读连通性测试，未打印 API key：

- `GET /v1/models`：HTTP 200，返回 OpenAI-style `{object, data}`，共 9 个模型，`.env` 中配置的模型存在。
- `POST /v1/responses`：HTTP 404，说明当前 endpoint 不支持 Responses API。
- `POST /v1/chat/completions`：HTTP 200，能正常返回内容；第一次 `max_tokens=20` 时 token 全花在 reasoning 上导致正文为空，第二次 `max_tokens=100` 正常返回 `chat-ok`。
- `codex exec` 直接使用该 provider：Codex 识别到 `provider = cheap_proxy` 和配置模型，但实际请求 `/v1/responses` 后失败。
- `wire_api = "chat"`：Codex 0.139.0 直接拒绝，报错为 `wire_api = "chat" is no longer supported`，要求设置 `wire_api = "responses"`。

结论：当前 `.env` API 本身可用，但它是 Chat Completions 兼容接口，不是 Responses 兼容接口。它暂时不能直接作为当前 Codex custom provider 或 custom subagent provider 使用。要走 Codex 内部 provider/subagent 路线，需要在中间加一个 Responses-compatible adapter/proxy，或换一个支持 `/v1/responses` 的 base URL。否则只能走 CLI/MCP 委托，让外部 Claude/OpenCode/自写脚本直接调用这个 chat API。

#### Qwen vLLM Responses endpoint 实测结果

2026-06-22 又测试了 `/home/wangshu/skill/SkillOpt/shu/env/skillopt-qwen3.5-9b-awq-sealos-100k.env` 中的 Qwen endpoint：

- `GET /v1/models`：HTTP 200，返回 1 个模型，配置模型 `Qwen3.5-9B-AWQ` 存在。
- `POST /v1/responses`：HTTP 200，返回 Responses-style 对象，包含 `output`、`output_messages`、`usage` 等字段。
- `POST /v1/chat/completions`：HTTP 200，也可用；但该服务会把 thinking 文本放入 `content`，短 `max_tokens` 容易截断。
- `codex exec` 直接使用该 provider：成功。Codex 识别 `provider = qwen_vllm`、`model = Qwen3.5-9B-AWQ`，并通过 `/v1/responses` 返回结果。
- Codex custom subagent 测试：成功。主 Codex 仍使用默认 OpenAI provider，临时 `qwen_explorer` custom agent 配置 `model_provider = "qwen_vllm"`，能被主线程 spawn，并用 Qwen provider 完成合成 SkillOpt 失败日志分析。

结论：这条路线是可行的。只要 provider 支持 `/v1/responses`，Codex custom subagent 可以用不同 `model_provider`，从而实现“主 Codex + 低成本子 agent”的内部多 agent 降本实验。真实 SkillOpt 目录测试没有直接执行，因为会把本地运行结果发送给外部 provider；如需测试真实目录，需要明确确认该数据外传风险。

来源：

- [OpenAI Codex manual](https://developers.openai.com/codex/codex-manual.md)
- [Codex MCP manual section](https://developers.openai.com/codex/mcp.md)
- [Codex non-interactive mode](https://developers.openai.com/codex/noninteractive.md)
- [Codex subagents](https://developers.openai.com/codex/subagents.md)
- [Codex subagent concepts](https://developers.openai.com/codex/concepts/subagents.md)

### Claude Code / Claude Agent SDK

Claude Code 官方文档显示：

- CLI 支持 `claude -p "query"` print/非交互模式，能处理管道输入、指定模型、限制 turn、输出 JSON/stream JSON、设置预算等。
- Claude Code 支持 MCP client，能连接 HTTP、SSE、stdio、WebSocket MCP server。
- Claude Code 可以通过 `claude mcp serve` 作为 MCP server 暴露给其他 MCP client，但文档说明它暴露的是 Claude Code 的工具能力，如 View/Edit/LS；这不等同于一个“让 Claude 完整接任务并返回结果”的标准委托接口。
- Claude Agent SDK 提供 Python/TypeScript 库，能在自己的进程里运行带工具执行能力的 Claude agent；支持 built-in tools、hooks、subagents、MCP、permissions、sessions。
- Claude subagents 可以限制工具、限制可生成的子 agent、为 subagent 单独配置 MCP server。

对本设想的意义：

- `claude -p` 是最简单的被 Codex 调用方式。
- Claude Agent SDK 更适合做自定义 MCP 委托服务器的内部执行引擎。
- `claude mcp serve` 不能直接理解为“Codex 调 Claude agent”，它更像把 Claude Code 的文件/编辑等工具暴露给另一个 host。

来源：

- [Claude Code CLI reference](https://code.claude.com/docs/en/cli-reference)
- [Claude Code MCP docs](https://code.claude.com/docs/en/mcp)
- [Claude Agent SDK overview](https://code.claude.com/docs/en/agent-sdk)
- [Claude Code subagents](https://code.claude.com/docs/en/sub-agents)

### OpenCode

OpenCode 官方文档显示：

- OpenCode 是开源 coding agent，支持终端、桌面 app、IDE extension。
- 配 provider 时可以使用多种 LLM provider，也支持 OpenAI-compatible provider。
- `opencode run` 支持非交互执行，适合脚本和自动化；可指定 `--model provider/model`、`--agent`、`--format json`、`--attach` 到正在运行的 `opencode serve` 以减少 MCP 冷启动。
- OpenCode 支持 MCP client，本地和远程 MCP server 都可配置；文档特别提醒 MCP 工具描述会增加上下文，工具太多容易吃掉 context。
- OpenCode 支持自定义 agents，可为 agent 指定模型、prompt、工具开关；示例中 code-reviewer 使用 Claude Sonnet，命令示例可指定 Claude Haiku。

对本设想的意义：

- OpenCode 很适合成为“便宜子 agent harness”，尤其是它已经能接你现有的多 provider API。
- `opencode serve + opencode run --attach` 是一个值得测试的长任务优化点，可以减少每次 run 重新拉起 server/MCP 的成本。
- 和 Claude 一样，OpenCode 的 MCP 支持主要是“让 OpenCode 调工具”，不是天然被 Codex 委托；要被 Codex 调，需要 CLI 包装或自定义 MCP server。

来源：

- [OpenCode intro](https://opencode.ai/docs)
- [OpenCode CLI](https://opencode.ai/docs/cli/)
- [OpenCode providers](https://opencode.ai/docs/providers)
- [OpenCode MCP servers](https://opencode.ai/docs/mcp-servers/)
- [OpenCode config agents](https://opencode.ai/docs/config)

## MCP 互联是否足够

MCP 官方规范定义的是 AI 应用与外部系统之间的标准连接方式，server 可以提供：

- Resources：上下文和数据。
- Prompts：模板化消息和 workflow。
- Tools：模型可执行的函数。

这使 MCP 很适合连接数据库、浏览器、GitHub、文档、Figma、Sentry 等工具，也适合做一个 `delegate_to_claude` 工具。但 MCP 本身没有规定“一个 agent 怎样把任务完整委托给另一个 agent、怎样继承上下文、怎样返回 patch、怎样处理长时间运行、怎样做预算和身份审计”。

所以结论是：

- Codex ↔ MCP：可用，官方支持。
- Claude Code ↔ MCP：可用，官方支持。
- OpenCode ↔ MCP：可用，官方支持。
- Codex ↔ Claude/OpenCode 直接 agent 委托：没有看到一个官方、通用、成熟的标准；需要 CLI/MCP 包装或第三方协议。

来源：

- [MCP introduction](https://modelcontextprotocol.io/docs/getting-started/intro)
- [MCP specification 2025-06-18](https://modelcontextprotocol.io/specification/2025-06-18)

## 相关开源项目和软件

### LiteLLM

LiteLLM Proxy 官方文档说明它提供 LLM gateway，能用 OpenAI Chat Completions / Completions 格式调用 100+ LLM/provider，并支持 Anthropic。它也提供成本追踪、认证、预算、负载均衡等网关功能。

用途：

- 如果你想让 Codex 直接使用 Claude 或其他便宜 API，可用 LiteLLM 把 provider 转成 OpenAI-compatible endpoint。
- 也可把 LiteLLM 放在 OpenCode/Claude 子 agent 背后做预算和路由。

限制：

- 这更像“替换模型/统一网关”，不是“Codex 只把部分任务外包给 Claude”。
- Codex 长期最好走 Responses-compatible provider；如果只走 Chat Completions，要注意未来兼容风险。

来源：

- [LiteLLM Proxy quick start](https://docs.litellm.ai/docs/proxy/quick_start)
- [LiteLLM Anthropic provider](https://docs.litellm.ai/docs/providers/anthropic)

### tap / @hua-labs/tap

`@hua-labs/tap` 非常贴近这个想法。项目 README 写明：它把 repo 变成 Claude、Codex、Gemini 共享工作区，通过文件式 P2P 消息让多个 AI agent 在同一代码库协调，无需手写 glue code。

项目支持：

- `npx @hua-labs/tap init`
- `npx @hua-labs/tap add claude`
- `npx @hua-labs/tap add codex`
- `npx @hua-labs/tap serve`
- 共享 `tap-comms` 目录，保存 inbox、reviews、findings、handoff、logs 等 Markdown 文件。
- Claude 使用 `.mcp.json` native-push；Codex 使用 `~/.codex/config.toml` 和 WebSocket bridge。

优点：

- 正好解决跨 vendor agent 没有共享 runtime 的问题。
- 文件是原始消息和审计记录，适合长任务、重启恢复、review 留痕。

风险：

- 截至检索时 GitHub star 数不高，项目较新，成熟度需要验证。
- Codex 侧需要 bridge daemon；要确认与你本地 Codex 版本、权限模型兼容。
- 它是协作协议，不是简单“省 token 开关”；需要设计工作流和 discipline。

来源：

- [HUA-Labs/tap GitHub](https://github.com/hua-labs/tap)
- [tap paper: File-Based Protocol for Heterogeneous LLM Agent Collaboration](https://arxiv.org/abs/2606.14445)

### Ruflo / Claude Flow

`ruvnet/claude-flow` 目前重定向到 `ruvnet/ruflo`。它自称是面向 Claude Code 和 Codex 的 multi-agent AI harness，目标是用 swarm、memory、federated comms、插件和 MCP 来协调大量专门 agent。README 中还明确写到 Multi-Provider，包括 Claude、GPT、Gemini、Cohere、Ollama 和 smart routing。

用途：

- 值得作为“多 agent 编排 + 多 provider 路由”的参考项目。
- 如果目标是让多个 agent 跨机器、跨信任边界协作，它比单纯 CLI wrapper 更接近完整平台。

风险：

- 项目表述很宏大，功能面非常宽，需要实际安装验证哪些能力稳定可用。
- 它更像 Claude/Ruflo 生态的 meta-harness；如果只是想给 Codex 加一个便宜 worker，可能过重。

来源：

- [ruvnet/ruflo GitHub](https://github.com/ruvnet/ruflo)

### magents

`Santos-Enoque/magents` 是一个 Multi-Agent Claude Code Workflow Manager，README 写明它用 git worktrees 和 Docker isolation 管理多个 Claude Code 实例。它支持每个 agent 在自己的 worktree/容器里工作，带 Task Master 集成、Dashboard、Docker 模式和并行任务示例。

用途：

- 很贴近“把简单任务交给多个 Claude Code agent 并行做”的路线。
- 它不是 Codex 内部 subagent，而是外部 Claude Code 多实例编排器；适合作为 CLI 委托/外部 worker pool 的参考。

风险：

- GitHub 页面显示 star 很少、无 release，需要谨慎验证维护状态。
- 示例里偏 Claude Code，不是现成 Codex→Claude 委托工具。

来源：

- [Santos-Enoque/magents GitHub](https://github.com/Santos-Enoque/magents)

### claude-parallel-agents

`sean-rowe/claude-parallel-agents` 是一个 Bash/Zsh 风格的 Claude Code 并行工作流：为每个 feature 建 git worktree，启动 Claude Code 实例，记录日志，监控进度，可选自动重启。

用途：

- 简单、透明，适合作为“自己写一个 Codex 调度脚本”的最小参考。
- 它明确强调独立 feature、worktree 隔离、进度监控和 PR review。

风险：

- README 示例使用 `--dangerously-skip-permissions` 启动 Claude Code，安全上不适合直接照搬。
- star 很少，更像个人脚本项目。

来源：

- [sean-rowe/claude-parallel-agents GitHub](https://github.com/sean-rowe/claude-parallel-agents)

### Sidekick Agent Hub

`sidekick-agent-hub` 不是委托执行器，而是多 provider agent 监控和辅助工具。README 写明它支持 Claude Max、Claude API、OpenCode、Codex CLI，能跟踪 tokens、cost、context 和 session，并支持 Claude Code / Codex 多账号切换。

用途：

- 如果你的目标是“知道到底哪里烧 token、哪个 agent 最贵、上下文何时胀满”，它很有价值。
- 可以作为降本方案的观测层，而不是执行层。

风险：

- 它解决可见性和会话管理，不直接解决 Codex 自动分流。

来源：

- [Sidekick Agent Hub GitHub](https://github.com/cesarandreslopez/sidekick-agent-hub)

### Aider

Aider 不是 Codex/Claude Code 的委托器，但它是一个成熟的开源终端 AI pair programmer，支持多个 LLM/provider。它的 `architect` mode 会用一个 architect model 提方案，再用 editor model 生成具体文件编辑；高级模型设置里也有 `weak_model_name`、`editor_model_name` 这类配置。

用途：

- 它提供了一个成熟范式：不同阶段用不同模型，而不是所有事情都用同一个 frontier model。
- 对“Codex 主控 + 便宜 editor/researcher”的设计有参考意义。

风险：

- 它是独立工具，不是 Codex 的插件式子 agent。

来源：

- [Aider chat modes](https://aider.chat/docs/usage/modes.html)
- [Aider advanced model settings](https://aider.chat/docs/config/adv-model-settings.html)

### GitHub Agent HQ

GitHub Agent HQ 不是开源项目，但它说明“在同一个开发平台里选择 Claude、Codex、Copilot 等多个 coding agent，并行运行/比较结果”已经成为主流产品方向。The Verge 和 TechRadar 都报道了 GitHub 把 Claude 和 Codex 接入 Agent HQ，用户可以把 agent 分配给 issue/PR，并在同一工作流里比较输出。

用途：

- 证明你的思路并不小众：多 agent 控制台、多 provider agent、并行任务和人工选择结果，已经是产品级方向。

限制：

- 它是 GitHub/Copilot 生态能力，不是你本地 Codex CLI 的开源实现。

来源：

- [The Verge: GitHub adds Claude and Codex AI coding agents](https://www.theverge.com/news/873665/github-claude-codex-ai-agents)
- [TechRadar: GitHub integrates Claude and Codex AI coding agents](https://www.techradar.com/pro/github-integrates-claude-and-codex-ai-coding-agents-directly-into-github)

## 编排深度：任务拆分、Agent 通信和 Hook

只看“能切 provider”还不够。对这个降本设想更关键的是：系统有没有任务拆分、agent 生命周期、agent 间通信、hook/worker、失败恢复和结果归并。按这个标准，目前看到的项目可以分成几类：

| 项目 | 任务拆分/分配 | Agent 间通信 | Hook/生命周期 | 结果归并/审计 | 对本设想的价值 |
| --- | --- | --- | --- | --- | --- |
| Codex custom subagents | 需要主 prompt 显式拆分；Codex 可 spawn 指定 subagent | 主线程收集 subagent summary | Codex 有 SubagentStart/SubagentStop hooks，但跨 provider 需实测 | 主线程汇总 | 最轻量，若 `model_provider` 可用就是首选 |
| tap | 不负责自动拆任务，重点是跨 runtime 通信 | 强：`inbox/`、`reviews/`、`findings/`、`handoff/`、`receipts/` 等文件协议 | 有 runtime adapter、bridge、watch、doctor；目录里也有 hooks | 强：Markdown 留痕、回执、归档 | 最贴近 Codex/Claude/Gemini 协作层 |
| Ruflo / Claude Flow | 声称有 router、swarm、GOAP planner、100+ agents、background workers | 强：comms layer、federation、swarm coordination | 强：README 明确说 hooks 自动路由任务、12 个 auto-triggered workers | 强：memory、cost tracker、observability | 最像完整多 agent 编排平台，但重且需验证 |
| magents | 中到强：Task Master parse PRD、task-create、task-agents，可为任务创建 agent | 中：共享 Task Master/CLAUDE.md/MCP config，主要不是 agent-to-agent 消息协议 | 中：Docker/container lifecycle、dashboard/monitor；未看到通用 hook 系统 | 中：Task Master status/notes、dashboard | 适合外部 worker pool，不是 Codex 内置 |
| claude-parallel-agents | 弱到中：从 `features.json` 手工列 features；每个 feature 一个 agent | 弱：主要通过日志和状态文件监控 | 中：auto-restart daemon、cron CodeRabbit autofix | 中：独立 logs/status/PR | 简单透明，适合参考脚本结构 |
| Sidekick Agent Hub | 弱：不负责拆任务 | 弱：监控多 provider session，不是消息总线 | 中：live event/session monitoring | 强：tokens/cost/context/session 可视化 | 适合作为观测层，帮判断是否真的降本 |
| Aider | 中：architect/editor 模式把规划和编辑分成两次模型调用 | 弱：不是多 agent 通信系统 | 弱到中：有模型阶段配置，但不是生命周期 hook 平台 | 中：Git diff/commit 工作流 | 参考“强模型规划 + 便宜模型编辑”的范式 |

### 具体判断

#### tap 的“hook/通信”设计

tap 最强的是通信层，不是自动 planner。它把不同 runtime 接到同一个 `tap-comms` 目录，目录里有：

- `inbox/`：agent-to-agent messages。
- `reviews/`：代码审查结果。
- `findings/`：离题但有价值的发现。
- `handoff/`：会话交接文档。
- `receipts/`：已读回执。
- `archive/`：归档消息。

它还有 adapter contract：probe、plan、apply、verify，用于把 Claude、Codex、Gemini 等 runtime 接进来。Claude 是 `.mcp.json` native-push，Codex 是 `~/.codex/config.toml` + WebSocket bridge。也就是说，tap 很适合做“多 agent 之间怎么互相留言、交接、审查、留证据”，但任务拆解仍然主要靠人或上层 agent。

#### Ruflo 的“自动路由/hook”设计

Ruflo 是目前看起来最像你说的“hook 设计”的项目。README 明确写到：

- Claude Code 初始化后，hooks system 会自动路由任务、学习成功模式、协调 agent。
- 架构里有 Router、Swarm、Agents、Memory、LLM Providers。
- 有 100+ specialized agents。
- 有 hierarchical/mesh/adaptive swarm coordination。
- 有 12 个 auto-triggered background workers。
- 有 cost tracker、observability、federation、smart routing、多 provider。
- 还有 GOAP A* planner，把 plain-English goals 转成 executable agent plans。

这说明它不仅是 provider 切换，也在做任务路由、后台 worker、agent 协作和记忆。但它的问题是功能面极大，README marketing 色彩很强，需要本地实测确认：哪些是稳定 CLI/MCP 能力，哪些是插件/云/实验功能。

#### magents 的任务拆分

magents 的任务拆分主要依赖 Task Master AI：

- `task-master parse-prd docs/requirements.txt`：从需求文档生成任务。
- `magents task-create <task-id>`：为单个任务创建 agent。
- `magents task-agents`：为所有 pending tasks 自动创建 agents。
- 每个 agent 可使用 `task-master next/show/set-status/update-subtask`。

这是一种很实用的“任务系统驱动 agent 池”模式。它不像 tap 那样强调 agent-to-agent 消息，也不像 Ruflo 那样强调自动 hooks/swarm；它更像项目管理器：先拆 PRD，再给每个任务拉一个 Claude Code worker。

#### claude-parallel-agents 的拆分和 hook

claude-parallel-agents 走的是最朴素路线：你写 `features.json`，每个 feature 有独立 instructions；工具创建 worktree、启动 Claude Code、写日志、维护状态、监控进度、失败自动重启。它还有 CodeRabbit review comment cron autofix。

这不是智能 task planner，但对我们很有启发：最小可用系统不一定要复杂。一个 JSON 任务列表 + worktree + logs + monitor + restart daemon，就能做出低成本 worker pool。

#### Sidekick 的位置

Sidekick 不做任务拆分和 agent-to-agent 通信，但它解决另一个关键问题：观测。你的目标是降本，那就必须知道：

- 哪个 agent 烧了多少 token。
- 哪个 session context 快满了。
- 哪些 tool calls 最频繁。
- 任务拆出去后是否真的减少主 Codex 成本。

所以 Sidekick 更像降本体系里的仪表盘，而不是调度器。

### 小结

如果按“最贴近目标”排序：

1. **Codex custom subagent + cheap provider**：最轻，但需验证 `model_provider` 是否在 custom agent 文件里生效。
2. **tap**：最适合跨 Codex/Claude 的 agent 间通信、交接、review、留痕。
3. **magents**：最适合 PRD/task-list 驱动的外部 Claude worker pool。
4. **Ruflo**：功能最完整，包含 routing/hooks/swarm/workers/memory/cost，但引入成本最高。
5. **Sidekick**：作为观测层很有用，特别适合证明是否真的省钱。

### Code2MCP / AutoMCP 类项目

调研中还看到一些 MCP 自动生成方向的项目/论文，例如把 GitHub repo 或 OpenAPI 规格自动转成 MCP server。它们不直接解决 Codex 调 Claude，但说明 MCP 生态正在补“工具接入成本太高”的问题。

用途：

- 后续如果你要把内部脚本、日志系统、评测平台、模型服务封装给 Codex/Claude/OpenCode 共用，这类方向有参考价值。

来源：

- [Code2MCP paper](https://arxiv.org/abs/2509.05941)
- [AutoMCP / OpenAPI to MCP paper](https://arxiv.org/abs/2507.16044)

## 先决条件清单

### 账号/API

- Anthropic API key，或你已有的 Claude-compatible provider key。
- OpenCode 已能连接这些便宜 API。
- 如果走 Codex provider 替换，需要 OpenAI-compatible 或 Responses-compatible 网关。
- 如果走 LiteLLM，需要部署 LiteLLM proxy 并配置 Anthropic/其他 provider。

### 本地工具

- `claude` CLI 可用，且 `claude auth status` 正常或 `ANTHROPIC_API_KEY` 可用。
- `opencode` CLI 可用，且 `opencode models` 能列出目标模型。
- Codex CLI 可用，MCP 配置可写到用户级 `~/.codex/config.toml`。
- 需要 `git worktree` 支持，以隔离可写子任务。

### 权限与安全

- 子 agent 默认只读。
- 对可写任务使用 worktree，不允许直接操作主工作区。
- 禁止危险命令：`rm -rf`、`git reset --hard`、force push、改权限、读密钥文件。
- 限制最大预算、最大 turn、最大输出字符。
- 子 agent 输出只返回摘要、patch、关键证据，不返回完整 transcript。
- MCP server 的 tool description 和外部内容都按不可信处理。

### 结果格式

建议所有委托任务都返回结构化 Markdown 或 JSON：

```json
{
  "summary": "...",
  "evidence": [
    {"path": "src/example.ts", "observation": "..."}
  ],
  "patch_path": null,
  "risks": ["..."],
  "recommended_next_step": "..."
}
```

## 可行性评级

| 方案 | 可行性 | 成本节省潜力 | 工程复杂度 | 主要风险 |
| --- | --- | --- | --- | --- |
| Codex 直接换 provider / LiteLLM | 高 | 中到高 | 中 | provider 兼容、Responses API 支持、模型行为差异 |
| Codex custom subagent 指定便宜 provider | 中高，需本机实测 | 高 | 低到中 | `model_provider` 在 custom agent 文件中的支持需确认；仍需显式 spawn |
| Codex custom subagent 指定便宜 OpenAI 模型 | 高 | 中 | 低 | 仍消耗 OpenAI/Codex 侧额度，但可降低单次成本 |
| Codex 通过 shell 调 `claude -p` | 高 | 中 | 低 | 上下文传递和输出清洗 |
| Codex 通过 shell 调 `opencode run` | 高 | 中 | 低 | 同上，另需 OpenCode provider 配置 |
| 自建 MCP 委托 server | 中高 | 高 | 中高 | 安全、预算、长任务状态、失败恢复 |
| tap 文件式多 agent 协作 | 中 | 高 | 中 | 项目成熟度、bridge 运维、工作流纪律 |
| Ruflo / Claude Flow | 中 | 高 | 中高到高 | 功能面大，需验证稳定性和是否过重 |
| magents / claude-parallel-agents | 中 | 中到高 | 中 | 更偏 Claude Code 外部 worker，不是 Codex 内置委托 |
| Sidekick Agent Hub | 高 | 间接 | 低到中 | 主要是观测和账号/会话管理，不负责自动分流 |
| 纯 Codex subagents | 高 | 低或负 | 低 | 官方提示会增加 token，除非子 agent 换便宜 provider |

## 推荐下一步实验

1. 先验证 Codex custom agent 能否使用 `model_provider`：建一个 `cheap-explorer.toml`，让它只读扫描一个小目录，看请求是否打到 cheap proxy。
2. 如果成功，把 `cheap-explorer` 固化为日志总结、代码搜索、测试失败初诊的默认 worker。
3. 如果失败，再选一个真实但低风险任务，例如“读最近一次失败测试日志并定位原因”。
4. Codex 主线程只准备最小上下文和验收标准。
5. 分别调用：

```bash
claude -p --model haiku --max-turns 3 "..."
opencode run --model anthropic/claude-haiku-4-5 --agent researcher --format json "..."
```

6. 记录：

- Codex 主线程 token。
- Claude/OpenCode 费用。
- wall time。
- 输出是否足够准确。
- Codex 为了验证输出又花了多少 token。

7. 如果 3-5 次任务都有收益，再封装 MCP server 或测试 tap/magents/Ruflo。

## 最终判断

“Codex 主控 + 低成本子 agent”是合理方向。现在最值得优先验证的是 Codex custom subagent 能否稳定使用不同 `model_provider`：如果可行，它是最轻量的内建路线；如果不可行，再转向 CLI 委托、MCP 委托服务器或 tap/Ruflo/magents 这类外部编排层。

最关键的不是技术上能不能调用，而是要把委托边界设计得足够窄：任务小、上下文少、权限低、输出短、可验收。否则多 agent 很容易变成“多一层不确定性 + 多一份 transcript + 更多 token”。
