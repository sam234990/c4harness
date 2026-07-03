# C4 Task Decomposition and Routing Method

**Status**: method design draft  
**Date**: 2026-07-03  
**Scope**: C4 / C4Harness / Cost Router 的任务理解、拆解、worker 分配、验证与在线适应

本文提出 C4 的默认任务拆解方法 **C4-ACD（Adaptive Contract Decomposition，自适应契约式拆解）**。它面向 Codex、Claude CLI、OpenCode 和不同 provider/model 组成的异构 agent harness，目标不是生成一份好看的待办清单，而是形成一套能够真实执行、验证、调整和追踪的任务运行机制。

## 1. 设计目标

### 1.1 要解决的问题

C4 不应把任务拆解实现为“把用户最后一条 prompt 交给 planner，再得到若干字符串子任务”。真实 coding task 的边界还取决于：

- 用户最初目标、后续补充和明确禁止事项。
- 当前是普通执行、Skill 驱动还是 Plan Mode。
- Skill 规定的流程、资源和验收要求。
- 仓库结构、相关代码、日志、测试和运行环境。
- 可用 worker 的模型、harness、工具、模态、权限和上下文能力。
- 用户偏好以及 worker 在本机历史任务中的实际表现。

如果忽略这些信息，拆出来的节点可能无法执行、不能验证、超出权限，或者根本没有合适的 worker。因此 C4 拆解的对象不是裸 prompt，而是经过必要 grounding 的 **Task Situation**；拆解产物不是普通待办列表，而是可路由、可验证、可重规划的 **Task Contract Graph**。

### 1.2 核心设计原则

1. **先理解任务，再进行拆解**：只收集完成决策所需的最小上下文，不盲目扫描整个仓库。
2. **先定义完成，再定义工作**：主任务和每个子任务都必须在执行前写明验收条件。
3. **拆解与路由联合考虑**：只有存在可用 worker、明确上下文和可执行 verifier 的子任务才是有效拆解。
4. **每个节点都是执行契约**：节点同时声明目标、输入、产物、能力、权限、验证和失败策略。
5. **硬能力先过滤，软能力再比较**：工具、模态和权限不满足时直接排除；偏好与历史能力只在合格 worker 中起作用。
6. **验证独立于 worker 自报**：测试、文件、日志和结构化证据优先于“我已经完成”的自然语言声明。
7. **任务图允许动态变化**：上下文不足、能力不匹配、发现新依赖或验证失败时，可以补信息、换 worker 或继续拆解。
8. **简单任务保持简单**：一个 worker 足以完成的任务走 fast path，不为方法完整性强行构建复杂 DAG。
9. **反馈必须可解释**：记录路由理由、结果证据与失败归因，再决定是否更新能力画像。

### 1.3 设计目标

- 覆盖 Skill 驱动任务、长用户请求和 Plan Mode 三类主要入口。
- 同时适用于 Codex internal subagent 与 Claude/OpenCode 等 external harness。
- 模型、harness、工具、模态、权限和上下文限制可以独立描述。
- 简单任务低延迟执行，复杂任务可形成多 worker、有依赖的任务图。
- 每次委托都有可阅读的候选、过滤原因和选择理由。
- 不依赖大规模离线数据或预先训练一个 router。
- 将 verifier 结果安全地转化为本地历史与后续路由依据。
- 让用户能够控制偏好、查看统计并纠正错误路由。

### 1.4 非目标

- 不追求一次生成全局最优 DAG。
- 不按文件数量、段落或 token 长度机械切块。
- 不让 worker 无限制读取主 harness 的完整 memory。
- 不把模型自报 confidence 当作准确成功概率。
- 不强迫所有任务进入多 agent 模式。
- 第一版本不实现 PPO、神经 router、reward model 或大规模离线标注。
- C4 聚焦 multi-harness coding task routing，不扩张为通用 multi-agent runtime。

## 2. 总流程与实现路线

### 2.1 九步主流程

```text
1. 构建任务情境
   用户目标 + Skill/模式 + 仓库事实 + worker 能力
                  ↓
2. 定义主任务验收条件
   Requirement Ledger + Root Contract
                  ↓
3. 判断是否需要拆解
   Inline Fast Path 或 Graph Path
                  ↓
4. 生成任务契约图
   节点目标 + 依赖 + 上下文 + 权限 + verifier
                  ↓
5. 根据能力选择 worker
   Hard Capability Filter + Explainable Assignment
                  ↓
6. 执行 worker
   发送受限 Context Pack，收集结果、artifact 和 patch
                  ↓
7. 独立验证节点结果
   Deterministic / Grounded / Semantic Verification
                  ↓
8. 失败时动态调整
   补上下文、重试、换 worker、继续拆解或升级
                  ↓
9. 主任务验收并记录结果
   Merge + Root Verification + Ledger/Profile Update
```

