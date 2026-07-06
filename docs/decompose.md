# C4 Task Decomposition and Assignment Method

**Status**: method design draft
**Date**: 2026-07-05
**Scope**: C4 / C4Harness 中的任务理解、契约式拆解、worker 分配、验证计划与受反馈驱动的重规划

本文提出 C4 的默认拆解方法 **C4-ACD（Adaptive Contract Decomposition，自适应契约式拆解）**。Decompose 的职责不是运行完整 multi-agent 系统，而是把经过必要 grounding 的用户任务转换为一份可执行、可分配、可验证、可重规划的计划。

系统如何启动 worker、执行验证、保存运行状态和向用户收口，分别属于 Delegator、Verifier、Memory/History 与 Application。本文只定义 Decompose 自己的算法和这些模块之间的契约。

## 1. 模块定位与设计目标

### 1.1 要解决的问题

C4 不能只把用户最后一句 prompt 切成若干字符串。真实 coding task 的边界同时取决于：

- 用户目标、补充要求、明确禁止事项和验收期望。
- 当前是普通任务、Skill workflow 还是 Plan Mode。
- 仓库结构、相关文件、日志、测试和运行环境。
- 可用 worker 的模型、harness、工具、模态、权限和上下文能力。
- 输入数据分类、外部信任域、用户授权范围和宿主强制策略。
- worker 在相似任务上的历史验证结果，而非模型自报能力。

因此，C4 拆解的输入是经过最小充分 grounding 的 `TaskSituation`，输出是 `DecompositionPlan`，其中包含任务契约图、worker assignment、节点级 verifier plan 和有界重规划策略。

### 1.2 Decompose 的输入与输出

```text
Inputs
  user request and interaction mode
  active Skill workflow
  minimal repository/environment facts
  worker capability manifests
  historical capability evidence
  security and user policy
                  ↓
             C4-ACD
                  ↓
Outputs
  TaskSituation
  RootContract
  TaskContractGraph
  WorkerAssignmentPlan
  VerifierPlan per node
  SecurityRiskManifest per external assignment
  BoundedReplanPolicy
```

### 1.3 核心原则

1. **先理解任务，再拆解**：只收集支持拆解决策所需的最小上下文。
2. **先定义完成，再定义工作**：Root Contract 和节点验收条件先于执行。
3. **拆解与分配联合考虑**：无法找到合格 worker 或 verifier 的节点不是有效拆解。
4. **每个节点都是契约**：同时声明目标、输入、产物、能力、权限和验证计划。
5. **硬能力先过滤，软能力再比较**：多模态、工具、权限等不满足时直接排除。
6. **验证由拆解阶段设计、Verifier 执行**：Decompose 不自己运行测试或接受结果。
7. **反馈可以改变任务图**：失败归因后可补上下文、换 worker 或继续拆分。
8. **简单任务保持简单**：能由一个 worker 完成时使用 fast path。
9. **选择理由可解释**：保留候选、排除原因、评分证据和不确定性。
10. **授权晚绑定**：provider、路径、操作和 callback 明确后才汇总风险并请求授权。

### 1.4 模块边界

Decompose 负责：

- 构建 TaskSituation、Requirement Ledger 和 Root Contract。
- 判断 fast path 或 graph path。
- 生成 Task Contract Graph。
- 生成 hard capability requirements 和 soft capability weights。
- 选择 worker，并解释候选过滤与选择理由。
- 为每个节点生成 `VerifierPlan`。
- 根据结构化反馈提出有限图修订。

Decompose 不负责：

- 启动 Claude、Codex、OpenCode 或其他 worker。
- 管理 subprocess、session、workspace、timeout 或 callback。
- 真正运行测试、lint、build 或语义评审。
- 应用 patch、合并 artifact 或决定主任务最终完成。
- 保存单次协作上下文、运行日志或跨任务历史记录。
- 直接更新 Dashboard 或向用户回复。

