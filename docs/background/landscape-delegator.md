# Literature Landscape: Delegator / Backend Module for Cost-Aware Coding-Agent Routing

**Date**: 2026-06-23
**Papers analyzed**: 18
**Sources**: 用户指定论文列表 + arXiv 检索 (3 queries) + WebSearch
**模块定位**: cost-aware coding-agent router 中的 Delegator / Backend 子模块

---

## Executive Summary

Delegator / Backend 是 cost-aware coding-agent router 的执行层：给定 Task Router 做出的路由决策（目标后端、任务描述、约束条件），Delegator 负责将任务实际分发到正确的后端执行，并收集结构化的执行结果。当前系统有两个已实现的后端：(1) Codex 内部子 agent——生成自定义 agent TOML，调用 `codex exec` 并指定不同 model_provider；(2) 外部 CLI 后端——以子进程方式调用 `claude -p` 或 `opencode run`。未来可能扩展到 MCP delegate server、基于 worktree 的可写任务、Aider、Roo/Cline 等后端。

这一问题在学术文献中处于三个研究领域的交叉地带：**多 agent 通信协议**（multi-agent communication protocols）、**任务委派与编排**（task delegation & orchestration）、以及**工具抽象与 API 统一**（tool abstraction & API unification）。

文献分析揭示了以下关键发现：

1. **多 agent 通信已从自然语言演进到结构化协议**。ChatDev [P07] 和 MetaGPT [P08] 用自然语言/结构化文档作为 agent 间通信载体，而 2025-2026 年的 A2A 协议 [P04] 和 MCP [P16, P17, P18] 正在建立标准化的 agent-to-agent 和 agent-to-tool 通信层。然而，这些协议聚焦于同一框架内的 agent 交互，**不解决异构 harness 之间的任务委派问题**。

2. **任务委派正在从静态编排走向学习型选择性委派**。Shen et al. [P01] 的 planner-caller-summarizer 分解、Yuan et al. [P05] 的 Agent-as-Tool 并行编排、以及 Cui et al. [P15] 的 Uno-Orchestra 选择性委派，展示了从固定流水线到自适应委派策略的演进。但这些工作都在单一框架内运行，不涉及跨 harness 委派。

3. **委派的信任与问责成为新兴关注点**。Prakash [P13] 揭示了"来源悖论"（provenance paradox）——基于自报质量的路由会系统性地选择最差的委派者；Dalugoda [P14] 提出了密码学委派溯源协议 HDP。这些工作对 Delegator 的设计有直接启示：需要验证后端的实际能力而非依赖声明。

4. **工具/后端抽象层缺乏统一标准**。ToolRegistry [P09] 提出了协议无关的工具管理，MCP [P16-P18] 建立了 agent-to-tool 的标准接口，但**没有一个抽象层能统一 Codex 子 agent、Claude CLI、OpenCode CLI 等异构后端**。Delegator 需要填补这一空白。

本报告分析 18 篇关键论文，识别出 4 个主题和 8 个研究空白，为 Delegator / Backend 模块的设计提供文献基础。

---

## Paper Table