这九步是 C4 的主控制流。第一版本先跑通完整闭环；后续工作增强其中每个模块，而不改变主流程。

### 2.2 第一版本实现内容

第一版本要实现的是可运行、可验证的基础闭环：

| 流程阶段 | 第一版本范围 |
|---|---|
| 任务情境 | 基础 `TaskSituation`；支持长 prompt、单个 Skill 和 Plan Mode；必要时创建 `probe` |
| 主任务验收 | Requirement Ledger 与基础 Root Contract |
| 拆解判断 | 规则 + 一次 LLM 判断；支持 fast path 与 graph path |
| 任务图 | `probe`、`work`、`verify`、`merge`；默认 2-5 个主要 work 节点 |
| worker 选择 | WorkerArm manifest、hard capability mask、声明偏好和基础软能力标签 |
| 执行 | 顺序图执行为主；仅对依赖和文件范围明确独立的节点有限并行 |
| 验证 | 结构、文件范围、证据、测试、lint 和 build 等确定性检查 |
| 动态调整 | 补上下文、同 worker 重试一次、换 worker、继续拆解或升级主 agent |
| 最终记录 | Root verification；记录图、路由理由、Token、延迟、验证与失败归因 |

第一版的历史数据主要用于展示和辅助判断，不自动接管高风险任务的路由决策。

### 2.3 Future Work

#### 更强的任务理解与拆解

- 从复杂 Skill、多个 Skill 和隐式 workflow 中自动抽取 contract graph。
- 更精细的 requirement dependency、冲突检测和长上下文渐进读取。
- 同时生成多个候选图，联合优化拆解、worker 分配、协调和验证成本。
- 支持 `decision`、`wait`、alternative branch 和长时间异步任务图。

#### 更强的能力画像与在线适应

- 使用 Bayesian scorecard、分能力后验和样本量表达经验能力。
- 引入 decomposition、routing 与 result confidence 及其 calibration。
- 在低风险、可验证任务上使用 Thompson Sampling、UCB 或 contextual bandit 受控探索。
- 处理模型版本变化、冷启动 prior、跨项目差异和能力迁移。
- 根据用户反馈与历史结果形成可解释、可关闭的个性化路由。

#### 更强的验证与失败恢复

- 为开放式研究、架构设计、视觉效果和文档质量设计 semantic verifier。
- 使用独立模型评审、交叉验证、差异测试和 verifier ensemble。
- 改进 decomposition error、worker error、上下文缺失和环境失败之间的归因。
- 支持复杂 patch merge、同文件并发修改、回滚和局部重执行。

#### 更高效的运行机制

- 基于依赖、文件锁、资源和风险进行安全并行调度。
- 动态决定补充 Context Pack、重新拆分或改变任务边界。
- 优化重复上下文、协调 Token、延迟和主模型唤醒次数。
- 统一异步 worker、持续会话、外部事件和 Codex callback 与任务图。

#### 方法研究

- 提供稳定的 decomposer、assignment policy 和 verifier 扩展接口。
- 系统评估 task-situation grounding、joint decomposition-routing 和 verifier-by-construction。
- 只有在本地数据充分且能够证明收益后，才考虑 learned router 或 reward model。

### 2.4 当前实现状态

当前代码已经建立第一层开发骨架：`cost_router.decomposition` 定义了 `TaskSituation`、Requirement Ledger、Root Contract、`TaskNodeContract`、WorkerArm、hard capability filter、fast/graph 初始规划和图持久化；`DelegationRuntime` 将单个节点的 route、delegate、verify、record 生命周期从 CLI 中抽离，后续图执行器可以复用。

尚未完成的是从真实聊天与 Skill 自动 grounding、LLM 候选图生成、图调度与重规划、Root Verifier、经验能力画像和在线适应。现有 `route_task()` 仍主要使用 read-only log/exploration 规则，CLI 也尚未自动启动完整 decomposition 流程。因此本文其余部分仍是目标方法规范，不代表第一版本闭环已经全部实现。

## 3. 方法细节

本章按照九步主流程展开。每一节对应一个运行阶段，避免把数据结构、算法和执行策略拆散到互不相邻的章节。

### 3.1 构建任务情境

#### TaskSituation