这些职责分别属于 [delegator.md](delegator.md)、[verifier.md](verifier.md)、[memory.md](memory.md)、[history.md](history.md) 和 Application 层。

## 2. Decompose 核心流程

原先 C4 的九步流程是整个系统的运行流程，不应全部放在 Decompose 中。Decompose 自身收缩为六步：

```text
1. Task Situation Grounding
   用户目标 + Skill/模式 + 必要仓库事实 + worker registry
                  ↓
2. Root Contract Construction
   Requirement Ledger + 全局验收条件
                  ↓
3. Fast Path / Graph Path Decision
   判断拆解是否真正降低风险、上下文或能力压力
                  ↓
4. Contract Graph Generation
   节点目标 + 依赖 + Context Pack + 权限 + VerifierPlan
                  ↓
5. Capability-Aware Worker Assignment
   Hard Filter + Soft Score + Confidence + Risk/Consent Plan
                  ↓
6. Feedback-Driven Replanning
   根据 Delegator/Verifier/Application 的结构化反馈修订计划
```

步骤 4 和步骤 5 是 C4-ACD 最核心的方法贡献：拆解时同时考虑 worker 能否执行、结果能否验证，以及协作成本是否值得。

### 2.1 与系统运行流程的关系

```text
Decompose.prepare
  -> Application 保存计划快照
  -> Delegator 执行已分配节点
  -> Verifier 执行节点 VerifierPlan
  -> Application 判断继续、重规划或终止
  -> Verifier 执行 Root Contract 验收
  -> History 记录 outcome，供未来 Decompose 使用
```

这里需要严格区分“设计验证”与“执行验证”：Decompose 生成验证契约，Verifier 执行契约并返回结果。

## 3. 方法细节

### 3.1 Task Situation Grounding

`TaskSituation` 是拆解前的主任务表示，属于 Private Orchestrator State，不原样发送给 worker。

```text
TaskSituation
  objective
  requirements[]
  constraints[]
  interaction_mode
  active_skills[]
  skill_steps[]
  environment_facts[]
  unresolved_questions[]
  available_workers[]
  historical_profile_summary
  security_context
```

信息优先级为：用户明确要求、系统与模式约束、Skill workflow、已验证仓库事实、worker manifest、历史画像、模型推断。低优先级信息不得覆盖高优先级要求；模型推断必须显式标记。

#### Minimal Sufficient Grounding

“看总体”不等于扫描整个仓库。C4 使用有预算的 preflight：

1. 读取已触发 Skill 的必要流程。
2. 读取用户点名的文件和入口。
3. 获取浅层目录、配置、测试入口和语言信息。
4. 仅在拆解被关键未知量阻断时生成 `probe` 节点。
5. 达到拆解决策所需信息后停止读取。

三类初始入口：

- **Skill 驱动任务**：Skill 步骤是 workflow 约束，不机械等同于一个步骤一个 worker。
- **长用户请求**：先抽取 deliverable、constraint、preference 与 acceptance。
- **Plan Mode**：允许调查和生成计划，但节点强制只读，不能因为计划中提到修改就授予写权限。

### 3.2 Root Contract Construction

`RequirementLedger` 保存：

```text
Requirement
  id
  kind: deliverable | constraint | preference | acceptance
  text
  required
```

`RootContract` 回答“整个任务何时算完成”，包括：

- 每个 required requirement 的对应证据或产物。
- 必须通过的整体测试、构建或人工判断。
- Skill 的最终流程要求。
- 用户禁止事项和安全边界。
- 多节点输出如何组合，以及最终决策由谁完成。

Root Contract 是 Decompose 的规划约束。最终是否满足它，由 Root Verifier 和 Application 判断。

### 3.3 Fast Path / Graph Path Decision

拆解并不总是更好。C4 比较直接执行与任务图执行的预期代价：

```text
GraphBenefit = context_reduction
             + capability_specialization
             + safe_parallelism
             + verification_locality
             - coordination_cost
             - duplicated_context
             - merge_risk
             - extra_model_calls
```