| ID | Paper | Authors | Year | Venue | Method | Key Result | Relevance |
|----|-------|---------|------|-------|--------|------------|-----------|
| P01 | Small LLMs Are Weak Tool Learners: A Multi-LLM Agent | Shen et al. | 2024 | arXiv:2401.07324 (preprint) | 将 tool use 分解为 planner/caller/summarizer 三个角色，每个角色用独立 LLM 实现 | 多 LLM 框架在 tool-use 基准上超越单 LLM 方法，小模型组合可接近大模型性能 | **高** — 角色分解思想直接对应 Delegator 的"路由决策 → 后端调用 → 结果汇总"流程 |
| P02 | Context Engineering for Multi-Agent LLM Code Assistants | Haseeb | 2025 | arXiv:2508.08322 (preprint) | 多 harness 协作：Intent Translator + Elicit 检索 + NotebookLM + Claude Code sub-agent | 多 agent 系统在真实代码库上实现高单次成功率，优于单 agent 基线 | **高** — 直接展示了多 harness 协作的实践模式 |
| P03 | Towards Effective GenAI Multi-Agent Collaboration | Shu et al. | 2024 | arXiv:2412.05449 (preprint) | 评估 coordination（并行通信+payload 引用）和 routing（消息转发）两种模式 | 多 agent 协作比单 agent 提升 70% 目标成功率；routing 机制可显著降低延迟 | **高** — coordination/routing 双模式设计可映射到 Delegator 的同步/异步委派模式 |
| P04 | Modality-Native Routing in A2A Networks | Srinivasan | 2026 | arXiv:2604.12213 (preprint) | MMA2A：基于 Agent Card 能力声明的模态原生路由，保留语音/图像/文本原始模态 | 模态原生路由比文本瓶颈基线提升 20pp 任务准确率，但需下游 agent 能利用丰富上下文 | **高** — 路由是"一阶设计变量"的结论直接支持 Delegator 的核心设计哲学 |
| P05 | Small Model as Master Orchestrator | Yuan et al. | 2026 | arXiv:2604.17009 (preprint) | Agent-as-Tool 范式：将 agent 和工具统一为标准化可学习动作空间，轻量编排器 ParaManager 做并行子任务分解 | ParaManager 在多个基准上表现强劲，对未见过的模型池有鲁棒泛化能力 | **高** — Agent-as-Tool 的协议标准化思想可直接用于 Delegator 的后端统一接口 |
| P06 | Code as Agent Harness | Ning et al. | 2026 | arXiv:2605.18747 (preprint) | 综述：代码作为 agent 基础设施的三层架构（harness interface, mechanisms, scaling） | 系统梳理了 code agent 的架构模式，涵盖单 agent 到多 agent 的扩展路径 | **高** — 提供了 Delegator 需要对接的各类 agent harness 的分类框架 |
| P07 | ChatDev: Communicative Agents for Software Development | Qian et al. | 2023 | arXiv:2307.07924 (preprint) | Chat chain：将软件开发分解为有序对话链，agent 通过多轮自然语言对话协作 | 展示了语言通信作为 agent 协作统一桥梁的可行性 | **中** — chat chain 模式可作为 Delegator 的简单同步委派参考 |
| P08 | MetaGPT: Meta Programming for Multi-Agent Collaborative Framework | Hong et al. | 2023 | arXiv:2308.00352 (preprint) | SOP 编码为 prompt 序列，结构化文档（PRD、设计文档、代码）作为 agent 间通信载体 | 在协作软件工程基准上生成比 chat-based 系统更连贯的解决方案 | **中高** — 结构化文档通信模式可作为 Delegator 任务描述格式的参考 |
| P09 | ToolRegistry: A Protocol-Agnostic Tool Management Library | Ding & Stevens | 2025 | arXiv:2507.10593 (preprint) | 统一 Tool 对象作为通用 RPC stub，registry 作为 RPC 客户端运行时，支持线程/进程后端 | 集成代码减少 60-80%，选择正确的并发模式可提升 3.1x 吞吐量 | **高** — 协议无关的工具抽象思想可直接用于 Delegator 的后端统一接口设计 |
| P10 | When Lower Privileges Suffice: Over-Privileged Tool Selection in LLM Agents | Yang et al. | 2026 | arXiv:2606.20023 (preprint) | 研究 agent 选择过高权限工具的问题，提出 ToolPrivBench 和权限感知后训练防御 | 过度权限工具选择在主流 LLM agent 中普遍存在，且被瞬态故障放大 | **中** — 提醒 Delegator 需要考虑后端权限级别匹配 |
| P11 | Live API-Bench: 2500+ Live APIs for Testing Multi-Step Tool Calling | Elder et al. | 2025 | arXiv:2506.11266 (preprint) | 将 NL2SQL 数据集转换为交互式 API 环境，评估多步工具调用能力 | SOTA LLM 任务完成率仅 7-47%，交互式 agent 设置下提升至 50% | **中** — 多步工具调用的低成功率揭示了 Delegator 需要处理的后端失败场景 |
| P12 | Task-Aware Delegation Cues for LLM Agents | Gu | 2026 | arXiv:2603.11011 (preprint) | 任务感知的协作信号层：Capability Profiles + Coordination-Risk Cues 驱动闭环委派协议 | 任务分类携带可操作结构，集群特征改善胜者预测准确率 | **中高** — 能力画像和风险信号的设计思路可迁移到 Delegator 的后端能力匹配 |
| P13 | The Provenance Paradox in Multi-Agent LLM Routing | Prakash | 2026 | arXiv:2603.18043 (preprint) | LDP 扩展：委派合约（目标、预算、失败策略）+ 声称 vs 经认证身份模型 | 基于自报质量的路由比随机选择更差；经认证路由接近最优（d=9.51, p<0.001） | **高** — 来源悖论直接警示 Delegator 不能依赖后端自报能力 |
| P14 | HDP: A Lightweight Cryptographic Protocol for Human Delegation Provenance | Dalugoda | 2026 | arXiv:2604.04522 (preprint) | 轻量 token 方案：Ed25519 签名的委派链，离线验证，无需注册中心 | 已发布为 IETF Internet-Draft，提供 TypeScript SDK 参考实现 | **中** — 密码学委派链为 Delegator 的跨后端审计提供了安全设计参考 |
| P15 | Uno-Orchestra: Parsimonious Agent Routing via Selective Delegation | Cui et al. | 2026 | arXiv:2605.05007 (preprint) | 统一编排策略：选择性分解 + 分派到 (model, primitive) 对，RL 联合训练 | 77.0% macro pass@1，比最强基线高 16%，成本低一个数量级 | **高** — 选择性委派与联合优化的思路可直接用于 Delegator 的策略设计 |
| P16 | MCP-Universe: Benchmarking LLMs with Real-World MCP Servers | Luo et al. | 2025 | arXiv:2508.14704 (preprint) | 首个 MCP 综合基准：6 核心领域、11 MCP 服务器、执行级评估器 | GPT-5 仅 43.72%、Claude-4.0-Sonnet 29.44%，MCP 任务仍极具挑战性 | **中** — MCP 的低成功率表明 MCP delegate server 后端需要强大的错误处理 |
| P17 | MCPToolBench++: Large Scale MCP Tool Use Benchmark | Fan et al. | 2025 | arXiv:2508.07575 (preprint) | 4000+ MCP 服务器、40+ 类别的大规模基准，涵盖单步和多步工具调用 | 真实 MCP 工具的成功率不保证，且上下文窗口限制了可用工具数量 | **中** — MCP 工具成功率的不确定性对 Delegator 的 MCP 后端设计有直接影响 |
| P18 | MCP Tool Descriptions Are Smelly! | Hasan et al. | 2026 | arXiv:2602.14878 (preprint) | 对 856 个 MCP 工具的描述质量实证分析，识别 6 类描述 smell | 97.1% 工具描述至少含一种 smell；增强描述提升 5.85pp 成功率但增加 67.46% 执行步骤 | **中** — 工具描述质量直接影响 Delegator 对 MCP 后端的调用效果 |