`TaskSituation` 是拆解前的任务表示，属于主 harness 的 Private Orchestrator State，不原样发送给 worker。

```text
TaskSituation
  user_intent
  deliverables[]
  constraints[]
  interaction_mode
  active_skills[]
  skill_workflow
  environment_facts[]
  unresolved_questions[]
  available_workers[]
  policy_preferences
  historical_profile_summary
```

信息优先级为：

1. 用户明确要求与禁止事项。
2. 系统和当前交互模式的权限边界。
3. 已触发 Skill 的流程、资源与验证要求。
4. 仓库、文件、日志、git 状态和命令的必要观察。
5. worker capability manifest。
6. 本地历史画像与用户偏好。
7. 模型推断。

发生冲突时高优先级覆盖低优先级。模型推断必须显式标记，不能伪装成用户要求或已验证事实。

#### Minimal Sufficient Grounding

“先看总体”不等于读取整个仓库。C4 使用有预算的 preflight：

- 读取已触发 Skill 的完整主流程和它明确要求的资源。
- 从长 prompt 中提取交付物、约束、验收条件和引用对象。
- 读取文件树、相关配置、当前变更和测试入口等必要仓库信息。
- 对日志、图片、PDF 或目录只进行任务相关探测。
- 检查候选 worker 的模态、工具、权限和上下文能力。

如果信息不足以形成稳定拆解，则创建 `probe` 节点。Probe 的产物是经过证据支持的 environment fact 或 context map，例如定位失败测试、确认修改范围、识别必需图片，或者找到可运行的测试命令。

#### 三类初始入口

**Skill 驱动任务**：Skill 是 workflow contract source。主 harness 抽取必要阶段、顺序、保留决策、必读材料和验收条件，再判断哪些阶段可以委托。Skill 不应被整体视为只能交给同一 worker 的原子任务。

**长用户请求**：先提取交付物、约束、偏好、验收条件和未决歧义，拆解优先沿交付物、证据、依赖与权限边界展开，而不是按自然语言段落切分。

**Plan Mode**：硬约束是不修改目标工作区。允许 repository probe、方案比较、风险分析和验证设计；编辑节点只能产生计划或 patch sketch。

### 3.2 定义主任务验收条件

#### Requirement Ledger

用户需求先被整理为可追踪条目：

```text
R1 deliverable
R2 deliverable
C1 hard constraint
C2 preference
A1 acceptance condition
Q1 unresolved ambiguity
```

每个 requirement 必须由至少一个任务节点覆盖。约束与验收条件不能只保留在原始聊天文本中，否则多个 worker 执行后很容易被遗漏。

#### Root Contract

Root Contract 回答“什么情况下整个任务才算完成”，至少包括：

- 最终交付物和必须满足的约束。
- 每个 requirement 对应的证据或产物。
- 必须执行的整体测试、构建或人工判断。
- Skill 的最终流程要求。
- 多节点结果如何合并，以及由谁做最终决策。

Root Contract 与局部 verifier 同时存在。局部节点全部成功，并不自动表示用户任务已经完成。

### 3.3 判断是否需要拆解

#### Fast Path 与 Graph Path

满足以下条件时使用 inline fast path：

- 只有一个主要产物。
- 一个合格 worker 可以在单次 session 中完成。
- 所需 Context Pack 较小。
- 没有并发文件冲突或复杂依赖。
- verifier 可以直接执行。

```text
TaskSituation summary
  -> one TaskNodeContract
  -> worker execution
  -> verifier
  -> root acceptance and ledger
```

出现多个 worker、异构能力、动态依赖、长任务或独立验证阶段时才持久化完整 graph。

#### 拆解触发条件

- 用户要求包含多个可分别验收的交付物。
- Skill 规定多阶段流程或独立检查。
- 任务跨视觉、代码、测试、文档等不同能力域。
- 输入超过单个 worker 的有效上下文范围。
- 不同部分具有不同权限或风险等级。
- 可以按假设、模块或 review dimension 独立获取证据。
- 代码修改可能沿依赖或 change impact 传播。
- 存在需要等待和持续监控的 workload。
- 当前 worker 无法完成整体任务，但可能完成更小节点。

#### 停止拆解条件

- 节点已经满足原子性要求。
- active work nodes 达到策略上限，第一版建议 2-5 个。
- 继续拆解的收益低于上下文复制、协调、合并与验证开销。
- 子任务需要共享大量隐式状态，无法形成稳定接口。
- verifier 无法判断局部结果是否推进 Root Contract。
- 所有候选 worker 都缺少必要权限或主 agent 私有上下文。

