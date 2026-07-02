# Refined Ideas: Task Router Top 2 研究想法精炼

**日期**: 2026-06-24
**来源**: IDEA-SCREEN Deep 排名前 2 的想法
**目标**: 为每个想法提供详细的 problem anchor、contribution statement、experimental design、expected results、positioning

---

## Refined Idea 1: Harness-Level Routing for Coding Agent Selection

### Problem Anchor (Frozen)

**问题定义**: 给定一个编码任务，选择最优的 agent harness（codex_subagent, claude_cli, opencode_cli, main_agent）执行该任务，以最小化成本并保持任务完成质量。

**为什么这个问题重要**:
- 不同 agent harness 有不同的工具链、上下文窗口、成本结构和擅长领域
- 总是使用最贵的 harness 浪费成本；总是使用最便宜的可能降低质量
- 现有路由器都在模型级别操作，不涉及 harness 级别选择

**为什么这个问题难**:
- Harness 之间的差异不是简单的"更强/更弱"，而是"擅长不同东西"
- Codex 擅长文件操作，Claude CLI 擅长推理，OpenCode 擅长终端交互
- 需要捕获任务特征与 harness 能力的匹配度

**问题边界**:
- 只考虑 coding 任务（不涉及通用 NLP 任务）
- 只考虑 4 个后端（codex_subagent, claude_cli, opencode_cli, main_agent）
- 不涉及任务分解（那是 Refined Idea 2 的范围）

---

### Core Contribution Statement

**主贡献**: 首次在 agent harness 级别建模路由问题，提出 harness-aware 特征工程方法，并创建首个异构 agent harness 路由基准。

**具体贡献点**:
1. **问题 formulation**: 将 harness-level routing 建模为多类分类问题，定义 harness 能力空间和任务-harness 匹配度
2. **特征工程**: 提取 harness-aware 特征（工具链能力、上下文窗口大小、成本结构、任务-工具匹配度）
3. **基准创建**: 构建首个涵盖 Codex/Claude CLI/OpenCode 的异构路由评测基准
4. **实验验证**: 在基准上对比多种路由策略，展示 learned routing 优于 static routing

**贡献类型**: 系统 + 基准

---

### Experimental Design (Skeleton Experiment)

#### 实验 1: Harness 能力表征

**目标**: 量化不同 harness 的能力差异

**方法**:
- 设计一组标准任务，涵盖不同难度和类型
- 在每个 harness 上执行，记录成功率、token 用量、延迟
- 分析 harness 之间的能力差异模式

**数据**:
- 任务集: 100 个 coding 任务（25 simple, 25 medium, 25 hard, 25 sensitive）
- 每个任务在 4 个 harness 上执行，共 400 次执行

**指标**:
- 成功率（任务完成率）
- 平均 token 用量
- 平均延迟
- Harness 之间的能力差异度（用 KL 散度或类似指标）

#### 实验 2: 特征工程有效性

**目标**: 验证 harness-aware 特征的有效性

**方法**:
- 提取三类特征：
  - 通用特征：任务描述的文本嵌入
  - 代码结构特征：AST 深度、依赖图复杂度、文件数量
  - Harness-aware 特征：任务-工具匹配度、上下文窗口需求
- 对比不同特征组合的路由准确性

**数据**:
- 使用实验 1 的数据
- 特征提取: 通用特征用 sentence-transformers，代码结构用 tree-sitter，harness-aware 用自定义规则

**指标**:
- 路由准确率（选择最优 harness 的比例）
- 成本节省率（相对于 always-best-harness）
- 质量保持率（相对于 always-best-harness）

#### 实验 3: 路由策略对比

**目标**: 对比不同路由策略的效果

**方法**:
- Baseline 1: Always use main_agent（最贵但最可靠）
- Baseline 2: Always use codex_subagent（最便宜）
- Baseline 3: Random routing
- Baseline 4: Rule-based routing（基于任务类型的硬编码规则）
- 方法: Learned routing（用实验 2 的最佳特征组合训练分类器）

**数据**:
- 训练集: 实验 1 的 70% 数据
- 测试集: 实验 1 的 30% 数据
- 交叉验证: 5-fold

**指标**:
- 平均成本（token 用量 × 单价）
- 平均质量（任务成功率）
- 成本-质量 Pareto 前沿
- 成本节省率（相对于 always-main-agent）

#### 实验 4: 泛化性验证

**目标**: 验证路由器对新任务的泛化能力

**方法**:
- 在训练集上训练路由器
- 在测试集上评估（测试集包含训练集未见的任务类型）
- 分析路由器的泛化模式

**数据**:
- 训练集: Web 和 Systems 领域的任务
- 测试集: Data 和 ML 领域的任务