---

## Thematic Analysis

### Theme 1: 多 Agent 通信协议的演进（Evolution of Multi-Agent Communication Protocols）

**Status**: active（2023-2026 年从自然语言到标准化协议快速演进）
**Dominant approach**: 从 chat chain / 结构化文档 → 标准化协议（MCP, A2A）
**Papers**: P07, P08, P03, P04, P16, P17, P18

多 agent 系统的通信模式经历了三个阶段。**第一阶段（2023）**：ChatDev [P07] 用 chat chain 将软件开发分解为有序的自然语言对话链，MetaGPT [P08] 则引入结构化文档（PRD、设计文档、代码）作为 agent 间通信载体。这两种方式都假设所有 agent 在同一框架内运行，通信协议内嵌于框架之中。

**第二阶段（2024-2025）**：Shu et al. [P03] 在企业场景中评估了 coordination（并行通信+payload 引用）和 routing（消息转发）两种多 agent 协作模式，发现 routing 机制可显著降低延迟。这一发现直接启示了 Delegator 的设计：当后端能力明确时，应支持"直通路由"（bypass orchestration overhead）。

**第三阶段（2025-2026）**：标准化协议开始主导。MCP（Model Context Protocol）建立了 agent-to-tool 的标准接口 [P16-P18]，Google 的 A2A 协议定义了 agent-to-agent 的任务委派标准 [P04]。Srinivasan [P04] 证明了路由是一阶设计变量——模态原生路由比文本瓶颈基线提升 20pp 任务准确率。然而，MCP 的实际表现仍不理想：MCP-Universe [P16] 测试中 GPT-5 仅 43.72% 成功率，且 97.1% 的 MCP 工具描述存在质量问题 [P18]。

