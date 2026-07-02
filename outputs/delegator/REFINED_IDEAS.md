# Delegator Module: Refined Top 2 Ideas

**深度精炼**: 对排名前 2 的想法进行完整的研究设计

---

## Refined Idea 1: Adaptive Fallback Chain for Backend Failures

### 1. Problem Anchor

**核心问题**: agent 后端的失败是常态而非异常。

现有数据表明：多步工具调用的成功率仅 7-47% [P11]，MCP 任务的成功率不足 50% [P16]。当 Delegator 将任务委派给后端（如 `claude -p`、`opencode run`）时，失败是大概率事件。然而，现有设计要么假设通信总是成功的 [P07, P08]，要么仅提出简单的重试策略 [P13]。

**问题形式化**:
- 给定任务 $t$，后端集合 $B = \{b_1, b_2, ..., b_n\}$，每个后端有成功率 $p_i(t)$ 和成本 $c_i(t)$
- 目标：选择后端序列 $\sigma = (b_{i_1}, b_{i_2}, ...)$，使得在预算约束下最大化任务成功率
- 挑战：$p_i(t)$ 是未知的，需要从历史数据中估计；不同后端的失败模式不同，需要不同的处理策略

**为什么这个问题重要**:
- 如果 Delegator 不能可靠地处理失败，整个 cost-aware router 的价值将大打折扣
- 简单重试同一后端往往无效——如果后端 $b_1$ 因为能力不足而失败，重试 $b_1$ 不会成功
- 降级到其他后端需要考虑任务格式适配、成本差异、和能力匹配

### 2. Core Contribution

**贡献 1: Agent 后端失败模式分类体系**

基于对 CLI 后端（`claude -p`、`opencode run`）的实际观察，定义以下失败模式分类：

| 错误类型 | 描述 | 示例 | 恢复策略 |
|---------|------|------|---------|
| Timeout | 后端超时未返回 | 复杂任务超出时间限制 | 缩短任务/分解任务后重试 |
| Crash | 后端进程异常退出 | 内存不足、依赖缺失 | 重试同一后端或降级 |
| FormatError | 输出格式不符合预期 | JSON 解析失败、缺少必要字段 | 重试并调整 prompt |
| CapabilityGap | 后端能力不足以完成任务 | 不支持特定编程语言/框架 | 降级到更强后端 |
| PermissionDenied | 权限不足 | 文件系统访问被拒绝 | 切换到高权限后端 |
| RateLimit | 后端限流 | API 调用频率超限 | 等待后重试或切换后端 |
| PartialSuccess | 部分完成 | 生成了代码但有语法错误 | 补充任务后重试 |

**贡献 2: 自适应降级链算法**

```
Algorithm: AdaptiveFallbackChain
Input: task t, backend set B, cost ledger L, budget constraint β
Output: execution result r

1. Compute affinity scores: for each b in B, score(b, t) = f(L, t, b)
2. Sort backends by score: B_sorted = sort(B, by=score)
3. Initialize circuit_breakers: CB[b] = {failures: 0, state: CLOSED}
4. for b in B_sorted:
5.   if CB[b].state == OPEN: continue  // 跳过断路的后端
6.   if cost(b, t) > remaining_budget(β): continue  // 预算不足
7.   Adapt task format: t' = adapt(t, b)  // 适配后端格式
8.   result = dispatch(b, t')
9.   if result.status == SUCCESS:
10.    Update L with success record
11.    return result
12.  else:
13.    CB[b].failures += 1
14.    if CB[b].failures >= threshold: CB[b].state = OPEN
15.    Update L with failure record
16.    Classify error: error_type = classify(result.error)
17.    Adapt strategy: apply_recovery(error_type, t, b)
18. return FAILURE(all backends exhausted)
```

**贡献 3: Circuit Breaker 的任务感知扩展**