**指标**:
- 跨领域路由准确率
- 跨领域成本节省率
- 泛化 gap（in-domain vs cross-domain 的性能差异）

---

### Expected Results and Ablations

#### 预期结果

1. **Harness 能力差异显著**: 不同 harness 在不同任务类型上的成功率差异 > 20%
2. **Harness-aware 特征有效**: 相比通用文本特征，harness-aware 特征提升路由准确率 12-20%
3. **Learned routing 优于 static**: 相比 always-main-agent，learned routing 节省 20-30% 成本，质量损失 < 5%
4. **泛化能力有限**: 跨领域路由准确率下降 10-15%，需要领域适应

#### Ablation Study

| Ablation | 目的 | 预期发现 |
|----------|------|----------|
| 去除 harness-aware 特征 | 验证特征贡献 | 路由准确率下降 12-20% |
| 去除代码结构特征 | 验证代码结构的价值 | 路由准确率下降 5-10% |
| 使用不同分类器 (LR, SVM, MLP) | 验证分类器选择的影响 | MLP 略优于 LR/SVM，但差异不大 |
| 使用不同训练数据量 | 验证数据需求 | 50 个标注任务即可达到 80% 的最优性能 |
| 使用不同任务难度分布 | 验证分布敏感性 | 路由器对分布变化有一定鲁棒性 |

---

### Positioning Against Closest Work

| 维度 | Code as Agent Harness [P12] | Fang et al. [P10] | 本工作 |
|------|---------------------------|-------------------|--------|
| 问题 | 描述 harness 差异 | 本地-云端路由 | Harness 级路由 |
| 方法 | 综述（无方法） | RL 训练路由器 | 特征工程 + 分类器 |
| 路由级别 | N/A（不涉及路由） | 模型级 | Harness 级 |
| 特征 | N/A | 通用特征 | Harness-aware 特征 |
| 基准 | N/A | 本地 vs 云端 | 异构 harness |

**关键差异**: 本工作首次在 harness 级别建模路由问题，并提出 harness-aware 特征工程方法。与 [P12] 的差异在于有具体方法；与 [P10] 的差异在于路由级别不同（harness vs model）。

**潜在反驳**: "这只是 model-level routing 的简单扩展。"
**应对**: Harness 之间的差异不仅是能力大小，而是质的不同（擅长不同东西）。需要新的特征来捕获这种质的差异，这是本工作的核心贡献。

---

## Refined Idea 2: Joint Optimization of Task Decomposition and Subtask Routing

### Problem Anchor (Frozen)

**问题定义**: 给定一个可能需要分解的编码任务，联合优化"如何分解"和"分解后如何路由"，以最小化总成本并保持任务完成质量。

**为什么这个问题重要**:
- 复杂任务需要分解为子任务，子任务可以并行执行或用不同 harness 处理
- 现有工作将分解和路由视为独立阶段，可能错过联合优化的机会
- 联合优化可能产生非直觉的分解策略（如将 medium 任务分解为两个 simple 子任务）

**为什么这个问题难**:
- 分解和路由的搜索空间都是组合的
- 联合优化需要同时考虑分解策略和路由策略
- 需要处理分解成本（分解本身消耗 token）和路由成本

**问题边界**:
- 只考虑 coding 任务
- 分解目标是生成子任务 DAG（有向无环图）
- 路由目标是为每个子任务选择最优 harness

---

### Core Contribution Statement

**主贡献**: 首次将任务分解和子任务路由建模为联合优化问题，提出 tractable 的求解算法，并展示联合优化相对于独立优化的成本节省。

**具体贡献点**:
1. **问题 formulation**: 将分解+路由建模为 bilevel optimization 或 bi-objective optimization
2. **求解算法**: 提出 tractable 的近似算法（如 bilevel relaxation、greedy decomposition with routing-aware scoring）
3. **理论分析**: 给出联合优化相对于独立优化的提升上界
4. **实验验证**: 在复合任务上对比联合优化 vs 独立优化

**贡献类型**: 理论 + 实验

---

### Experimental Design (Skeleton Experiment)

#### 实验 1: 联合优化 vs 独立优化

**目标**: 验证联合优化是否优于独立优化

**方法**:
- Baseline 1: 独立分解 + 独立路由（P11 的分解 + P02 的路由）
- Baseline 2: 独立分解 + 联合路由（分解固定，只优化路由）
- Baseline 3: 联合分解 + 独立路由（路由固定，只优化分解）
- 方法: 联合优化（同时优化分解和路由）

**数据**:
- 复合任务集: 50 个需要分解的 coding 任务
- 每个任务有 ground truth 分解策略（人工标注）
- 每个子任务有 ground truth 最优 harness（通过穷举搜索确定）