对 Delegator 的启示：(1) 通信协议正在标准化，Delegator 应设计为协议无关的——内部使用统一接口，对外适配 MCP、A2A、CLI 等不同协议；(2) routing 是一阶设计变量 [P04]，Delegator 的后端选择策略直接影响下游任务成功率；(3) MCP 后端目前可靠性不足，需要强大的降级和重试机制。

### Theme 2: 任务委派与选择性编排（Task Delegation & Selective Orchestration）

**Status**: rapidly evolving（2024-2026 年从固定流水线到学习型委派）
**Dominant approach**: 从 planner-caller-summarizer 分解 → Agent-as-Tool 统一抽象 → RL 训练的选择性委派
**Papers**: P01, P05, P15, P03

任务委派的核心问题是：**何时委派、委派给谁、如何委派**。Shen et al. [P01] 最早将 tool use 能力分解为 planner（规划）、caller（调用）、summarizer（总结）三个角色，每个角色用独立 LLM 实现。这一分解思想直接对应 Delegator 的工作流程：路由决策（planner）→ 后端调用（caller）→ 结果汇总（summarizer）。

Yuan et al. [P05] 提出了更具雄心的 Agent-as-Tool 范式：将 agent 和外部工具统一抽象为标准化的可学习动作空间，通过协议标准化和显式状态反馈实现并行子任务编排。他们的 ParaManager 编排器用小模型实现，在复杂任务上接近大模型性能。这一思想对 Delegator 的核心启示是：**后端（Codex 子 agent、Claude CLI、OpenCode CLI 等）应该被抽象为统一的"tool"接口**，Delegator 通过这一统一接口调度所有后端。

Cui et al. [P15] 的 Uno-Orchestra 将选择性委派推向新高度：不仅决定委派给谁，还决定是否需要分解任务。通过 RL 联合训练分解策略和委派策略，Uno-Orchestra 在 13 个基准上达到 77.0% macro pass@1，比最强基线高 16%，成本低一个数量级。这直接验证了 Delegator 设计中"分解与委派联合优化"的价值。

对 Delegator 的启示：(1) planner-caller-summarizer 三角色分解 [P01] 可映射到 Delegator 的内部架构；(2) Agent-as-Tool [P05] 的统一抽象思想是 Delegator 后端接口设计的核心参考；(3) 选择性委派 [P15] 的 RL 训练范式可用于优化 Delegator 的后端选择策略。

### Theme 3: 工具抽象与后端统一（Tool Abstraction & Backend Unification）

**Status**: emerging（2025-2026 年开始出现协议无关的工具管理方案）
**Dominant approach**: 统一 Tool 对象 + 协议适配层 + 可插拔执行后端
**Papers**: P09, P05, P06, P02

Delegator 面临的核心工程挑战是：**如何在统一接口下管理异构后端**。Ding & Stevens [P09] 的 ToolRegistry 直接回应了这一挑战——他们观察到每个 LLM 工具调用在结构上都是 RPC（函数名 + JSON 参数 + 序列化结果），但每个协议（原生 Python、MCP、OpenAPI、LangChain）都需要从头集成。ToolRegistry 通过一个通用 Tool 对象作为 RPC stub，支持可插拔的线程/进程后端，将集成代码减少 60-80%。

Ning et al. [P06] 的综述从更高层面梳理了 code agent 的架构模式，将 agent harness 定义为三层架构：harness interface（连接推理、动作和环境建模）、harness mechanisms（规划、记忆、工具使用）、harness scaling（从单 agent 到多 agent 扩展）。这一分类框架帮助我们定位 Delegator 在 harness 架构中的位置——它处于 harness interface 层，负责将上层决策转化为对具体 harness 的调用。

Haseeb [P02] 的实践展示了多 harness 协作的真实模式：Intent Translator（GPT-5）+ Elicit 检索 + NotebookLM 文档合成 + Claude Code sub-agent 代码生成。这一系统证明了异构 harness 协作的可行性，但也暴露了当前的局限——每个 harness 的集成都是手工定制的，缺乏统一抽象。

对 Delegator 的启示：(1) ToolRegistry [P09] 的"RPC 本质显式化"思想可直接用于 Delegator 的后端接口设计——每个后端调用本质上都是"函数名 + 参数 + 结果"；(2) 但 Delegator 的挑战比 ToolRegistry 更大：它需要处理的不仅是 API 调用差异，还有进程生命周期管理（CLI 后端）、配置生成（Codex 子 agent TOML）、以及工作区隔离（worktree）；(3) Agent-as-Tool [P05] 的协议标准化可作为 Delegator 后端接口规范的参考。

