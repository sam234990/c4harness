# Delegator Module: Raw Research Ideas

**生成日期**: 2026-06-24
**基于**: landscape-delegator.md (18 papers, 8 gaps)

---

## Idea 1: BackendAdapter Protocol-Agnostic Harness Abstraction

- **Title**: BackendAdapter: A Protocol-Agnostic Abstraction Layer for Heterogeneous Agent Harness Delegation
- **Thesis**: 异构 agent harness（Codex 子 agent、Claude CLI、OpenCode CLI、MCP server）之间的核心差异可以被抽象为统一的 `BackendAdapter` trait，使 Delegator 无需感知底层协议细节即可调度任意后端。
- **Problem**: G1/G2 — 现有工作（ToolRegistry [P09]、Agent-as-Tool [P05]）仅统一了工具级调用，未涉及 harness 级的生命周期管理（进程启动/停止、配置生成、工作区隔离）。每个新后端的集成都需要手工定制。
- **Core mechanism**: 定义 `BackendAdapter` trait：`dispatch(task) -> Result`，每个后端实现此 trait。内部处理：(1) 协议适配（TOML 生成、CLI 子进程、MCP JSON-RPC）；(2) 进程生命周期管理；(3) 工作区隔离（worktree）。
- **Non-obvious reason**: ToolRegistry [P09] 已证明 RPC 本质可统一工具调用，但 harness 级统一涉及更多维度——配置生成、进程管理、错误恢复——这些维度的统一需要比 RPC stub 更丰富的抽象。
- **Contribution type**: 系统设计 + 开源实现
- **Risk**: 中 — 工程挑战大但技术路线清晰，风险在于不同后端的边界情况可能使抽象层过于复杂
- **Effort**: 高 — 需要实现多个后端 adapter 并处理大量边界情况
- **Closest work + delta**: ToolRegistry [P09]（工具级统一）→ 本工作扩展到 harness 级，增加进程生命周期管理和配置生成

---

## Idea 2: Attested Backend Capability Cards

- **Title**: Attested Capability Cards: Verified Backend Declarations for Trustworthy Delegation
- **Thesis**: 后端能力声明（支持的任务类型、模型、工具、成本、延迟）应通过实际执行数据验证，而非依赖后端自报——来源悖论 [P13] 证明自报质量不可靠。
- **Problem**: G4 — A2A 的 Agent Card [P04] 允许 agent 声明能力但无验证机制。Delegator 需要一种机制来声明、发现和验证后端能力，但现有工作未提供。
- **Core mechanism**: (1) 定义标准化的 Capability Card 格式；(2) 通过 cost ledger 中的历史执行数据计算经认证的能力分数；(3) 引入衰减机制——旧数据权重降低，防止能力漂移。
- **Non-obvious reason**: 来源悖论 [P13] 的核心洞察是：在自报系统中，最差的委派者会系统性地被选中。将此洞察迁移到后端能力声明，意味着 Delegator 必须基于经认证的执行数据而非后端声明做路由决策。
- **Contribution type**: 机制设计 + 实证验证
- **Risk**: 中 — 需要足够的执行数据才能建立可靠的能力画像，冷启动问题需要解决
- **Effort**: 中 — 核心是数据收集和统计建模，不需要复杂的系统设计
- **Closest work + delta**: Prakash [P13]（来源悖论 + 委派合约）→ 本工作将其具体化为后端能力卡片，并利用 cost ledger 作为认证数据源

---

## Idea 3: Structured Error Taxonomy for CLI-Based Delegation

- **Title**: Towards Robust CLI Delegation: A Structured Error Taxonomy and Recovery Framework
- **Thesis**: CLI 后端（`claude -p`、`opencode run`）的失败模式可以被系统化分类，并映射到自动化的恢复策略，使 Delegator 在后端失败时能智能降级而非盲目重试。
- **Problem**: G3 — 现有 CLI 后端以子进程方式调用，缺乏结构化错误码、超时管理、进度回报和优雅终止机制。P11 显示多步工具调用成功率仅 7-47%，P16 显示 MCP 任务成功率不足 50%。
- **Core mechanism**: (1) 定义错误分类体系：超时、崩溃、输出格式错误、能力不足、权限拒绝等；(2) 为每类错误定义恢复策略：重试、降级到其他后端、任务分解后重试、放弃并报告；(3) 引入 circuit breaker 模式防止对已知失败后端的无效重试。
- **Non-obvious reason**: 现有工作假设 agent 通信总是成功的 [P07, P08]，但实际数据表明后端失败是常态。将错误处理从"事后补充"提升为"一等公民"是 Delegator 设计的关键转变。
- **Contribution type**: 分类体系 + 工程框架
- **Risk**: 低 — 错误分类和恢复策略是成熟的工程实践，风险在于分类可能不够全面
- **Effort**: 中 — 需要大量实际执行数据来完善错误分类
- **Closest work + delta**: P11（揭示低成功率问题）→ 本工作提供系统化的错误分类和自动化恢复框架

