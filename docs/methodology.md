# Methodology Notes

日期：2026-06-22

## Method-Level Questions

实现前最重要的问题不是“用哪个库”，而是运行机制本身：

- 多 agent 同时运行时，共享 memory 如何读写？
- 主 agent、subagent、external harness 的职责怎么分？
- memory 应该是检索式的，还是主 agent 指定上下文为主？
- hooks 放在哪些决策点？
- verifier 如何判断便宜 worker 的输出可信？
- 哪些信息应该长期保存，哪些只属于本次 task？

下面是当前推荐的方法设计。

## Memory Design: Multi-Layer Graph Memory

> 详细设计见 [memory.md](memory.md)

Shared memory 不应该只有一个”向量库”。对 coding-agent 协作来说，更合理的是**轻量分层图**：

```text
Private Orchestrator State（主 harness 私有状态，可不落库）
  -> Worker Task Node（每次委托的核心节点）
      -> Context Pack（可选背景包）
          -> File / Artifact Node（真实文件、日志、patch 等）
```

### Worker Task Node

这是 worker 真正接收的任务节点，是系统里最重要的实体。

包含：

- worker-visible goal
- assigned harness（claude_cli / qwen_subagent 等）
- allowed files / context packs
- constraints（read-only / patch / no network）
- status
- worker output / proposed facts / proposed patches
- token usage / verifier result

### Context Pack

可选背景包。当 worker 缺背景时，主 harness 创建或选择一个 context pack，而不是把全部 memory 塞过去。

包含：

- 简短说明
- 已验证事实
- 相关模块说明
- 项目约定
- 历史失败/尝试记录
- 指向具体 artifact/file 的引用

### File / Artifact Node

表示真实材料：源代码、配置、日志、测试输出、patch proposal、worker raw output。一个 file node 可以连接多个 worker node，天然是图结构。

### 两个视图

原”双轨”概念保留为图的两个视图：
- **Worker Task Nodes + Verified Facts + Routing Status** ≈ 原 Shared Task Memory
- **Context Packs + File/Artifact Nodes + Raw Outputs** ≈ 原 Artifact Memory

即：**双轨是概念分类，图是实现结构。**

建议分两层：

1. Metadata index
   - artifact id
   - type: log / transcript / patch / summary / command_output / review
   - path
   - producer agent
   - task id
   - timestamp
   - short summary
   - tags
   - sensitivity level
   - verification status

2. Raw artifact
   - 原始 worker summary
   - 裁剪后的日志
   - patch 文件
   - 命令输出
   - 对话 transcript 摘要

主 agent 默认只看 metadata 和少量 verified facts。只有需要时才打开 raw artifact。

## Why Not Pure Similarity Retrieval

你的判断是对的：在这个项目里，subagent/slave 多数时候不应该自己靠相似度检索到处找 memory。

原因：

- coding task 往往有明确路径、日志、diff、命令输出。
- 主 agent 更适合决定“这个子任务需要哪些材料”。
- subagent 自己检索太自由，容易引入不相关 memory，增加成本和错误。
- memory 是控制通道，不只是知识库；错误检索可能改变 agent 行为。

因此第一版建议：

- 主 agent/router 选择任务相关 memory。
- subagent 接收一个明确的 context bundle。
- subagent 可以请求更多 artifact，但默认不自由搜索全局 memory。
- similarity search 只作为辅助召回，不作为默认上下文注入机制。

更准确地说，第一版采用 **directed memory access**：

> 主 agent 指定上下文，memory 系统提供候选，verifier/策略层决定是否注入。

后续可以加入 semantic retrieval，但必须加 memory gate：

- 是否同 repo。
- 是否同 task type。
- 是否同路径或模块。
- 是否 verified。
- 是否过期。
- 是否敏感。

## Concurrency Model

### Initial Version: Single Writer, Few Readers

第一版不需要复杂分布式一致性。建议采用：

- SQLite。
- WAL mode。
- 一个 orchestrator/main agent 作为唯一写协调者。
- subagent 不直接写 shared task memory。
- subagent 返回 result，由 main orchestrator/verifier 写入 memory。

这样可以避免多个 agent 同时写出冲突事实。

读写规则：

- Main agent / orchestrator：read + write。
- Subagent：read-only context bundle，不直接访问完整 memory。
- External harness：只拿到任务包，不拿到数据库写权限。
- Verifier：生成 memory_facts，但由 orchestrator commit。

### Later Version: Controlled Multi-Writer

如果后续支持多个 worker 直接写 memory，需要引入：

- SQLite transaction。
- optimistic locking。
- memory item version。
- writer agent id。
- provenance。
- conflict resolution。
- fact status: proposed / verified / rejected / stale。

但这个不要一开始做。第一版先保持“worker 提案，orchestrator 入库”。

## Memory Item Lifecycle

建议每条 memory item 有生命周期：

1. Proposed：worker 提出。
2. Verified：verifier 或主 agent 接受。
3. Used：被后续任务引用过。
4. Superseded：被新事实替代。
5. Stale：过期但保留。
6. Rejected：明确错误。

只有 Verified 和少量高置信 Proposed 可以进入 shared task memory。

## Hooks Design

Hooks 不是插件噱头，而是运行机制的决策点。

### pre_route