### Theme 4: 委派信任、问责与安全（Delegation Trust, Accountability & Safety）

**Status**: emerging（2026 年刚开始出现针对 LLM agent 委派的信任研究）
**Dominant approach**: 委派合约 + 经认证身份 + 密码学溯源
**Papers**: P13, P14, P12, P10

当 Delegator 将任务委派给后端时，面临一个根本性信任问题：**如何验证后端的实际能力而非依赖其声明**。Prakash [P13] 揭示了"来源悖论"（provenance paradox）：在多 agent LLM 系统中，当委派者可以夸大自报质量分数时，基于质量的路由会系统性地选择最差的委派者，表现甚至比随机选择更差。他们通过 LDP（LLM Delegate Protocol）扩展引入了委派合约（delegation contracts）——通过明确的目标、预算和失败策略约束委派权限，以及经认证身份模型区分自报质量和验证质量。经认证路由接近最优性能（d=9.51, p<0.001）。

Dalugoda [P14] 从密码学角度解决委派问责问题，提出了 HDP（Human Delegation Provenance）协议——一个轻量 token 方案，用 Ed25519 签名记录委派链的每一跳，支持完全离线验证。这一协议已发布为 IETF Internet-Draft，为跨 agent 系统的审计提供了标准化基础。

Gu [P12] 从人机协作角度研究委派信号，提出了任务感知的协作信号层：Capability Profiles（任务条件化的胜率图）和 Coordination-Risk Cues（任务条件化的分歧先验）。这些信号驱动闭环委派协议，支持共同基础验证、自适应路由和隐私保护的问责日志。

Yang et al. [P10] 则从安全角度揭示了过度权限工具选择的问题：agent 倾向于选择高权限工具，即使低权限工具已足够，且瞬态故障会放大这一倾向。这对 Delegator 的启示是：后端选择不仅应考虑能力匹配，还应考虑权限最小化原则。

对 Delegator 的启示：(1) 来源悖论 [P13] 警示 Delegator 不能依赖后端自报能力——需要基于实际执行数据（cost ledger）的经认证路由；(2) 委派合约 [P13] 的设计（目标、预算、失败策略）可直接映射到 Delegator 的任务描述格式；(3) HDP [P14] 的密码学溯源为跨后端审计提供了安全设计参考；(4) 权限最小化 [P10] 应成为 Delegator 后端选择的约束条件。

---

## Gap Identification Matrix