### 3.4 生成任务契约图

#### 节点与边

C4 使用可版本化 DAG：

| Node kind | Purpose | 第一版本 |
|---|---|---|
| `probe` | 获取拆解或执行所需事实 | 是 |
| `work` | 产生分析、代码、文档等目标产物 | 是 |
| `verify` | 独立检查节点结果 | 是 |
| `merge` | 合并多个产物并检查一致性 | 是 |
| `decision` | 需要主 agent 或用户选择 | Future |
| `wait` | 等待训练、构建或部署事件 | Future |

主要关系包括 `requires`、`produces_for`、`verifies`、`alternative_to`、`conflicts_with` 和 `discovered_from`。重规划产生新版本，不在同一个 DAG 版本里用循环表示无限返工；历史变更作为 event 保存。

#### TaskNodeContract

```yaml
id: node_...
kind: work
objective: one observable outcome
requirement_refs: [R1, C1]
inputs:
  context_packs: []
  artifacts: []
  allowed_paths: []
output_contract:
  artifact_type: patch | report | evidence_set | plan | status
  schema: optional structured schema
capabilities:
  hard: []
  soft: []
constraints:
  mode: read_only | patch | execute | monitor
  network: deny | allow
  write_paths: []
  token_budget: optional
  timeout: optional
verification_contract:
  deterministic_checks: []
  evidence_requirements: []
  semantic_check: optional
  root_contribution: what this proves for the parent task
failure_policy:
  missing_context: request_context | create_probe
  failed_verification: retry | reroute | decompose | escalate_main
  max_attempts: 1
```

节点目标必须描述可观察结果，不能只是“思考”“尽量完成”或“处理这些文件”。

#### 原子性检查

一个节点在以下条件下才算足够原子：

- 只有一个主要产物或结论。
- 所需上下文可以明确列出并控制大小。
- 文件写权限可以显式枚举。
- 存在可执行或证据化的验收方法。
- 一个 worker session 能够在预算内完成。
- 失败后能够判断下一步是补上下文、换 worker、继续拆解还是升级。

#### 拆解操作符

第一版使用有限、可解释的操作符：

1. `deliverable split`：按最终产物拆分。
2. `workflow split`：按 Skill 或已知流程阶段拆分。
3. `evidence split`：按证据来源或失败假设拆分。
4. `dependency split`：按代码依赖、change impact 或数据流拆分。
5. `capability split`：将视觉、前端、测试、文档等工作分开。
6. `permission split`：将只读调查与 patch/execute 分开。
7. `alternative split`：验证少量互斥假设，满足条件后停止。
8. `temporal split`：将启动、监控、终态诊断和后续修复分开。

#### Routing-Aware Split Test

每个 leaf 必须至少存在一个 eligible worker，否则候选图无效。概念上的联合效用为：

```text
U(G, A) = sum_i [Q(i, a_i) - wc*C(i, a_i) - wl*L(i, a_i) - wr*R(i, a_i)]
          - wk*Coord(G) - wv*Verify(G) - wx*ContextDup(G)
```

其中 `Q`、`C`、`L` 和 `R` 分别表示预测质量、Token、延迟和风险；`Coord`、`Verify` 与 `ContextDup` 是拆解带来的额外开销。第一版不求全局最优，只做可解释的 atomic-vs-split 比较：

```text
accept split when:
  estimated_utility(split) > estimated_utility(atomic) + split_margin
  and every leaf has an eligible worker
  and every leaf is verifiable
  and root requirement coverage is complete
```

### 3.5 根据能力选择 worker

#### WorkerArm

C4 的路由单位不是 model name，而是：

```text
WorkerArm = backend + harness + model + model_version + policy_profile
```

同一模型在 Codex subagent、Claude Code 或 OpenCode 中可能拥有不同工具、系统提示、memory 和文件编辑行为，因此必须分别描述和统计。

#### Hard Capabilities

Hard capability 不参与偏好打分；不满足就直接过滤：

- `modalities`: text、image、audio、video。
- `tools`: read、grep、glob、patch、shell、browser、MCP tools。
- `write_isolation`: none、staged_copy、worktree、direct。
- `network`: supported/forbidden。
- `structured_output`: JSON/schema support。
- `context_limit` 与建议有效上下文。
- `persistent_session` 与 async callback。
- `provider_protocol`: Responses、Chat Completions、harness-native CLI。
- `privacy_zone`: local-only 或 approved external provider。
- `risk_ceiling`: worker 可承担的最高风险。

