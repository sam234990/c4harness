# 核心方法 Idea 整合

**日期**: 2026-06-24
**来源**: 4 个模块的 idea 探索（Task Router / Delegator / Verifier / Shared Memory）
**方法**: lit-survey → idea-gen → idea-screen → idea-refine 全流程

## Executive Summary

经过对 4 个核心模块的文献调研（60+ 篇论文）和系统化 idea 探索（44 个原始想法 → 过滤 → 深度评审 → 精炼），我们提炼出 **6 个独立但可组合的核心方法**。这些方法共同构成一个完整的 cost-aware coding-agent router 系统，但每个方法也可以独立发表。

**最关键发现**：现有工作在三个方向上存在结构性空白——(1) 没有人在 agent harness 级别做路由，(2) 没有人为 multi-agent coding memory 设计两步确认机制，(3) 没有人让验证器的强度与置信度自适应匹配。这三个空白恰好对应我们系统的核心创新。

---

## 方法全景

```
用户任务
  │
  ▼
┌──────────────────────────────────────────────┐
│  方法 1: Harness-Level Routing                │
│  选择 Codex / Claude CLI / OpenCode / Main    │
│                                               │
│  方法 2: Joint Decomposition-Routing          │
│  复杂任务拆分 + 子任务路由                      │
└──────────────────┬───────────────────────────┘
                   │
                   ▼
┌──────────────────────────────────────────────┐
│  方法 3: Adaptive Fallback Chain              │
│  后端失败时自动降级/切换                        │
│                                               │
│  方法 4: Task-Backend Affinity Learning       │
│  从历史数据学习任务-后端匹配度                   │
└──────────────────┬───────────────────────────┘
                   │
                   ▼
┌──────────────────────────────────────────────┐
│  方法 5: CAVE (Confidence-Adaptive Verifier)  │
│  置信度感知的验证强度动态调整                    │
│                                               │
│  方法 6: Two-Phase Commit Memory              │
│  Worker 提议 → Verifier 确认 → Memory 提交     │
└──────────────────────────────────────────────┘
```

---

## 方法 1: Harness-Level Routing

**一句话**: 首次在 agent harness 级别建模路由问题——不是选模型，而是选"用哪个 agent 执行这个任务"。

**核心主张**: 不同 agent harness（Codex、Claude CLI、OpenCode）有不同的工具链、上下文窗口、成本结构和擅长领域。Harness-aware 路由比 model-level 路由有更大的降本空间。

**关键机制**:
- 定义 harness 能力空间：工具链覆盖、上下文窗口、成本/token、推理能力、代码执行能力
- 提取任务-harness 匹配特征：任务类型（log/code/patch）、文件数量、读写模式、风险等级
- 学习路由策略：规则路由 → 轻量分类器 → 上下文 bandit

**实验设计**: 构建首个异构 agent harness 路由基准，覆盖 Codex/Claude CLI/OpenCode，对比 static routing / learned routing / oracle routing。

**风险**: LOW | **He 分数**: 15/20 | **审稿人评级**: Weak Accept (6.7)

---

## 方法 2: Joint Decomposition-Routing

**一句话**: 首次将任务分解和路由作为联合优化问题——不是先拆再路由，而是拆的时候就知道谁来做。

**核心主张**: 任务拆分和子任务路由应该联合优化。先拆再路由会丢失"哪个子任务适合哪个后端"的信息；联合优化可以在拆分时就考虑后端能力。

**关键机制**:
- 任务分解时同时评估每个子任务与各后端的匹配度
- 子任务粒度受后端能力约束（太小的任务不值得委托）
- 依赖关系决定并行/串行执行

**实验设计**: 在 SWE-bench 任务上对比 sequential (decompose → route) vs. joint optimization。

**风险**: HIGH | **He 分数**: 15/20 | **审稿人评级**: Weak Accept (6.7)，Theoretician 给 Strong Accept

---

## 方法 3: Adaptive Fallback Chain

**一句话**: Agent 后端的失败是常态（成功率 7-50%），需要智能降级链而非简单重试。

**核心主张**: 现有系统假设通信总是成功的，但实际上后端失败是大概率事件。Adaptive Fallback Chain 根据失败类型（超时/崩溃/格式错误/能力不足）选择不同的恢复策略。

**关键机制**:
- 失败模式分类体系：Timeout / Crash / FormatError / CapabilityGap / RateLimit / PartialSuccess
- 失败类型 → 恢复策略映射：
  - CapabilityGap → 降级到更强后端
  - FormatError → 调整 prompt 重试
  - Timeout → 分解任务后重试
  - RateLimit → 等待或切换
- 从历史数据学习每种失败类型的最佳恢复策略

**实验设计**: 在真实 CLI 调用 trace 上对比 retry-all / random-fallback / learned-fallback 策略。

**风险**: LOW | **He 分数**: 17/20 | **审稿人评级**: Strong Accept (7.0)

---

## 方法 4: Task-Backend Affinity Learning

**一句话**: 从历史路由数据中学习任务-后端匹配度，用上下文 bandit 做在线路由优化。

**核心主张**: 任务和后端之间的匹配度不是静态的，而是随任务特征、后端状态、上下文变化的。Contextual bandit 可以在线学习这种匹配度。

**关键机制**:
- 任务特征向量：类型、复杂度、文件数、语言、读写模式
- 后端特征向量：当前负载、历史成功率、成本、延迟
- 上下文 bandit：LinUCB / NeuralUCB 在线学习最优匹配
- 冷启动：用方法 1 的规则路由作为初始策略