传统 circuit breaker 仅基于失败率判断是否断路。我们提出任务感知的 circuit breaker：
- 不同任务类型的断路阈值不同——简单任务的容忍度更低（快速失败更重要），复杂任务的容忍度更高（值得等待）
- 断路恢复策略考虑任务类型——对于某类任务断路的后端，可能对另一类任务仍然可用
- 引入"半开"状态的探索机制——定期尝试已断路的后端，用少量探测请求评估是否恢复

### 3. Experimental Design

**实验 1: 错误分类实证研究**
- 数据来源: 收集 1000+ 次 CLI 后端调用的执行日志
- 方法: 手动标注错误类型，分析各类型的分布和特征
- 指标: 错误类型分布、各类型的可恢复性、平均恢复时间
- 预期结果: 建立错误类型的先验分布，为自适应策略提供基础

**实验 2: 降级链策略对比**
- 基线:
  - Random: 随机选择后端
  - Fixed: 固定优先级降级（始终按同一顺序尝试）
  - CostOnly: 始终选择最便宜的后端
  - SuccessRateOnly: 始终选择历史成功率最高的后端
- 方法: 在 Live API-Bench [P11] 上运行，记录任务成功率、总成本、平均延迟
- 指标: 任务成功率、平均成本、延迟分布、降级次数
- 预期结果: Adaptive Fallback Chain 在成功率上接近 SuccessRateOnly，但成本显著更低

**实验 3: Circuit Breaker 效果评估**
- 方法: 对比有/无 circuit breaker 的降级链性能
- 指标: 无效重试次数、总执行时间、成本节省
- 预期结果: Circuit breaker 减少 30-50% 的无效重试

**实验 4: 任务感知断路阈值消融**
- 方法: 对比固定阈值 vs 任务感知阈值
- 指标: 不同任务类型上的成功率差异
- 预期结果: 任务感知阈值在复杂任务上提升成功率，在简单任务上降低延迟

### 4. Expected Results

| 指标 | Random | Fixed | CostOnly | SuccessRateOnly | Adaptive (ours) |
|------|--------|-------|----------|-----------------|-----------------|
| 任务成功率 | ~30% | ~45% | ~35% | ~55% | ~52% |
| 平均成本 (normalized) | 1.0 | 1.2 | 0.7 | 1.8 | 1.0 |
| 平均延迟 (normalized) | 1.0 | 1.5 | 0.8 | 2.0 | 1.1 |
| 无效重试次数 | 高 | 中 | 高 | 低 | 低 |

核心预期: Adaptive Fallback Chain 在成功率上接近 SuccessRateOnly（~52% vs ~55%），但成本降低 44%（1.0 vs 1.8），实现成本-成功率的最优权衡。

### 5. Positioning

**与现有工作的区别**:

| 维度 | Uno-Orchestra [P15] | LDP [P13] | Ours |
|------|---------------------|-----------|------|
| 后端类型 | 同框架不同模型 | 异构 agent | 异构 harness |
| 失败处理 | 假设成功 | 简单重试 | 自适应降级链 |
| 成本优化 | RL 联合训练 | 无 | 启发式 + 在线学习 |
| 理论基础 | RL | 博弈论 | 容错系统 + 在线学习 |

**论文定位**: 系统 + 算法论文
- 核心贡献: (1) agent 后端失败模式分类体系；(2) 自适应降级链算法；(3) 任务感知 circuit breaker
- 故事线: "后端失败是常态——我们需要智能降级而非盲目重试"
- 目标会议: NeurIPS Systems Track / MLSys / EMNLP Industry Track

---

## Refined Idea 2: Task-Backend Affinity Learning

### 1. Problem Anchor

**核心问题**: 不同任务与不同后端之间存在可学习的匹配关系，但现有 Delegator 缺乏数据驱动的选择机制。