例如，没有 vision 的模型不能进入图片理解节点的候选集；没有 patch 能力或隔离写机制的 worker 不能执行编辑节点。

#### Soft Capability Dimensions

第一版使用少而稳定的能力维度：

| Dimension | Typical evidence |
|---|---|
| `repo_exploration` | 找入口、调用链和相关文件 |
| `code_edit` | 产生可应用并通过检查的 patch |
| `debugging` | 从日志、测试和代码定位根因 |
| `test_terminal` | 正确使用命令、测试和构建反馈 |
| `architecture_planning` | 跨模块设计、风险和依赖分析 |
| `documentation_research` | 技术文档、论文和说明文写作 |
| `frontend_ui` | 前端实现、交互和视觉质量 |
| `multimodal_understanding` | 图像、截图和 PDF 页面理解 |
| `long_context_synthesis` | 多文件、多日志综合 |
| `security_sensitive` | 权限、秘密和高风险修改判断 |

#### 能力画像来源

1. **Declared profile**：adapter/provider 声明的工具、模态、上下文和默认能力标签。
2. **User preference**：用户对模型、provider 或能力维度的 prefer/avoid/disable 设置。
3. **Empirical profile**：本机 verified history 产生的成功、Token、延迟、升级与返工统计。

用户偏好不能创造 hard capability。例如用户偏好某模型做视觉任务，但它不支持图片，该 worker 仍应被过滤。

#### 可解释选择

每次路由至少记录：

```text
eligible or filtered
hard capability reasons
declared and empirical capability evidence
expected token and latency
user preference adjustment
risk adjustment
final selection reason
```

第一版使用规则与基础评分。未来可以表示为：

```text
RouteScore = wq*QualityEstimate
             - wt*TokenEstimate
             - wl*LatencyEstimate
             - wr*RiskPenalty
             - wo*CoordinationOverhead
             + wp*UserPreference
```

### 3.6 执行 worker

#### 可见上下文边界

worker 只获得当前节点需要的：

- TaskNodeContract。
- 经过裁剪的 Context Pack。
- 前置节点产出的必要 artifact。
- 允许读取和修改的文件范围。
- 可运行命令、超时和预算约束。

主 harness 的完整 TaskSituation、隐藏 verifier 策略和其他私有信息保留在 Private Orchestrator State。该结构与 [memory.md](memory.md) 对应：

```text
Private Orchestrator State: TaskSituation + graph policy + hidden verifier policy
Worker Task Nodes: TaskNodeContracts and execution states
Context Packs: worker-visible progressive context
File/Artifact Nodes: code, logs, patches, outputs and evidence
```

#### 执行顺序与产物

第一版优先执行依赖已满足的节点，并以顺序调度为主。只有节点依赖、文件范围和 verifier 都相互独立时才允许有限并行。worker 必须返回统一状态、结果摘要、证据、artifact 路径、patch 路径和风险说明。

#### 核心生命周期事件

Hooks 不改变主流程，只在明确事件点执行策略与审计：

```text
pre_ground -> post_ground
pre_decompose -> post_decompose
pre_route -> post_route
pre_delegate -> post_delegate
pre_verify -> post_verify
on_replan
post_root_verify
```

安全策略只能收紧权限，不能扩大 hard capability、绕过 sandbox、删除 verifier requirement 或读取未授权私有状态。完整的第三方插件协议不属于第一版本主流程。

### 3.7 独立验证节点结果

#### Verifier-by-Construction

节点被分配前就必须回答：

- 什么产物算完成？
- 必须提供哪些证据？
- 可以执行哪些 deterministic checks？
- 谁有权限执行检查？
- 失败后应该重试、补上下文、换 worker、继续拆解还是升级？

无法回答这些问题的节点通常不适合委托，应当进一步 grounding 或改写任务边界。

#### 验证层级

1. **Contract/schema**：输出字段、artifact 和路径存在。
2. **Policy**：未访问或修改未授权对象。
3. **Grounding**：证据与真实文件、日志、网页或命令输出一致。
4. **Executable**：patch apply、syntax、type check、tests 或 build 通过。
5. **Semantic**：结果真正满足节点目标。
6. **Integration**：多个节点的产物不冲突，并能共同推进 Root Contract。

优先执行便宜、确定性的检查。只有确定性证据不足时，才使用主 agent 或独立强模型进行 semantic review。

#### Result Confidence

结果证据按强度区分：

1. `deterministic`：测试、构建、schema 或 patch apply 等客观检查通过。
2. `grounded`：文件、日志、行号、网页或 artifact 可以复查。
3. `semantic_reviewed`：由主 agent 或独立 verifier 复核。
4. `self_reported`：只有 worker 自报，证据等级最低。

