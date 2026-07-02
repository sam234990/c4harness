# Cost-Aware Multi-Agent Coding Router

日期：2026-06-22

## Motivation

长任务里，Codex 这类强 coding agent 很容易把额度消耗在大量低风险但高 token 的工作上：读日志、扫代码、找调用链、总结测试失败、写初版文档、做重复性 review。与此同时，不同模型和不同 agent harness 的能力、价格、接口形态差异越来越大：

- 有些模型便宜、快，适合只读探索和日志总结。
- 有些模型贵但稳，适合最终决策、复杂推理、跨文件修改和验收。
- 有些 API 只支持 Chat Completions，不支持 Codex 需要的 Responses API。
- 有些模型在特定 harness 里表现更好，例如 Claude Code、OpenCode、Aider、Roo Code 等。

因此真正有价值的事情，不是简单让 agent 之间“能通信”，而是做一个面向 coding tasks 的成本感知调度层：任务进来后，自动判断难度、风险、预算和上下文需求，把合适的子任务交给合适的模型或 agent harness，再由强模型验收和整合。

这个项目的核心目标是：

> 在尽量保持结果质量的前提下，把长 coding task 中低风险、可隔离、可验证的部分路由给更便宜的模型或外部 agent，从而降低强模型 token 消耗。

## Project Positioning

这个方向不应该做成又一个通用 multi-agent framework。LangGraph、CrewAI、AutoGen 已经覆盖了通用编排；Roo Code 已经有 IDE 内 orchestrator；tap 已经在做跨 agent 文件通信；LiteLLM/RouteLLM/Semantic Router 已经在做 request/query 级别路由。

更清晰的定位是：

> 一个 Codex-first、但 backend 可插拔的 coding-agent task router。

它和已有项目的区别在于：

- 不是通信优先，而是成本、质量和升级策略优先。
- 不是单一 harness，而是同时支持 Codex internal subagent 和 external harness。
- 不是 request-level LLM gateway，而是 task-level coding router。
- 不是把所有 agent transcript 混在一起，而是用结构化结果、验收器和共享 memory 控制上下文污染。
- 不是追求完全自动化，而是把高风险决策留给主 agent 或用户确认。

可以把它理解成：

- LiteLLM 是 request router。
- tap 是 agent communication layer。
- Roo 是 IDE orchestrator。
- 本项目是 coding task cost router / orchestrator。

## Current Understanding

我们已经验证了一个关键前提：Codex custom subagent 可以使用与主 Codex 不同的 `model_provider`。

实测结果：

- Chat Completions-only API 可以被外部脚本或 OpenCode/Claude 类 harness 使用，但不能直接作为当前 Codex provider，因为 Codex 0.139.0 要求 `wire_api = "responses"`。
- Qwen vLLM endpoint 支持 `/v1/responses` 后，可以作为 Codex provider 使用。
- 主 Codex 使用默认 OpenAI provider 时，可以 spawn 一个配置了 `model_provider = "qwen_vllm"` 的 custom subagent。
- 该 subagent 能完成只读日志分析，并把摘要返回给主 Codex。

这说明“主 Codex + 便宜 Responses-compatible subagent”的内部降本路线是可行的。

同时，Codex subagent 与主 agent 之间并不会自动共享完整 memory。更准确地说，它们通过任务说明和最终摘要通信：主 agent 把必要上下文传给子 agent，子 agent 独立执行，再把 summary 回传主 agent。若要跨 subagent、跨 harness 共享事实、决策、失败尝试和成本记录，需要项目自己实现 shared memory。

## Design Direction

项目应坚持两条 backend 路线。

### Backend A: Codex Internal Subagent

这是最轻量、最顺滑的路线。

主 Codex 负责总控、判断、验收和最终输出；便宜模型通过 Codex custom subagent 承担只读探索、日志总结、代码搜索、初步 review 等任务。

适用情况：

- provider 支持 `/v1/responses`。
- 子任务能被限制为只读或低风险。
- 希望尽量复用 Codex 的 subagent、sandbox、approval 和 summary 机制。

价值：

- 不需要另起一个 agent harness。
- 用户体验接近原生 Codex。
- 可以在 Codex 内部完成“强主控 + 低成本 worker”的结构。

限制：

- 对 provider API 兼容性要求更高。
- 不自动共享完整 memory。
- 不会自动路由，仍需项目提供任务评估和调度逻辑。

### Backend B: External Harness

这是必要的第二条路线。

外部 backend 可以是 Claude Code、OpenCode、Aider、Roo Code 或其他 CLI/MCP/SDK agent。Codex 主控通过 CLI、MCP server 或文件协议把任务委托出去，外部 agent 返回结构化结果、patch、证据和成本信息。

必须支持这条路线的原因：

- 很多便宜 API 只支持 Chat Completions，不支持 Codex Responses provider。
- 不同模型在不同 harness 中工具适配、提示风格和执行稳定性不同。
- 用户可能已经有 Claude Code、OpenCode、Aider 等成熟工作流和额度。
- 长期看，多 agent harness 协同本身也有价值。