---

## Idea 4: Unified Output Normalization Protocol

- **Title**: UnifiedOutput: A Normalization Protocol for Heterogeneous Agent Backend Results
- **Thesis**: 不同后端返回结果的格式差异可以通过统一的输出规范化协议消除，使 Delegator 的上层（cost ledger、router）无需感知后端特定的输出格式。
- **Problem**: G5 — Codex 子 agent 返回 agent 输出流，Claude CLI 返回 stdout/stderr，MCP server 返回 JSON-RPC 响应。没有统一的输出格式标准。
- **Core mechanism**: 定义统一输出格式：`{ status: Success|Failure|Partial, output: string, error: ErrorDetail, metadata: { tokens_used, latency_ms, model, backend_type } }`。每个 BackendAdapter 负责将后端特定输出转换为此格式。
- **Non-obvious reason**: 看似简单的格式统一实际上涉及深层语义映射——不同后端的"成功"和"失败"定义不同，输出粒度不同，元数据可用性不同。规范化不仅是格式转换，更是语义对齐。
- **Contribution type**: 协议规范 + 参考实现
- **Risk**: 低 — 技术路线清晰，风险在于格式设计可能过于刚性或过于灵活
- **Effort**: 低 — 核心是协议设计和几个 adapter 的实现
- **Closest work + delta**: ToolRegistry [P09]（RPC 结果序列化）→ 本工作扩展到 harness 级输出，增加语义状态和丰富元数据

---

## Idea 5: Async Delegation with Progress Callbacks

- **Title**: AsyncDelegator: Asynchronous Task Delegation with Progress Tracking for Long-Running Coding Tasks
- **Thesis**: 长时编码任务（数分钟到数小时）需要异步委派模式，支持进度回调、超时管理和取消操作，而非假设同步快速返回。
- **Problem**: G6 — 现有多 agent 通信工作假设同步交互 [P07, P08]，不处理长时任务。A2A [P04] 支持任务状态轮询但未被任何 harness 实现。
- **Core mechanism**: (1) 异步 dispatch 接口：`dispatch_async(task) -> DelegationHandle`；(2) 进度回调：后端定期报告进度百分比和当前状态；(3) 超时管理：可配置的硬超时和软超时（软超时触发警告，硬超时强制终止）；(4) 取消操作：支持优雅终止和强制终止。
- **Non-obvious reason**: 异步委派不仅是技术需求，更是成本优化的前提——只有支持异步，才能实现跨后端的并行委派和投机执行。
- **Contribution type**: 系统设计 + 实现
- **Risk**: 中 — 技术挑战在于不同后端的进度报告能力差异很大
- **Effort**: 中高 — 需要修改多个后端 adapter 以支持异步模式
- **Closest work + delta**: A2A [P04]（任务状态轮询）→ 本工作将其具体实现到实际的 agent harness 后端

---

## Idea 6: Cost-Aware Delegation Policy via RL

- **Title**: Learning Cost-Aware Delegation Policies for Heterogeneous Agent Backends
- **Thesis**: Delegator 的后端选择策略可以通过 RL 联合优化任务成功率和成本消耗，在异构后端的成本结构下找到最优委派策略。
- **Problem**: G7 — Uno-Orchestra [P15] 联合训练了分解和委派策略，但其"后端"是同一框架内的不同模型，不涉及异构 harness 的成本差异（token 成本、延迟、并发限制）。
- **Core mechanism**: (1) 定义状态空间：任务特征 + 后端能力画像 + 当前成本预算；(2) 动作空间：选择后端 + 是否分解任务；(3) 奖励函数：任务成功率 - λ * 标准化成本；(4) 使用 PPO/SAC 训练委派策略。
- **Non-obvious reason**: 异构后端的成本结构差异巨大（Codex 子 agent 按 token 计费、CLI 后端按调用次数计费、MCP server 可能有并发限制），这使得简单的启发式策略难以接近最优。
- **Contribution type**: 算法 + 实验
- **Risk**: 高 — 需要大量训练数据，且 RL 训练的稳定性和泛化性是挑战
- **Effort**: 高 — 需要构建训练环境、收集数据、训练和评估策略
- **Closest work + delta**: Uno-Orchestra [P15]（RL 联合训练）→ 本工作扩展到异构后端的成本结构，引入真实的成本约束