Uno-Orchestra [P15] 证明了选择性委派的价值（77.0% macro pass@1，比最强基线高 16%，成本低一个数量级），但其训练在同一框架内进行，不涉及异构 harness 的成本差异。在 Delegator 的实际场景中，后端 $b_1$（如 Codex 子 agent）可能在简单任务上性价比最高，而后端 $b_2$（如 Claude CLI）可能在复杂任务上成功率最高。这种任务-后端亲和性是可学习的。

**问题形式化**:
- 给定任务 $t$（用特征向量 $\phi(t)$ 表示），后端集合 $B = \{b_1, b_2, ..., b_n\}$
- 每个后端 $b_i$ 对任务 $t$ 有未知的成功率 $p_i(t)$ 和成本 $c_i(t)$
- 目标：学习一个策略 $\pi: \phi(t) \rightarrow b_i$，最大化累积奖励 $\sum_t [r(t) - \lambda \cdot c(t)]$
- 约束：需要在线学习（不能离线训练后部署），因为后端能力会随时间变化

**为什么这个问题重要**:
- 启发式策略（如"始终选择最便宜的"或"始终选择最强的"）无法适应任务多样性
- 纯随机选择浪费资源——如果任务 $t$ 在后端 $b_1$ 上成功率 80%，在 $b_2$ 上成功率 20%，随机选择的期望成功率只有 50%
- 数据驱动的选择可以持续改进，随着执行数据积累越来越准确

### 2. Core Contribution

**贡献 1: 任务特征提取方案**

从任务描述中提取以下特征：

| 特征类别 | 特征 | 提取方法 |
|---------|------|---------|
| 任务类型 | bug_fix, feature, refactor, test, docs | LLM 分类 |
| 代码语言 | python, javascript, rust, ... | 正则匹配 |
| 复杂度估计 | simple, medium, complex | 代码行数 + 依赖深度 |
| 工具需求 | file_read, file_write, shell, browser | 任务描述分析 |
| 上下文依赖 | low, medium, high | 引用的文件/模块数量 |

特征向量: $\phi(t) = [type\_onehot, lang\_onehot, complexity, tool\_needs, context\_deps]$

**贡献 2: Contextual Bandit 模型**

将后端选择建模为 contextual bandit 问题：
- 上下文: 任务特征 $\phi(t)$
- 动作: 选择后端 $b_i$
- 奖励: $r(t) = \mathbb{1}[\text{success}] - \lambda \cdot \text{normalized\_cost}(t)$

使用 LinUCB 算法:
- 对每个后端 $b_i$ 维护线性模型: $\hat{r}_i(t) = \phi(t)^T \theta_i$
- 选择后端: $b^* = \arg\max_i [\hat{r}_i(t) + \alpha \sqrt{\phi(t)^T A_i^{-1} \phi(t)}]$
- 其中 $A_i = \sum_{t: b_t = b_i} \phi(t)\phi(t)^T + I$ 是设计矩阵

**贡献 3: 冷启动策略**

项目早期缺乏执行数据，需要冷启动策略：
- Phase 1（前 100 次委派）: 使用 Capability Cards [Idea 2] 作为先验，均匀探索所有后端
- Phase 2（100-500 次委派）: 使用 LinUCB 的探索-利用平衡，$\alpha$ 从高到低衰减
- Phase 3（500+ 次委派）: 以利用为主，$\alpha$ 保持在较低水平

**贡献 4: 后端能力漂移检测**

后端能力可能随时间变化（模型更新、配置变更、网络波动）。引入漂移检测机制：
- 维护滑动窗口（最近 N 次委派）的成功率统计
- 当窗口内成功率与历史成功率的差异超过阈值时，触发"重置"——增加探索权重
- 使用 CUSUM 或 Page-Hinkley 检测算法

### 3. Experimental Design

**实验 1: 任务特征有效性验证**
- 数据来源: 收集 500+ 次委派的执行记录
- 方法: 用任务特征预测后端成功率，评估预测准确率
- 指标: AUC-ROC、F1-score
- 预期结果: 任务类型和复杂度是最强预测特征，AUC > 0.7