| Gap ID | Gap Description | Evidence (papers) | Gap Type | Confidence |
|--------|----------------|-------------------|----------|------------|
| G1 | **无跨 harness 任务委派标准协议**：A2A [P04] 定义了 agent-to-agent 协议，MCP [P16] 定义了 agent-to-tool 协议，但两者都不解决"将任务从一个 agent harness 委派到另一个异构 harness"的问题。Delegator 需要的不是 agent-to-agent 对话，而是 harness-to-harness 的结构化任务传递。 | P04 (A2A 聚焦同协议 agent), P16 (MCP 聚焦 tool 调用), P06 (harness 分类但无跨 harness 协议) | overlooked formulation | HIGH |
| G2 | **异构后端缺乏统一抽象层**：ToolRegistry [P09] 统一了工具调用协议，但不涉及 agent harness 的生命周期管理（进程启动/停止、配置生成、工作区隔离）。没有一个抽象层能统一 Codex 子 agent（TOML 配置 + `codex exec`）、Claude CLI（`claude -p` 子进程）、OpenCode CLI（`opencode run` 子进程）等异构后端。 | P09 (工具级统一但非 harness 级), P02 (多 harness 协作但手工集成), P05 (Agent-as-Tool 但未涉及 CLI 后端) | cross-domain transfer | HIGH |
| G3 | **子进程委派缺乏结构化错误处理**：现有 CLI 后端（`claude -p`, `opencode run`）以子进程方式调用，缺乏结构化的错误码、超时管理、进度回报和优雅终止机制。P11 显示多步工具调用成功率仅 7-47%，P16 显示 MCP 任务成功率不足 50%，表明后端失败是常态而非异常。 | P11 (低成功率), P16 (MCP 低成功率), P07/P08 (假设 agent 通信总是成功的) | missing diagnostic | HIGH |
| G4 | **后端能力声明与验证机制缺失**：A2A 的 Agent Card [P04] 允许 agent 声明能力，但没有验证机制。来源悖论 [P13] 证明自报质量不可靠。Delegator 需要一种机制来声明、发现和验证后端能力（支持的任务类型、模型、工具、成本、延迟），但现有工作未提供这一机制。 | P04 (Agent Card 无验证), P13 (来源悖论), P12 (能力画像但面向人机协作) | overlooked formulation | HIGH |
| G5 | **无跨后端统一输出格式标准**：不同后端返回结果的格式、粒度和元数据完全不同——Codex 子 agent 返回 agent 输出流，Claude CLI 返回 stdout/stderr，MCP server 返回 JSON-RPC 响应。Delegator 需要一个统一的输出格式来标准化所有后端的结果，但现有工作未定义这一格式。 | P09 (ToolRegistry 的结果序列化但仅限工具级), P03 (payload 引用但仅限 coordination 模式) | overlooked formulation | HIGH |
| G6 | **长时任务的异步委派与状态追踪缺失**：现有多 agent 通信工作 [P07, P08] 假设同步交互，不处理需要数分钟甚至数小时的长时编码任务。A2A [P04] 支持任务状态轮询和推送通知，但尚未被任何 agent harness 实现。Delegator 需要支持异步委派、进度回调和超时管理。 | P07/P08 (同步假设), P04 (A2A 支持但未实现), P15 (Uno-Orchestra 假设快速返回) | overlooked formulation | MEDIUM-HIGH |
| G7 | **委派策略与成本优化未联合训练**：Uno-Orchestra [P15] 联合训练了分解和委派策略，但其"后端"是同一框架内的不同模型，不涉及异构 harness 的成本差异（token 成本、延迟、并发限制）。Delegator 需要在异构后端的成本结构下优化委派策略，但缺乏训练数据和基准。 | P15 (联合训练但同框架), P01-P06 (路由器与执行解耦) | untested assumption | HIGH |
| G8 | **权限最小化在后端选择中未被考虑**：Yang et al. [P10] 证明 agent 倾向于选择过度权限的工具。在 Delegator 场景中，不同后端有不同的权限级别（main_agent 有完整文件系统访问，codex_subagent 可能受限，CLI 后端的权限取决于配置）。没有工作将权限最小化原则纳入后端选择决策。 | P10 (过度权限问题), P14 (HDP 的权限范围但未涉及后端选择) | cross-domain transfer | MEDIUM |

---

## 与 Delegator 设计的映射

基于上述分析，Delegator / Backend 模块的设计可以借鉴以下技术路线：

| Delegator 能力 | 借鉴来源 | 实现思路 |
|----------------|---------|---------|
| 后端统一接口 | P09 (ToolRegistry), P05 (Agent-as-Tool) | 定义 `BackendAdapter` trait：`dispatch(task) -> Result`，每个后端实现此 trait，内部处理协议差异（TOML 生成、CLI 子进程、MCP 调用） |
| 任务描述格式 | P08 (MetaGPT 结构化文档), P13 (委派合约) | 任务描述包含：目标、约束、预算（token/时间）、失败策略、输出格式要求 |
| 同步/异步委派 | P03 (coordination/routing 双模式), P04 (A2A 任务状态) | 支持同步阻塞模式（简单任务）和异步轮询模式（长时任务），统一进度回调接口 |
| 后端能力发现 | P04 (Agent Card), P12 (Capability Profiles) | 每个后端声明能力卡片：支持的任务类型、模型列表、工具列表、成本结构、延迟特征 |
| 委派结果标准化 | P09 (RPC 结果序列化) | 统一输出格式：`{ status, output, error, metadata: { tokens_used, latency_ms, model } }` |
| 错误处理与降级 | P13 (失败策略), P11 (低成功率) | 结构化错误码 + 自动重试 + 后端降级链（如 MCP 失败则回退到 CLI） |
| 委派审计与溯源 | P14 (HDP), P13 (问责日志) | 记录每次委派的完整链路：路由决策 → 后端选择 → 执行结果 → 成本消耗 |
| 权限感知委派 | P10 (权限最小化) | 后端选择时考虑权限级别：高风险操作优先选择受限后端，除非任务必须更高权限 |