触发 graph path 的常见条件：

- 存在多个可独立追踪的 deliverable。
- Skill 包含有真实依赖的多阶段 workflow。
- 单一 worker 不具备所有硬能力。
- 不同节点需要不同权限、模态或 harness。
- 子任务可以独立验证并显著缩小上下文。
- 未解决问题需要先执行有界 probe。

停止拆解的条件：

- 节点目标单一且产物明确。
- 输入上下文和权限范围可界定。
- 存在至少一个符合硬能力的 worker。
- 能定义成本合理的 verifier。
- 继续拆分的协调开销大于预期收益。

### 3.4 Contract Graph Generation

#### 节点契约

每个 `TaskNodeContract` 至少包含：

```text
identity
  node_id
  kind: probe | work | verify | merge | decision | wait
  objective
  requirement_refs[]

context
  context_packs[]
  artifact_inputs[]
  allowed_paths[]

execution requirements
  execution_mode
  write_paths[]
  output_type
  hard_capabilities
  soft_capability_weights

verification design
  deterministic_checks[]
  evidence_requirements[]
  semantic_check
  root_contribution

recovery
  max_attempts
  fallback_actions[]
```

Task Contract Graph 只描述计划和依赖，不等同于 [memory.md](memory.md) 的 Shared Context-Artifact Graph。前者是 Decompose 的规划产物；后者是一次任务执行时给 worker 共享上下文和 artifact 的运行视图。

#### 拆解操作符

C4 第一版使用可解释操作符生成候选图：

- `deliverable_split`：按独立交付物拆分。
- `workflow_split`：按 Skill 中真实前后依赖拆分。
- `evidence_split`：把 probe/调查与实现分开。
- `capability_split`：按多模态、工具、写权限或持续会话需求拆分。
- `risk_split`：把高风险写操作与只读分析分开。
- `verification_split`：把昂贵或独立的验证节点显式化。

禁止按文件数量、段落或 token 长度机械切分。

#### Atomicity 与 Routing-Aware Split Test

候选节点通过以下检查才进入计划：

1. 目标能否一句话说明？
2. 输入与产物是否有清楚边界？
3. 是否能定义 verifier？
4. 是否至少存在一个符合 hard capabilities 的 worker？
5. worker 是否能在不读取主线程隐藏状态的前提下完成？
6. 合并成本是否低于拆解收益？

如果没有合格 worker，Decompose 应改变任务边界、继续拆分或保留给主 agent，而不是生成一个注定失败的节点。

### 3.5 Capability-Aware Worker Assignment

#### WorkerArm

```text
WorkerArm
  backend
  harness
  model and version
  policy profile
  hard capability manifest
  declared soft capabilities
  historical capability evidence
  current availability
```

同一个模型在不同 harness 下应视为不同 WorkerArm，因为工具、session、memory、patch 和 sandbox 能力可能不同。

#### Hard Capability Filter

硬能力不参与加权补偿，任一必要条件不满足就排除：

- modalities：text、image、audio 等。
- tools：read、grep、terminal、browser、patch、test。
- write isolation：staged copy、worktree 或直接 workspace。
- network 与 provider protocol。
- context window 与 structured output。
- persistent session / async monitor。
- privacy zone、外发策略和宿主限制。

#### Soft Capability Dimensions

第一版使用少量可解释维度：

- code implementation
- debugging and root-cause analysis
- frontend and visual work
- documentation and research
- architecture and planning
- long-context synthesis
- test generation and review

用户可以声明偏好；历史 verified outcome 只能作为证据，不能覆盖硬约束。

#### 历史能力证据

历史能力数据来自独立的 Execution History，而不是 Shared Memory。输入只应是聚合或摘要，例如：

```text
CapabilityEvidence
  worker_arm_id
  task_dimension
  verified_success / failure / inconclusive
  sample_count
  rework and escalation rate
  token and latency distribution
  environment / policy failure excluded
```