适用情况：

- provider 不能直接接入 Codex。
- 某个 harness 对特定模型或任务更强。
- 需要 worktree、容器、独立进程或更强隔离。

价值：

- 兼容面更广。
- 能利用各 harness 的最佳能力。
- 为未来跨 agent 协作、handoff 和 shared memory 打基础。

## Core Capabilities

### Task Router

Router 接收用户任务和当前上下文，判断：

- 任务难度：simple / medium / hard。
- 风险等级：read-only / patch / destructive / credential-sensitive。
- 上下文需求：是否需要读大量文件、日志、diff、测试输出。
- 可拆分性：是否能并行拆成独立子任务。
- 推荐 backend：Codex subagent、Claude Code、OpenCode、强主模型。
- 推荐模型和预算。

它不是简单 provider switching，而是 coding task 级别的调度。

### Delegator

Delegator 负责把子任务发送到具体 backend：

- Codex custom subagent。
- External CLI agent。
- MCP delegate server。
- 文件协议或 worktree worker。

它需要统一任务输入、权限边界、超时、预算和输出格式。

### Verifier

Verifier 负责判断便宜模型或外部 agent 的结果能不能用：

- 是否回答了任务。
- 是否有文件路径、命令、日志等证据。
- 是否越权或改了不该改的内容。
- 是否需要升级到强模型重做。
- 是否需要用户确认。

这是降本能否成立的关键：便宜 worker 只能降低成本，不能降低最终质量底线。

### Shared Memory

Shared memory 不等于 transcript 存档。它应该只存可复用、可引用、可过期的结构化信息：

- repo facts：项目结构、关键模块、常见命令、约定。
- task facts：本次任务发现、失败尝试、候选根因。
- decisions：已确认的方案和原因。
- cost ledger：每个子任务用了哪个 backend、多少 token、是否升级。
- evidence references：文件路径、日志行、命令摘要。

Memory 的目标是减少重复探索，而不是把上下文越塞越满。

### Hooks

Hook 不是独立卖点，但它是把系统嵌入现有 agent harness 的机制：

- pre-task：评估难度、预算、是否拆解。
- pre-delegate：选择 backend、模型、权限。
- post-delegate：抽取事实、写 memory、记录成本。
- post-verify：决定接受、重试、升级或请求用户确认。

## Overall Roadmap

### Phase 1: Codex-First Cost Routing

先围绕 Codex 做最小闭环：

- 一个主 Codex。
- 一个便宜 Codex subagent backend。
- 一个外部 CLI backend。
- 一个只读任务类型，例如日志总结、代码搜索、测试失败初诊。
- 一个 cost ledger。
- 一个 verifier。

目标不是功能多，而是证明同一个真实 coding task 里，路由后能降低主 Codex token 消耗，并且最终质量可接受。

### Phase 2: Dual Backend Stabilization

把 Codex internal subagent 和 external harness backend 都做成稳定接口。

这一阶段要重点解决：

- Responses-compatible provider 和 Chat Completions-only provider 的差异。
- Claude Code / OpenCode / Aider 等外部 harness 的输出规范。
- worktree 或临时目录隔离。
- 子任务超时、失败、重试和升级。
- 结构化 summary、patch、evidence 的统一格式。

### Phase 3: Shared Memory And Quality Loop

加入 repo-scoped memory 和质量反馈闭环。

系统应该开始学习：

- 哪类任务适合便宜模型。
- 哪类任务经常需要升级。
- 哪个 backend 在某个 repo 上最稳定。
- 哪些事实已经被验证，不需要反复探索。

这一阶段的目标是让路由策略越来越少依赖硬编码规则。

### Phase 4: Multi-Harness Collaboration

在降本之外，扩展到多 agent harness 协同。

此时项目不只是“省钱”，还可以成为一个统一协作层：

- Codex 负责主控和验收。
- Claude Code 负责复杂编辑或推理。
- OpenCode 负责低成本搜索、总结和局部实现。
- Aider/Roo 等负责特定工作流。
- shared memory 负责跨 agent 留痕和知识复用。

## Future Vision

如果这个方向跑通，未来可以成为一个轻量但有辨识度的开源项目：

> 给 coding agents 加一个成本感知的大脑，让它们知道什么时候该自己做，什么时候该派便宜 worker，什么时候该升级强模型，什么时候该把发现写进长期 memory。

可能的未来能力包括：

- 自动生成任务拆分图和成本估算。
- 按 repo 学习最优 backend 组合。
- 对比“强模型单独完成”和“路由完成”的成本与质量。
- 支持多 agent harness 的 handoff、review、receipt。
- 支持本地模型作为低成本探索 worker。
- 支持团队共享 memory 和路由策略。
- 支持 CI failure、日志排障、PR review、测试补全等固定场景模板。

这个项目的价值不在于重新发明 agent，也不在于重新发明 MCP，而在于把不同模型、不同 harness、不同成本层级组织成一个可控、可验收、可度量的 coding workflow。