verifier 输出应区分 accepted、rejected 和 inconclusive，不能把“无法验证”当作通过。

### 3.8 失败后动态调整

#### 失败归因

| Attribution | 对 worker 画像的影响 |
|---|---|
| `worker_error` | 正常负向记录 |
| `capability_mismatch` | 更新 eligibility/profile，较强负向记录 |
| `missing_context` | 少量或不惩罚 worker；修正 context policy |
| `bad_task_contract` | 不惩罚 worker；修正 decomposer |
| `environment_failure` | 不更新模型质量 |
| `permission_blocked` | 更新 capability/policy，不惩罚模型能力 |
| `verification_inconclusive` | 仅作低权重记录 |
| `integration_conflict` | 更新协调与拆解统计 |

失败归因是后续在线适应可信的前提。否则测试环境损坏可能被错误学习为“某模型不擅长写代码”。

#### 调整阶梯

```text
add context
  -> retry same worker once
  -> reroute to a better-matched worker
  -> decompose the failed node
  -> independent verifier or stronger harness
  -> main agent decision
```

能力不匹配时应横向换专长 worker；只有任务难度或不确定性明显上升时才向更强模型升级。

#### 图重规划事件

- `missing_context`：创建 Context Pack 或 Probe Node。
- `capability_mismatch`：更换 worker，必要时改写节点边界。
- `verification_failed`：局部修复、再拆解或升级。
- `new_dependency`：根据新证据增加节点和依赖。
- `conflict_detected`：增加 merge 或主 agent 决策。
- `budget_exhausted`：缩小范围、停止探索或升级。
- `root_gap`：Root Verifier 发现 requirement 未覆盖。

每个节点设置 attempt、depth 和 budget 上限，重规划不能无限循环。

### 3.9 主任务验收与结果记录

#### Root Verification

Root Verifier 检查：

- Requirement Ledger 是否全部覆盖。
- 节点之间是否还有未解决冲突。
- patch、文档、测试和配置是否一致。
- Skill 的最终流程要求是否完成。
- 用户明确禁止事项是否遵守。
- 是否仍有关键结论只有 self-reported evidence。

只有通过 Root Contract，系统才向主 harness 或用户报告任务完成。

#### Outcome Vector

账本保留原始结果，不立即压缩为单一 reward：

- node verifier accepted/rejected/inconclusive。
- root task 是否完成。
- deterministic checks 通过比例。
- 是否需要主 agent 大幅返工。
- 是否 reroute 或 escalate。
- input、output、delegated 和 returned token。
- latency、timeout 和执行状态。
- 用户 accept、override、retry 或明确负反馈。
- failure attribution。

原始 outcome 使用户以后可以切换“优先质量”“减少主模型 Token”“低延迟”或“保守修改”等策略，而不用重写历史。

#### 在线能力画像

第一版本只提供按 `WorkerArm x CapabilityDimension` 聚合的描述性统计。Future Work 可以维护：

```text
Beta(alpha, beta) for verified success
effective_sample_count
token and latency quantiles / EWMA
revision_count
escalation_count
last_model_version
```

由于系统只观察被选 worker 的结果，而不知道其他候选的反事实表现，这属于 partial bandit feedback。未来的安全探索应限制在只读、低风险、可验证节点；生产配置、凭证和不可逆操作不用于模型能力探索。

用户手动换 worker 是 override，不自动等同于原 route 失败；没有投诉也不能自动视为成功。能力画像必须依赖 verifier 或明确任务完成信号。

#### 三类置信度

C4 区分：

- **Decomposition confidence**：requirements、Skill、环境事实、依赖和 verifier 是否完整。
- **Routing confidence**：候选能力证据、样本量、分数差距和任务相似性是否足够。
- **Result confidence**：最终结果拥有 deterministic、grounded、semantic-reviewed 还是 self-reported 证据。

第一版使用等级和解释文本。样本积累后才能使用 reliability diagram、Brier score 或 ECE 检查 calibration；在此之前不能把 confidence 称为准确成功概率。

### 3.10 运行算法汇总