**指标**:
- 总成本（分解成本 + 子任务执行成本）
- 任务完成质量（最终代码的正确性）
- 分解质量（与 ground truth 分解的相似度）
- 路由质量（与 ground truth 路由的一致性）

#### 实验 2: 分解策略分析

**目标**: 分析联合优化产生的分解策略的特点

**方法**:
- 收集联合优化产生的分解策略
- 与独立分解策略对比
- 分析非直觉的分解模式

**数据**:
- 使用实验 1 的数据

**指标**:
- 分解粒度（子任务数量）
- 分解类型（顺序分解 vs 并行分解）
- 非直觉分解比例（如将 medium 任务分解为两个 simple 子任务）

#### 实验 3: 计算开销分析

**目标**: 评估联合优化的计算开销

**方法**:
- 测量联合优化 vs 独立优化的运行时间
- 分析计算开销的来源

**数据**:
- 使用实验 1 的数据

**指标**:
- 平均运行时间（每次路由决策）
- 计算开销 breakdown（分解时间 vs 路由时间）
- 成本节省 vs 计算开销的权衡

#### 实验 4: 敏感性分析

**目标**: 分析联合优化对参数的敏感性

**方法**:
- 变化分解成本权重
- 变化路由成本权重
- 变化任务复杂度分布

**数据**:
- 使用实验 1 的数据，变化参数

**指标**:
- 成本节省率 vs 分解成本权重
- 成本节省率 vs 路由成本权重
- 成本节省率 vs 任务复杂度

---

### Expected Results and Ablations

#### 预期结果

1. **联合优化优于独立优化**: 成本节省 18-30%，质量损失 < 3%
2. **非直觉分解策略存在**: 约 15-20% 的任务，联合优化产生与独立分解不同的策略
3. **计算开销可控**: 联合优化的运行时间比独立优化多 2-5 倍，但绝对时间仍在 1 秒内
4. **分解成本权重敏感**: 分解成本权重越高，联合优化越倾向于减少分解

#### Ablation Study

| Ablation | 目的 | 预期发现 |
|----------|------|----------|
| 使用不同求解算法 (greedy, DP, ILP) | 验证算法选择的影响 | ILP 最优但慢，greedy 快但 suboptimal |
| 使用不同分解粒度限制 | 验证粒度限制的影响 | 粒度限制越松，成本节省越大 |
| 使用不同路由成本结构 | 验证成本结构的影响 | 成本差异越大，联合优化的价值越大 |
| 使用不同任务复杂度分布 | 验证分布敏感性 | 复杂任务比例越高，联合优化的价值越大 |
| 去除分解成本 | 验证分解成本的影响 | 无分解成本时，联合优化退化为独立优化 |

---

### Positioning Against Closest Work

| 维度 | Small Model as Master Orchestrator [P11] | GraphPlanner [P05] | 本工作 |
|------|----------------------------------------|-------------------|--------|
| 问题 | 任务分解 | 多 agent 路由 | 分解 + 路由联合优化 |
| 方法 | 小模型编排 | 图记忆 + MDP | Bilevel optimization |
| 分解-路由耦合 | 独立 | 不涉及分解 | 联合优化 |
| 理论贡献 | 无 | MDP formulation | Bilevel optimization |

**关键差异**: 本工作首次将分解和路由作为联合优化问题。与 [P11] 的差异在于路由与分解耦合；与 [P05] 的差异在于涉及分解。

**潜在反驳**: "联合优化的提升可能来自'更多计算'而非'联合优化本身'。"
**应对**: 需要 controlled experiment：在相同计算预算下对比联合优化 vs 独立优化。如果联合优化在相同计算预算下仍优于独立优化，则说明联合优化本身有价值。

**潜在反驳**: "联合优化的计算开销太大，不实用。"
**应对**: 需要展示计算开销在可接受范围内（如 < 1 秒），且成本节省大于计算开销。

---

## 两个想法的互补性

| 维度 | IDEA-02 (Harness-Level Routing) | IDEA-03 (Joint Decomposition-Routing) |
|------|--------------------------------|--------------------------------------|
| 风险 | LOW | HIGH |
| 理论深度 | 低 | 高 |
| 工程价值 | 高 | 中 |
| 实验难度 | 低 | 高 |
| 依赖关系 | 独立 | 依赖 IDEA-02 的 harness 能力表征 |

**建议策略**:
- 先做 IDEA-02（稳扎稳打，建立基础设施）
- 在 IDEA-02 的基础上做 IDEA-03（利用 harness 能力表征做联合优化）
- 两篇论文可以形成一个系列：第一篇建立 harness-level routing 基础，第二篇展示联合优化的价值