Execution History 的方法和持久化边界见 [history.md](history.md)。Decompose 只读取画像，不负责保存原始执行事件。

#### Explainable Assignment

通过 hard filter 后，第一版使用显式 scorecard：

```text
RouteScore = wq * quality_evidence
           + wc * capability_match
           + wp * user_preference
           - wt * expected_tokens
           - wl * expected_latency
           - wr * operational_risk
           - wu * uncertainty
```

Assignment 输出必须包含：

- 所有候选 worker。
- 被硬过滤的 worker 及原因。
- 合格 worker 的分项得分与证据来源。
- 最终选择、备选和不确定性。
- 结果验证失败后的 fallback 顺序。

模型自报 confidence 只能作为弱信号。第一版 confidence 主要由任务覆盖、能力匹配、历史样本量和 verifier 可执行性组成。

#### Security Risk Manifest 与 Consent Plan

选择实际 provider/harness 后，Decompose 为外部 assignment 生成 `SecurityRiskManifest`：

- destination/provider 与认证方式。
- 精确传输路径、Context Pack、日志快照和 artifact。
- 只读、隔离 patch、执行或持续 monitor 模式。
- write allowlist、本地副作用、session 和 callback 行为。
- 可能暴露的信息与明确排除的 secret。
- provider 处理、日志、留存等 C4 无法控制的风险。
- 宿主策略仍可能拒绝执行。

Decompose 只生成风险清单和 consent scope。真正暂停执行、获得用户确认和调用宿主审批的是 Application 的 Policy Gate；Delegator 不得自行扩大已批准范围。

### 3.6 Verifier-by-Construction

Decompose 为每个可执行节点生成 `VerifierPlan`：

```text
VerifierPlan
  structural_checks[]
  policy_checks[]
  evidence_requirements[]
  executable_checks[]
  semantic_criteria[]
  root_contribution
  inconclusive_policy
```

设计原则：

- 确定性检查优先于模型评审。
- worker 自报成功不能作为唯一证据。
- patch 节点必须检查 write scope 和可应用性。
- 验证成本过高时，应重新考虑是否值得拆解。
- `inconclusive` 与失败不同，应触发补证据或升级，而不是直接惩罚 worker。

Verifier 的检查算法、Root Verification 和 failure attribution 见 [verifier.md](verifier.md)。

### 3.7 Feedback-Driven Replanning

Decompose 接收结构化反馈，而不是直接观察 subprocess：

```text
missing_context
worker_capability_mismatch
verification_failed
verification_inconclusive
environment_failure
permission_blocked
consent_scope_changed
new_dependency
conflict_detected
budget_exhausted
root_gap
```

基础调整阶梯：

```text
add context
  -> revise node contract
  -> retry same worker once
  -> select another eligible worker
  -> split node further
  -> escalate to main agent
  -> stop and report blocker
```

环境失败和宿主策略阻断不能记为 worker 能力失败。路径、provider、写权限、持续快照或 callback 范围扩大时，旧 consent scope 失效，必须重新生成风险摘要。

每次重规划都有 attempt、depth、Token 和 wall-time 上限，不能无限循环。

## 4. 第一版本实现与 Future Work

### 4.1 第一版本

- 基础 TaskSituation、Requirement Ledger 和 Root Contract。
- 支持长 prompt、单个 Skill workflow 和 Plan Mode。
- 规则式 fast/graph path 判断。
- 使用可解释拆解操作符生成 2–5 个主要 work 节点。
- TaskNodeContract 包含 hard requirements、soft weights 和 VerifierPlan。
- hard capability filter 与静态 scorecard assignment。
- `never/ask/allow`、数据分类和节点级风险清单。
- 接收结构化失败类型并产生有界 ReplanDecision。
- 输出完整 `DecompositionPlan`，但不执行 worker 或写 Shared Memory。

### 4.2 Future Work