**实验 2: LinUCB vs 基线对比**
- 基线:
  - Random: 随机选择后端
  - Greedy: 始终选择当前估计最优的后端（无探索）
  - EpsilonGreedy: 以 $\epsilon$ 概率随机探索
  - Oracle: 事后选择最优后端（上界）
- 方法: 在收集的执行数据上模拟在线学习过程
- 指标: 累积奖励、任务成功率、平均成本、regret（与 Oracle 的差距）
- 预期结果: LinUCB 的累积 regret 最低，接近 Oracle 的 80-90%

**实验 3: 冷启动策略消融**
- 方法: 对比三种冷启动策略的效果
- 指标: 前 100/200/500 次委派的任务成功率
- 预期结果: Capability Cards 先验 + LinUCB 在前 200 次委派中比纯随机高 15-20pp

**实验 4: 漂移检测效果**
- 方法: 模拟后端能力漂移（如切换模型版本），评估检测延迟和恢复速度
- 指标: 检测延迟（漂移发生到检测到的委派次数）、恢复延迟（检测到到策略调整完成的委派次数）
- 预期结果: CUSUM 检测延迟 < 20 次委派，恢复延迟 < 50 次委派

### 4. Expected Results

| 方法 | 累积奖励 (normalized) | 任务成功率 | 平均成本 | Regret vs Oracle |
|------|----------------------|-----------|---------|-----------------|
| Random | 0.50 | ~35% | 1.0 | 50% |
| Greedy | 0.65 | ~45% | 0.9 | 35% |
| EpsilonGreedy (ε=0.1) | 0.70 | ~48% | 0.85 | 30% |
| LinUCB (ours) | 0.78 | ~52% | 0.80 | 22% |
| Oracle | 1.00 | ~60% | 0.70 | 0% |

核心预期: LinUCB 在累积奖励上比 EpsilonGreedy 高 11%，比 Random 高 56%。Regret 为 22%，意味着我们捕获了 Oracle 最优策略的 78% 价值。

### 5. Positioning

**与现有工作的区别**:

| 维度 | Uno-Orchestra [P15] | Agent-as-Tool [P05] | Ours |
|------|---------------------|---------------------|------|
| 学习方式 | 离线 RL 训练 | 无学习 | 在线 contextual bandit |
| 后端类型 | 同框架不同模型 | 统一抽象 | 异构 harness |
| 成本建模 | 隐式 | 无 | 显式成本-奖励权衡 |
| 冷启动 | 不适用 | 不适用 | Capability Cards 先验 |
| 漂移适应 | 不适用 | 不适用 | CUSUM 检测 |

**论文定位**: 算法 + 系统论文
- 核心贡献: (1) 任务-后端亲和性的 contextual bandit 建模；(2) 冷启动策略；(3) 后端能力漂移检测
- 故事线: "后端选择是一个在线学习问题——我们需要从执行数据中学习最优策略"
- 目标会议: NeurIPS / ICML / AutoML

---

## 组合方案: ResilientDelegation

两个 refined idea 可以组合为一个综合论文：

**标题**: ResilientDelegation: Cost-Aware Agent Backend Routing with Adaptive Fallback and Affinity Learning

**核心故事线**: "agent 后端失败是常态，我们需要智能降级（Idea 1）和数据驱动选择（Idea 2）来实现可靠的、成本高效的委派"

**论文结构**:
1. Introduction: 后端失败问题 + 成本优化需求
2. Related Work: 多 agent 委派、容错系统、在线学习
3. System Design: BackendAdapter + Unified Output + Delegation Contract（基础层）
4. Adaptive Fallback Chain: 错误分类 + circuit breaker + 降级策略（容错层）
5. Affinity Learning: contextual bandit + 冷启动 + 漂移检测（优化层）
6. Experiments: 4 组实验覆盖各层贡献
7. Discussion: 局限性、未来方向

**目标会议**: MLSys 2027 / NeurIPS 2027 Systems Track