---

## Idea 7: Privilege-Minimal Backend Selection

- **Title**: Least-Privilege Delegation: Privilege-Aware Backend Selection for Safer Agent Systems
- **Thesis**: 后端选择应遵循最小权限原则——高风险操作优先选择受限后端，除非任务必须更高权限。这可以减少过度权限工具选择 [P10] 带来的安全风险。
- **Problem**: G8 — Yang et al. [P10] 证明 agent 倾向于选择过度权限的工具。在 Delegator 场景中，不同后端有不同的权限级别，但没有工作将权限最小化纳入后端选择。
- **Core mechanism**: (1) 为每个后端定义权限级别（文件系统读/写、网络访问、进程创建等）；(2) 为每个任务评估所需权限级别；(3) 后端选择时加入权限匹配约束：选择满足任务需求的最低权限后端。
- **Non-obvious reason**: 权限最小化不仅是安全原则，也是成本优化的隐含维度——低权限后端通常更轻量、更便宜、更快。
- **Contribution type**: 安全机制 + 实证分析
- **Risk**: 中 — 权限级别的定义可能过于粗糙，难以精确匹配任务需求
- **Effort**: 中 — 需要定义权限模型并在后端选择逻辑中实现
- **Closest work + delta**: Yang et al. [P10]（过度权限问题）→ 本工作将其解决方案迁移到 Delegator 的后端选择场景

---

## Idea 8: Delegation Contract Protocol

- **Title**: Delegation Contracts: Formalizing Task-Backend Agreements for Accountable Agent Routing
- **Thesis**: 每次委派应通过正式的"委派合约"进行，合约明确目标、预算、失败策略和输出格式要求，为跨后端审计提供结构化基础。
- **Problem**: Prakash [P13] 提出了委派合约的概念但未具体化。Delegator 需要一个可执行的合约格式来约束委派行为。
- **Core mechanism**: (1) 定义合约格式：`{ goal, budget: { tokens, time, cost }, failure_strategy: retry|fallback|abort, output_format, timeout }`；(2) BackendAdapter 在执行前验证合约可行性；(3) 执行过程中监控合约约束；(4) 违约时触发失败策略。
- **Non-obvious reason**: 委派合约不仅是约束机制，更是 Delegator 与后端之间的"接口契约"——它使 Delegator 的行为可预测、可审计、可调试。
- **Contribution type**: 协议设计 + 实现
- **Risk**: 低 — 合约格式设计是工程问题，风险在于合约可能过于复杂
- **Effort**: 低中 — 核心是格式设计和验证逻辑
- **Closest work + delta**: Prakash [P13]（委派合约概念）→ 本工作将其具体化为可执行的协议格式

---

## Idea 9: Provenance-Aware Delegation Audit Trail

- **Title**: DelegAudit: Cryptographic Audit Trails for Cross-Backend Task Delegation
- **Thesis**: 跨后端委派的完整链路（路由决策 → 后端选择 → 执行结果 → 成本消耗）应通过密码学方式记录，支持离线审计和不可篡改的溯源。
- **Problem**: 现有 Delegator 设计缺乏结构化的审计机制。HDP [P14] 提供了密码学委派链的参考，但未针对 agent 后端委派场景具体化。
- **Core mechanism**: (1) 每次委派生成签名记录：`{ delegation_id, task_hash, backend_id, timestamp, result_hash, cost }`；(2) 记录链式签名形成不可篡改的审计链；(3) 支持离线验证和完整性检查。
- **Non-obvious reason**: 审计不仅是合规需求，更是 Delegator 自我改进的数据基础——完整的审计数据可以用于训练更好的委派策略。
- **Contribution type**: 安全协议 + 实现
- **Risk**: 中低 — 密码学技术成熟，风险在于性能开销可能过大
- **Effort**: 中 — 需要设计签名方案并集成到 Delegator 流程中
- **Closest work + delta**: HDP [P14]（密码学委派链）→ 本工作将其扩展到 agent 后端委派场景，增加成本追踪