```text
INPUT: user request, active mode, available skills, repo/environment, worker registry

1. Build TaskSituation
   parse requirements, load Skill/mode constraints,
   collect minimal environment facts and worker capabilities

2. Define Root Contract
   create Requirement Ledger and final acceptance checks

3. Choose execution shape
   use fast path for atomic tasks; otherwise enter graph path

4. Build Task Contract Graph
   create bounded probe/work/verify/merge nodes
   require coverage, eligible workers and verifier contracts

5. Assign workers
   apply hard capability masks, then compare soft capability evidence,
   token, latency, risk and user preference

6. Execute ready nodes
   expose only node-visible contracts, context and artifacts

7. Verify each result
   run policy, grounding, executable and semantic checks

8. Replan failures
   classify attribution; add context, retry, reroute, split or escalate
   enforce attempt/depth/budget limits

9. Merge and root verify
   resolve conflicts, verify all requirements,
   write outcomes to ledger and return a compact result
```

## 4. 评估方案

### 4.1 主要指标

- Root task success。
- Requirement coverage。
- Delegated token 与 estimated main-model token saved。
- Worker token、latency 和 escalation rate。
- Invalid route rate：缺少硬能力、越权或无法验证。
- Coordination/context duplication overhead。
- Verifier false accept / false reject。
- User override/rework rate。
- Route confidence calibration：Brier、ECE 和 reliability。
- 在线策略启用后的 adaptation regret 或前后质量变化。

### 4.2 核心消融实验

1. Prompt-only decomposition vs TaskSituation grounding。
2. 独立 decomposition + routing vs routing-aware split test。
3. Post-hoc verifier vs verifier-by-construction。
4. Static declared profile vs online empirical profile。
5. Worker self-confidence vs evidence/posterior confidence。
6. No failure attribution vs attribution-aware profile update。
7. Full graph for all tasks vs inline fast path。

### 4.3 初始任务类型

- Skill-guided repository analysis and implementation。
- Long multi-deliverable documentation/research task。
- Plan Mode repository migration or feature plan。
- Log + code debugging with deterministic test evidence。
- Frontend task with screenshot/visual requirement and patch verification。
- Long-running training/evaluation task with async monitor and terminal callback。

### 4.4 第一版本验收重点

- 简单任务能够稳定走 fast path，不产生不必要的图调度开销。
- 复杂任务的每个 requirement 都映射到节点和 Root Contract。
- 不具备 hard capability 的 worker 不会被选中。
- patch worker 只能修改允许文件，并能生成可审查 artifact。
- verifier 失败能够触发有限调整，而不是被 worker 自报覆盖。
- 节点全部通过但 Root Contract 不完整时，系统不会错误报告完成。
- Dashboard/ledger 能够还原任务来源、路由理由、Token、验证和失败归因。

## 5. 相关工作与不足

### 5.1 ADaPT：按需递归拆解