- 从复杂或多个 Skill 自动抽取 contract graph。
- 多候选任务图与 decomposition-routing-verification 联合优化。
- Bayesian capability profile、样本量与校准置信度。
- 在低风险、强验证任务上使用 contextual bandit 受控探索。
- 处理模型版本迁移、跨项目差异和冷启动 prior。
- 更精细的协调成本、重复上下文和 merge-risk 估计。
- 针对开放式研究、架构和视觉任务的 verifier planning。
- 自动检查 Risk Manifest 完整性与 consent scope 复用粒度。

### 4.3 当前代码状态

当前 `cost_router/decompose/` 已有 TaskSituation、RootContract、TaskContractGraph、基础 fast/graph planner、hard capability filter 和简单 assignment。它仍把若干职责集中在 `planner.py`，且 `DecompositionService` 还直接调用 `MemoryStore.record_decomposition()`，这是早期闭环的过渡耦合。

目标结构中 Decompose 应只返回计划；由 Application 决定是否把计划快照写入 Execution History。Task Contract Graph 不应作为 Shared Memory 的上下文节点图保存。当前 SQLite 中的 `record_decomposition()` 行为需在后续兼容迁移中转移到独立 History repository。

## 5. 评估方案

### 5.1 Decompose 直接指标

- Requirement coverage 和 constraint preservation。
- 节点原子性、可执行率与可验证率。
- Invalid route rate：缺少硬能力、越权或没有 verifier。
- Worker eligibility precision/recall。
- Assignment verified success、rework 与 escalation rate。
- Graph coordination、重复上下文和 merge overhead。
- Replan 次数、深度和原因分布。
- Decomposition/assignment confidence calibration。
- 用户 override 与偏好符合度。

### 5.2 核心消融

1. 裸 prompt 拆解 vs TaskSituation grounding。
2. 先拆后路由 vs joint decomposition-assignment。
3. 无 VerifierPlan vs verifier-by-construction。
4. 仅声明能力 vs hard manifest + verified history。
5. 静态 graph vs feedback-driven replanning。
6. 自报 confidence vs evidence-based confidence。
7. 所有任务建图 vs fast path。

### 5.3 初始任务类型

- Skill 驱动的多步骤 coding task。
- 长用户请求中的多交付物任务。
- 代码库调查、日志分析、bounded patch 和 review。
- 需要不同 harness、权限或模态的组合任务。

端到端 Token、callback、Dashboard 和最终用户体验属于整个 C4Harness 的系统评估，不应混入 Decompose 的直接指标。

## 6. 相关工作与局限

- **ADaPT** 提示拆解应按执行反馈逐步加深，而非一次生成固定树。
- **CodePlan** 说明代码任务计划需要由依赖和实际修改持续扩展。
- **ParaManager / GraphPlanner** 支持把任务结构、角色与模型选择联合考虑。
- **在线路由与 contextual bandit** 适合只有被选择 worker 获得部分反馈的场景。
- **校准与不确定性工作** 提醒 C4 不能把自然语言 confidence 当概率。

C4 当前局限包括：grounding 尚未自动化，能力画像样本稀疏，scorecard 权重缺少实证，开放式任务的 verifier plan 较弱，复杂图的协调成本也尚未被准确估计。

## 7. 总结与开放问题

C4-ACD 的核心不是“把任务切小”，而是：

```text
understand the task
  -> define completion
  -> decide whether decomposition helps
  -> build executable and verifiable contracts
  -> jointly assign capable workers
  -> revise the plan from attributed feedback
```

开放问题：

- 如何从 Skill workflow 中抽取真实依赖，而不是机械复制步骤？
- 如何联合优化拆解质量、worker 成功率、验证成本和协调开销？
- 如何在历史样本很少时表达能力与 assignment confidence？
- 如何避免环境失败、权限阻断和上下文不足污染 worker 画像？
- consent scope 应在什么粒度复用，才能兼顾安全与用户打断次数？
- 何时继续拆解，何时升级主 agent，才具有稳定可解释的边界？