---

## References

```
[P01]  Shen, W., Li, C., Chen, H., Yan, M., Quan, X., Chen, H., Zhang, J., &
       Huang, F. (2024). Small LLMs Are Weak Tool Learners: A Multi-LLM Agent.
       arXiv:2401.07324.

[P02]  Haseeb, M. (2025). Context Engineering for Multi-Agent LLM Code Assistants
       Using Elicit, NotebookLM, ChatGPT, and Claude Code. arXiv:2508.08322.

[P03]  Shu, R., Das, N., Yuan, M., Sunkara, M., & Zhang, Y. (2024). Towards
       Effective GenAI Multi-Agent Collaboration: Design and Evaluation for
       Enterprise Applications. arXiv:2412.05449.

[P04]  Srinivasan, V. (2026). Modality-Native Routing in Agent-to-Agent Networks:
       A Multimodal A2A Protocol Extension. arXiv:2604.12213.

[P05]  Yuan, W., Xiong, W., Yu, F., Tang, S., Liu, T., Chen, T., Ye, P., Fu, Y.,
       Ouyang, W., & Bai, L. (2026). Small Model as Master Orchestrator: Learning
       Unified Agent-Tool Orchestration with Parallel Subtask Decomposition.
       arXiv:2604.17009.

[P06]  Ning, X., Tieu, K., Fu, D., et al. (2026). Code as Agent Harness.
       arXiv:2605.18747.

[P07]  Qian, C., Liu, W., Liu, H., et al. (2023). ChatDev: Communicative Agents
       for Software Development. arXiv:2307.07924.

[P08]  Hong, S., Zhuge, M., Chen, J., et al. (2023). MetaGPT: Meta Programming
       for A Multi-Agent Collaborative Framework. arXiv:2308.00352.

[P09]  Ding, P. & Stevens, R. (2025). ToolRegistry: A Protocol-Agnostic Tool
       Management Library for Function-Calling LLMs. arXiv:2507.10593.

[P10]  Yang, K., Bu, Y., Yi, J., et al. (2026). When Lower Privileges Suffice:
       Investigating Over-Privileged Tool Selection in LLM Agents.
       arXiv:2606.20023.

[P11]  Elder, B., Murthi, A., Kang, J., et al. (2025). Live API-Bench: 2500+ Live
       APIs for Testing Multi-Step Tool Calling. arXiv:2506.11266.

[P12]  Gu, X. (2026). Task-Aware Delegation Cues for LLM Agents.
       arXiv:2603.11011.

[P13]  Prakash, S. (2026). The Provenance Paradox in Multi-Agent LLM Routing:
       Delegation Contracts and Attested Identity in LDP. arXiv:2603.18043.

[P14]  Dalugoda, A. (2026). HDP: A Lightweight Cryptographic Protocol for Human
       Delegation Provenance in Agentic AI Systems. arXiv:2604.04522.

[P15]  Cui, Z., Xie, H., Yuan, J., et al. (2026). Uno-Orchestra: Parsimonious
       Agent Routing via Selective Delegation. arXiv:2605.05007.

[P16]  Luo, Z., Shen, Z., Yang, W., et al. (2025). MCP-Universe: Benchmarking
       Large Language Models with Real-World Model Context Protocol Servers.
       arXiv:2508.14704.

[P17]  Fan, S., Ding, X., Zhang, L., & Mo, L. (2025). MCPToolBench++: A Large
       Scale AI Agent Model Context Protocol MCP Tool Use Benchmark.
       arXiv:2508.07575.

[P18]  Hasan, M. M., Li, H., Rajbahadur, G. K., Adams, B., & Hassan, A. E. (2026).
       Model Context Protocol (MCP) Tool Descriptions Are Smelly! Towards Improving
       AI Agent Efficiency with Augmented MCP Tool Descriptions. arXiv:2602.14878.
```

---

*本文档为 Delegator / Backend 模块的文献基础，后续设计决策应参考上述空白分析（尤其是 G1-G5）来确保创新性。关键设计原则：(1) 后端接口应协议无关但 harness 感知；(2) 委派策略应基于经认证的执行数据而非后端自报能力；(3) 错误处理应是 Delegator 的一等公民而非事后补充。*