[ADaPT](https://arxiv.org/abs/2311.05772) 先尝试直接执行，失败后由 planner 将任务递归拆成较短步骤，并根据 executor 能力动态增加分解深度。它支持 C4 的 fast path 和 as-needed decomposition。

其局限是使用 executor 自报 completed/failed 作为重要中间信号。Coding agent 更适合依赖测试、文件证据和权限检查，因此 C4 用 verifier contract 约束节点验收。

### 5.2 CodePlan：依赖驱动的动态计划

[CodePlan](https://arxiv.org/abs/2309.12499) 将 repository-level edit 表示为动态 plan graph，并在修改后根据 change impact 添加任务，最终使用 build、static analysis、type checker 或 tests 等 oracle 验证仓库。

C4 借鉴动态扩图、代码依赖和可执行 oracle，但第一版不实现完整语言级 dependency analysis，只记录新依赖和 change impact 作为重规划原因。

### 5.3 ParaManager：统一 action 与结构化反馈

[Small Model as Master Orchestrator / ParaManager](https://arxiv.org/abs/2604.17009) 将 agent 和 tool 统一为 action，并返回 `OK`、`PARSE_ERR`、`EXEC_ERR`、`TIMEOUT` 等状态。它说明多 harness 编排需要协议归一化和可恢复反馈。

其 SFT + RL 训练流程不适合作为 C4 的前置条件。C4 只借鉴 action contract、结构化状态与恢复循环。

### 5.4 GraphPlanner：联合 workflow 与模型选择

[GraphPlanner](https://arxiv.org/abs/2604.23626) 联合选择 planner/executor/summarizer 角色和模型，并使用 dynamic mask 排除无效 action。这支持 C4 将子任务形态、harness 和模型能力共同考虑。

GraphPlanner 依赖 PPO、离线数据和通用 QA utility。C4 第一版只采用图状态、联合考虑和 hard mask，不采用其训练方式。

### 5.5 在线路由与部分反馈

[BaRP](https://arxiv.org/abs/2510.07429) 将模型选择表示为带用户偏好的 contextual bandit；系统只观察被选模型的结果。[Online Multi-LLM Selection](https://arxiv.org/abs/2506.17670) 进一步研究多轮上下文、预算与 LinUCB 路由。

这与 C4 的本地运行数据相符，但初期样本稀疏，且失败可能来自任务契约、上下文或环境。因此 C4 先记录 outcome vector 和失败归因，再逐步引入安全在线适应。

### 5.6 不确定性与校准

[UCCI](https://arxiv.org/abs/2605.18796) 将 token-level uncertainty 校准为查询错误概率。[CP-Router](https://arxiv.org/abs/2505.19970) 使用 conformal prediction 进行训练自由的不确定性路由。

CLI harness 通常不暴露 logits，C4 不能假设这些信号始终存在。因此优先使用 verified history、候选差距、grounding coverage、verifier 强度和明确风险报告。

### 5.7 Harness 是一等变量

[Code as Agent Harness](https://arxiv.org/abs/2605.18747) 从 harness 层理解 planning、memory、tool use、feedback control、shared artifacts 和 verification。它支持 C4 路由完整 WorkerArm，而不是只记录 model name。

### 5.8 C4 的研究空白与自身不足

旧 landscape 中“现有方法都把请求视为原子请求”的说法过于宽泛。ADaPT、TDAG、CodePlan、ParaManager 和 GraphPlanner 均涉及动态拆解或 workflow generation。C4 更可信的研究空白是：

> 面向 coding-agent harness，由 Skill、交互模式和仓库状态共同 grounding，受能力、权限与验证契约约束的联合分解路由，并利用个人本地执行历史进行可解释适应。

目前方案仍有明显不足：

- Skill workflow 的自动抽取与冲突处理尚未解决。
- 第一版拆解主要依赖规则与 LLM 判断，不能保证全局最优。
- 开放式任务的 semantic verifier 仍可能昂贵且不稳定。
- 本地历史存在选择偏差和样本稀疏，不能直接视为模型真实能力。
- 文件并发、复杂 patch merge 和长期异步图仍需要更成熟的运行机制。
- 失败归因目前是可解释分类，但尚未证明具有严格因果正确性。

## 6. 总结与开放问题

### 6.1 总结

C4-ACD 的核心链路是：

```text
Task Situation Grounding
  -> Root Contract
  -> Fast Path or Contract Graph
  -> Hard Capability Filter
  -> Explainable Worker Assignment
  -> Bounded Worker Execution
  -> Verifier-Gated Acceptance
  -> Attribution-Aware Replanning
  -> Root Verification and Local History
```

它可以在一个 worker 的简单任务上退化为低开销 fast path，也能在多 harness、长任务和动态依赖场景中扩展成任务图。C4 的价值不在于声称首次进行任务拆解，而在于把任务理解、异构 harness 路由、权限、memory、artifact 和 verifier 放进同一条可运行、可追踪的闭环。

### 6.2 可检验的研究主张

1. **Task-situation grounding**：Skill、交互模式和 repository state 能否改善 coding task decomposition？
2. **Verifier-contracted decomposition**：在节点生成时定义 verifier，能否降低不可验证子任务和错误接受？
3. **Harness-aware joint decomposition-routing**：把 hard capability 和 harness toolchain 纳入拆解，是否优于先拆后路由？
4. **Attribution-aware online profiles**：本地 verified outcome 与失败归因能否在不离线训练的情况下改善 worker 分配？
5. **Explainable personal adaptation**：用户偏好与不确定性表达能否形成可理解、可控制的质量、Token、延迟和风险折中？

其中 verifier-contracted decomposition、harness-aware joint decomposition-routing 和 attribution-aware online profiles 的组合，可能构成 C4 最有辨识度的方法贡献。

### 6.3 Open Questions

- 如何稳定地从复杂 Skill 抽取 contract graph，而不误解隐式流程？
- 多个 Skill 同时触发时，如何合并流程并检测冲突？
- 架构设计、审美和开放式研究应如何定义成本可控的 semantic verifier？
- 任务的多标签能力向量应由规则、LLM、用户还是历史共同给出？
- 什么时候基础 scorecard 已经不足，需要升级为 contextual bandit？
- 如何更可靠地区分 decomposition error、worker error、missing context 和 environment failure？
- worker/harness 更新后，如何迁移历史 prior 而不产生负迁移？
- 同一文件被多个节点修改时，应优先串行、patch merge，还是重新划分任务边界？
- 如何让长期异步任务在正常结束和异常结束时都可靠返回主 Codex 会话？