---

## Idea 10: Adaptive Fallback Chain for Backend Failures

- **Title**: ResilientDelegation: Adaptive Fallback Chains for Graceful Backend Failure Handling
- **Thesis**: Delegator 应维护一个动态的后端降级链（fallback chain），当首选后端失败时自动降级到次优后端，并根据历史失败数据自适应调整降级顺序。
- **Problem**: G3 — 后端失败是常态（成功率 7-50%），但现有设计缺乏系统化的降级机制。简单重试同一后端往往无效。
- **Core mechanism**: (1) 为每个任务类型维护后端优先级列表；(2) 引入 circuit breaker 模式：连续失败 N 次后标记后端为"断路"；(3) 降级链自适应：根据历史成功率和成本动态调整后端优先级；(4) 降级时自动调整任务格式以适配目标后端。
- **Non-obvious reason**: 降级不是简单的"换一个试试"——不同后端的能力和限制不同，降级时可能需要调整任务描述、分解任务、或放宽约束。智能降级本身就是一个决策问题。
- **Contribution type**: 算法 + 系统设计
- **Risk**: 中 — 降级策略的设计需要大量实验调优
- **Effort**: 中 — 需要实现 circuit breaker 和自适应优先级调整
- **Closest work + delta**: P11（低成功率问题）+ P13（失败策略）→ 本工作提供完整的自适应降级框架

---

## Idea 11: Task-Backend Affinity Learning

- **Title**: AffinityRouter: Learning Task-Backend Affinity from Execution History for Cost-Aware Delegation
- **Thesis**: 不同任务类型与不同后端之间存在可学习的"亲和性"（affinity），通过分析历史执行数据可以预测给定任务在各后端上的成功率和成本，从而实现数据驱动的后端选择。
- **Problem**: G7 — 现有委派策略要么是启发式的，要么在同一框架内训练 [P15]。Delegator 需要一种能从实际执行数据中学习任务-后端亲和性的方法。
- **Core mechanism**: (1) 从 cost ledger 中提取任务特征（复杂度、类型、代码语言）和执行结果（成功率、延迟、成本）；(2) 训练亲和性预测模型：给定任务特征，预测各后端的成功率和成本；(3) 使用 Thompson Sampling 或 UCB 平衡探索与利用；(4) 亲和性分数随新数据持续更新。
- **Non-obvious reason**: 亲和性不仅是"哪个后端更好"——它捕捉的是任务特征与后端能力之间的细粒度匹配关系。例如，简单 bug fix 可能在轻量后端上性价比最高，而复杂重构可能需要最强后端。
- **Contribution type**: 机器学习 + 系统设计
- **Risk**: 中高 — 需要足够的执行数据，且特征工程是关键
- **Effort**: 中高 — 需要构建特征提取管道、训练模型、集成到 Delegator
- **Closest work + delta**: Uno-Orchestra [P15]（选择性委派）→ 本工作从实际执行数据中学习，而非在模拟环境中训练

---

## Idea 12: Speculative Parallel Delegation

- **Title**: SpecDeleg: Speculative Parallel Delegation for Latency-Optimal Agent Backend Selection
- **Thesis**: 对于高优先级任务，可以将同一任务同时发送到多个后端（投机执行），使用最先返回的成功结果，以延迟换成本。
- **Problem**: 现有 Delegator 设计是串行的——选择一个后端，等待结果，失败再尝试下一个。这在延迟敏感场景下不是最优的。
- **Core mechanism**: (1) 任务到达时，根据亲和性分数选择 top-K 后端；(2) 并行发送任务到 K 个后端；(3) 使用第一个成功返回的结果，取消其余；(4) 根据任务优先级和成本预算动态调整 K 值。
- **Non-obvious reason**: 投机执行看似浪费资源，但在后端成功率低（7-50%）的场景下，串行重试的总成本可能高于并行投机。这是一个反直觉的成本-延迟权衡。
- **Contribution type**: 算法 + 实验
- **Risk**: 高 — 并行执行的资源消耗和协调复杂度是主要挑战
- **Effort**: 高 — 需要实现并行调度、取消机制和成本追踪
- **Closest work + delta**: Yuan et al. [P05]（并行子任务编排）→ 本工作将并行思想应用到同一任务的多后端投机执行

---

*共生成 12 个研究想法，覆盖 G1-G8 所有识别的研究空白。*