输入：用户任务、repo metadata、budget。

职责：

- 判断任务类型。
- 估计难度。
- 检查风险。
- 读取少量 memory metadata。
- 决定是否拆任务。

输出：RouteDecision draft。

### post_route

输入：RouteDecision。

职责：

- 记录为什么这样路由。
- 写入 ledger。
- 如果风险过高，要求用户确认。

### pre_delegate

输入：子任务、backend、context bundle。

职责：

- 裁剪上下文。
- 检查敏感信息。
- 设置权限：read-only / worktree / no-network。
- 设置 timeout/budget。
- 生成 worker prompt。

### post_delegate

输入：WorkerResult。

职责：

- 保存 raw artifact。
- 抽取候选 facts。
- 记录 cost。
- 标记失败、超时或越权。

### post_verify

输入：VerificationResult。

职责：

- 接受结果。
- 拒绝结果。
- 升级强模型。
- 写入 verified memory。
- 更新 routing policy 的统计信息。

## Verifier Design

Verifier 第一版不要太聪明。它应该先做可解释、可调试的检查。

### Structural Verification

检查 worker 输出是否符合格式：

- 有 summary。
- 有 evidence。
- 有 next_steps。
- 有 uncertainty/risk。
- 没有超长 transcript。

### Grounding Verification

检查 evidence 是否落地：

- 文件是否存在。
- 行号是否合理。
- 日志片段是否真的包含相关关键词。
- patch 是否能 apply。
- 命令摘要是否和 artifact 对应。

### Policy Verification

检查是否越权：

- read-only task 是否修改文件。
- 是否访问未授权路径。
- 是否请求或输出密钥。
- 是否试图执行危险命令。

### Quality Verification

第一版可以规则化：

- 结论是否和 evidence 对齐。
- 是否给出可执行 next step。
- 是否承认信息不足。
- 是否避免没有证据的强判断。

后续再加入 strong-model verifier：

- cheap worker 先做。
- strong verifier 抽样检查。
- 不通过则升级重做。

## Task Decomposition Method

> 完整方法见 [decompose.md](decompose.md)。该文档定义 Task Situation、
> Adaptive Contract Graph、能力约束路由、verifier contract 和在线能力画像。

下面几类 coding task pattern 保留为原生 decomposition operators 的简单示例，
不再作为 C4 支持任务类型的边界：

### Log Failure Analysis

拆法：

- 找最新日志。
- 找 error/warn/traceback/OOM/timeout。
- 总结候选根因。
- 给下一步检查。

### Code Search

拆法：

- 找入口。
- 找调用链。
- 找类似实现。
- 标出风险文件。

### PR Review

拆法：

- correctness。
- tests。
- security。
- maintainability。

每个子任务都必须满足：

- 输入材料明确。
- 输出可验证。
- 低风险。
- 可以独立完成。

## Difference From Existing Memory Work

已有 memory 工作很多，不能假装从零开始。

相关方向：

- Mem0：长期 agent memory，强调从会话中抽取、合并和检索显著信息，并报告显著 token/cost/latency 降低。
- Zep/Graphiti：时间感知知识图谱 memory，强调跨会话、时间关系和企业数据。
- Letta/MemGPT：把短期/长期 memory 管理放进 agent runtime。
- LangGraph memory：为 agent workflow 提供 state、checkpoint、store。
- Collaborative Memory / GateMem：研究多用户、多 agent shared memory 的权限、访问控制和遗忘。
- Intrinsic Memory Agents：为异构 multi-agent 系统维护结构化、角色对齐 memory。

我们的差异点不应该是“我们也有 memory”，而应该是：

1. 面向 coding task，而不是通用聊天记忆。
2. memory 服务于 task routing、delegation、verification，而不只是个性化。
3. 采用多层图：worker task node + context pack + artifact node。
4. 默认 directed memory access，而不是让每个 subagent 自由 similarity retrieval。
5. worker 不直接写共享事实，先提案，再由 verifier/orchestrator commit。
6. memory 和 cost ledger 绑定，用于学习哪些任务值得委托、哪些需要升级。

这个角度有研究空间：它不是单纯 RAG，也不是单纯长期记忆，而是 **multi-agent coding workflow memory**。

## Recommended Initial Policy

为了尽快跑通又不把问题做复杂，初始策略建议：

- 只允许一个 subagent 并行运行。
- memory 用 SQLite。
- orchestrator 单写。
- subagent 不直接访问 DB。
- subagent 只拿 context bundle。
- artifact memory 保存原始输出，shared task memory 只存 verified fact。
- 不启用全局相似度检索。
- verifier 先规则化。
- strong-model verifier 作为可选升级。

这个策略看起来保守，但有利于把方法做清楚。等单 worker 闭环稳定，再打开并发、多 writer、semantic retrieval 和跨 harness memory。

## Research Questions

后续可以围绕 memory 做更有研究味道的问题：

- Directed memory access 是否比 naive similarity retrieval 更省 token、更少错误？
- Dual-track memory 是否能减少 context pollution？
- Worker-proposed / verifier-committed memory 是否能提升事实可靠性？
- Cost ledger 能否反过来优化 routing policy？
- 对 coding tasks，哪些 memory 类型最有复用价值？
- 多 harness 协作时，memory provenance 如何影响 verifier 决策？
