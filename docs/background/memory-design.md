# Shared Memory 设计文档（历史版本）

> **注意**：此文档为早期设计版本，已由 [docs/memory.md](../memory.md) 中的**多层图**设计取代。保留此文档供参考。

**日期**: 2026-06-23
**状态**: 已被多层图设计取代
**最新版本**: 见 [docs/memory.md](../memory.md)

## 1. 设计目标

在 cost-aware coding-agent router 中，shared memory 需要同时服务三个角色：

1. **主 agent (Codex)**：需要知道子任务的整体进展、已确认事实、当前阻塞点
2. **Worker (Claude CLI / Qwen subagent)**：需要接收精简的上下文 bundle，不自己检索
3. **Verifier**：需要验证 worker 输出，决定是否接受、拒绝或升级

核心约束：
- Worker 不直接写共享事实（先提案，再确认）
- 主 agent 指定上下文，不靠 worker 自己检索
- Memory 服务于 routing/delegation/verification，不只是存储

## 2. 多层图架构（更新）

> 详细设计见 [docs/memory.md](../memory.md)

核心结构是四层轻量分层图：

```text
Private Orchestrator State（主 harness 私有状态，可不落库）
  -> Worker Task Node（每次委托的核心节点）
      -> Context Pack（可选背景包）
          -> File / Artifact Node（真实文件、日志、patch 等）
```

原"双轨"概念保留为图的两个视图：
- **Worker Task Nodes + Verified Facts + Routing Status** ≈ 原 Shared Task Memory
- **Context Packs + File/Artifact Nodes + Raw Outputs** ≈ 原 Artifact Memory

即：**双轨是概念分类，图是实现结构。**

## 3. Directed Memory Access（受控访问）

**核心原则**：主 agent/router 指定上下文，memory 系统提供候选，verifier/策略层决定是否注入。

**流程**：
```
主 agent 收到用户任务
  → Router 判断任务类型和难度
  → 主 agent 从图中读取相关的 worker task nodes 和 verified facts
  → 主 agent 组装 context pack（goal + paths + relevant facts）
  → 发给 worker
  → Worker 执行任务，返回结构化结果
  → Verifier 验证结果
  → 如果接受：proposed facts → verified facts（写入图节点）
  → Worker 原始输出 → artifact node
  → 主 agent 只读取 verified summary + key facts
```

**为什么不默认相似度检索**：
- Coding task 有明确路径、日志、diff、命令输出
- 主 agent 更适合决定"这个子任务需要哪些材料"
- Subagent 自己检索太自由，容易引入不相关 memory，增加成本和错误
- Memory 是控制通道，不只是知识库

## 4. 读写规则

| 角色 | 能读什么 | 能写什么 |
|------|---------|---------|
| 主 harness | 全部 | 全部 |
| Worker | 自己的 task node、允许的 context pack、允许的 file/artifact | 只能写自己的 output/proposal |
| Verifier | worker 输出、证据文件、必要控制信息 | verifier result / accepted facts |
| Router | 任务元数据、ledger、历史结果 | worker node / routing decision |

关键规则：**worker 不直接写 shared facts，也不直接提交真实文件修改。** Worker 只能 propose（proposed fact / proposed patch / progress event / final result），由 verifier / main harness 决定是否 commit。

## 5. Memory Item 生命周期

```
Proposed (worker 提出)
  ↓
Verified (verifier 或主 agent 接受)
  ↓
Used (被后续任务引用过)
  ↓
Superseded (被新事实替代) / Stale (过期但保留) / Rejected (明确错误)
```

只有 Verified 和少量高置信 Proposed 可以作为 verified facts 被后续 worker 引用。

## 6. 与现有工作的差异

| 维度 | MetaGPT | MemGPT | Zep/Graphiti | 本项目 |
|------|---------|--------|-------------|--------|
| Memory 形式 | Message pool | 层次化 context | 时间感知图 | 多层分层图（task/context/artifact） |
| 访问方式 | 全局可见 | 相似度检索 | 图查询 | Directed access |
| 写入方式 | 直接写入 | 直接写入 | 自动抽取 | Worker 提案 → Verifier 确认 |
| 跨 harness | 否 | 否 | 否 | 是 |
| 成本感知 | 否 | 否 | 否 | 是（ledger 联动） |
| 面向场景 | 通用 SE | 长对话 | 企业知识 | Coding task cost routing |

## 7. Research Questions

- Directed memory access 是否比 naive similarity retrieval 更省 token、更少错误？
- 多层图结构是否能减少 context pollution（相比单一 message pool）？
- Worker-proposed / verifier-committed memory 是否能提升事实可靠性？
- Cost ledger 能否反过来优化 routing policy？
- 对 coding tasks，哪些 node 类型最有复用价值？
- 多 harness 协作时，memory provenance 如何影响 verifier 决策？