**实验设计**: 在累积路由数据上对比 epsilon-greedy / LinUCB / Thompson Sampling。

**风险**: MEDIUM | **He 分数**: 16/20 | **审稿人评级**: Accept (6.7)

---

## 方法 5: CAVE (Confidence-Adaptive Verification Escalation)

**一句话**: 验证强度应该与置信度匹配——高置信度直接接受，低置信度升级到强模型验证。

**核心主张**: 固定验证强度导致两种低效：(1) 对高置信度正确输出过度验证，浪费计算；(2) 对低置信度错误输出验证不足，污染 memory。CAVE 用置信度校准来动态调整。

**关键机制**:
- 轻量验证器（规则 + 小模型）计算置信度 $s \in [0,1]$
- 高置信度 ($s > \theta_h$): 直接接受
- 中置信度 ($\theta_l < s \leq \theta_h$): 升级到中等模型
- 低置信度 ($s \leq \theta_l$): 升级到强模型或拒绝
- 阈值通过验证集上的成本-质量权衡优化

**实验设计**: SWE-bench 上 4 种条件对比（规则验证 / 强模型验证 / CAVE / 无验证）。预期：事实错误率从 15-25% 降到 3-8%。

**风险**: MEDIUM | **He 分数**: 17/20 | **审稿人评级**: Weak Accept (7.0)

---

## 方法 6: Two-Phase Commit Memory

**一句话**: Shared memory 需要事务保证——Worker 提议事实，Verifier 确认后才提交，防止错误事实级联污染。

**核心主张**: 现有多 agent memory（MetaGPT/MemGPT/MACLA）允许 agent 直接写入，但 worker 产生的 facts 中有 15-25% 是错误的。这些错误 facts 会被后续任务引用，导致级联失败。Two-Phase Commit 将写入分为"提议"和"确认"两步。

**关键机制**:
- Phase 1 (Propose): Worker 返回结果时，提取 proposed facts（fact text, evidence ref, source agent, confidence）
- Phase 2 (Commit): Verifier pipeline 检查每条 fact：
  - Contradiction check: 是否与已有 facts 矛盾？
  - Grounding check: evidence 是否真实存在？
  - Consistency check: 是否与任务上下文一致？
- 只有通过验证的 facts 才作为 verified facts 写入图节点
- 被拒绝的 facts 记录到 rejection log（可用于训练 verifier）

**实验设计**: SWE-bench 上 4 种条件（direct write / post-hoc filter / two-phase commit / no memory）。预期：事实错误率从 15-25% 降到 3-8%，任务成功率提升 3-8%。

**风险**: LOW | **He 分数**: 16/20 | **审稿人评级**: Weak Accept (7.0)

---

## 组合策略

### 策略 A: 一篇大论文（系统论文）

将 6 个方法整合成一个完整的 cost-aware coding-agent router 系统，投 MLSys / OSDI / SOSP。

**优势**: 完整性最强，story 最大
**风险**: 工程量大，reviewer 可能觉得"每个贡献都不够深"

### 策略 B: 两篇互补论文（推荐）

**论文 1 (系统论文)**: 方法 1 + 3 + 4 — "Routing and Delegation"
- Harness-Level Routing + Adaptive Fallback + Affinity Learning
- 投 MLSys / NeurIPS Systems Track
- Story: "首次在 agent harness 级别做 cost-aware routing，含智能降级和在线学习"

**论文 2 (方法论文)**: 方法 5 + 6 — "Verification and Memory"
- CAVE + Two-Phase Commit
- 投 NeurIPS / ICSE
- Story: "Multi-agent coding memory 需要置信度自适应验证和事务保证"

方法 2 (Joint Decomposition-Routing) 可以作为论文 1 的扩展或独立短论文。

### 策略 C: 三篇渐进论文

1. **论文 1** (LOW risk): 方法 1 + 6 — 建立基础设施（routing + memory commit）
2. **论文 2** (MEDIUM risk): 方法 3 + 5 — 加入智能（fallback + adaptive verification）
3. **论文 3** (HIGH risk): 方法 2 + 4 — 理论提升（joint optimization + affinity learning）

---

## 优先级排序

| 优先级 | 方法 | 理由 |
|--------|------|------|
| 1 | Two-Phase Commit (方法 6) | 验证系统设计的核心创新，LOW risk，实验可快速出结果 |
| 2 | Harness-Level Routing (方法 1) | 建立基础设施，为后续所有方法提供基础 |
| 3 | CAVE (方法 5) | 与方法 6 互补，形成"Verifier 系列" |
| 4 | Adaptive Fallback Chain (方法 3) | 解决实际工程问题，LOW risk |
| 5 | Task-Backend Affinity Learning (方法 4) | 在方法 1 基础上做数据驱动优化 |
| 6 | Joint Decomposition-Routing (方法 2) | HIGH risk，但理论 novelty 最大 |

---

## 文献基础

本整合基于以下文献调研（详见 `docs/landscape-*.md`）：

| 模块 | 论文数 | 关键 Gap |
|------|--------|---------|
| Task Router | 12 | 请求级→任务级路由、harness 选择、cost ledger 闭环 |
| Delegator | 18 | 跨 harness 协议、统一抽象、失败处理 |
| Verifier | 18 | 中间结果验证、两步提交、置信度升级 |
| Shared Memory | 18 | 多层图设计、directed access、事务保证 |

总计分析 66 篇论文，识别 29 个研究空白，生成 44 个原始想法，最终精炼为 6 个核心方法。
