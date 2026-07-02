# IDEA-SCREEN: Task Router 研究想法筛选

**日期**: 2026-06-24
**筛选标准**: Prof. He's 4-dimension filter (Longevity + Passion + Application + Uniqueness, 满分20, 阈值12)

---

## 筛选结果总览

| 排名 | Idea ID | Title | Feasibility | Novelty | Impact | Longevity | Passion | Application | Uniqueness | **Composite** | 通过? |
|------|---------|-------|-------------|---------|--------|-----------|---------|-------------|------------|---------------|-------|
| 1 | IDEA-01 | Cost Ledger Feedback Loop | FEASIBLE | LIKELY NOVEL | HIGH | 4 | 4 | 5 | 4 | **17** | YES |
| 2 | IDEA-02 | Harness-Level Routing | FEASIBLE | LIKELY NOVEL | HIGH | 5 | 4 | 5 | 4 | **18** | YES |
| 3 | IDEA-08 | Contextual Bandit | FEASIBLE | NEEDS DEEPER CHECK | MEDIUM | 4 | 4 | 4 | 3 | **15** | YES |
| 4 | IDEA-09 | Cascaded Harness Routing | FEASIBLE | LIKELY NOVEL | MEDIUM | 4 | 4 | 5 | 3 | **16** | YES |
| 5 | IDEA-04 | Code Structure Features | FEASIBLE WITH CAVEATS | LIKELY NOVEL | MEDIUM | 4 | 3 | 4 | 4 | **15** | YES |
| 6 | IDEA-05 | Risk-Aware Uncertainty | FEASIBLE WITH CAVEATS | NEEDS DEEPER CHECK | MEDIUM | 4 | 3 | 4 | 3 | **14** | YES |
| 7 | IDEA-12 | Predictive Cost Modeling | FEASIBLE | NEEDS DEEPER CHECK | LOW | 3 | 3 | 4 | 3 | **13** | YES |
| 8 | IDEA-03 | Joint Decomposition-Routing | FEASIBLE WITH CAVEATS | LIKELY NOVEL | HIGH | 5 | 4 | 4 | 5 | **18** | YES |
| 9 | IDEA-10 | Adversarial Robustness | FEASIBLE | LIKELY NOVEL | LOW | 3 | 3 | 2 | 4 | **12** | BORDERLINE |
| 10 | IDEA-07 | Adaptive Few-Shot | FEASIBLE | NEEDS DEEPER CHECK | MEDIUM | 3 | 3 | 3 | 3 | **12** | BORDERLINE |
| 11 | IDEA-06 | Multi-Objective RL | FEASIBLE WITH CAVEATS | LIKELY NOVEL | MEDIUM | 4 | 5 | 3 | 4 | **16** | YES |
| 12 | IDEA-11 | Meta-Learning | INFEASIBLE | LIKELY NOVEL | MEDIUM | 3 | 4 | 3 | 4 | **14** | NO* |

*IDEA-11 虽然 composite 分数通过，但 feasibility 为 INFEASIBLE（元学习在编码路由场景的数据需求和训练成本过高），筛除。

---

## 逐项详细评估

### IDEA-01: Cost Ledger Feedback Loop for Self-Improving Task Routing

**Feasibility**: FEASIBLE
- 实现路径清晰：在现有路由器外加一层反馈收集和策略更新
- 数据来源明确：每次路由执行后的 token 用量、延迟、成功率
- 在线学习技术成熟（bandit、在线梯度下降）

**Novelty**: LIKELY NOVEL
- 搜索 "LLM routing online feedback" 未找到直接相关工作
- FrugalGPT [P01] 和 RouteLLM [P02] 都是离线训练
- 但需注意：在线学习在推荐系统中很常见，增量创新风险存在

**Impact**: HIGH
- 直接降低运营成本，工程价值明确
- 可以量化：反馈闭环 vs 静态路由器的成本差异

**Prof. He's 4-Dimension Filter**:
- Longevity (4/5): 在线反馈是长期有效的技术路线，不会因模型升级而过时
- Passion (4/5): 系统 + ML 交叉，符合 research 兴趣
- Application (5/5): 直接可部署，工程价值最高
- Uniqueness (4/5): 团队有系统实现能力，但在线学习本身不独特

**Composite**: 17/20

---

### IDEA-02: Harness-Level Routing with Code Agent Feature Engineering

**Feasibility**: FEASIBLE
- 需要实现多个 harness 的统一接口，工程量可控
- 特征提取基于代码结构，有成熟工具支持
- 需要创建评测基准，但数据可通过实际使用收集

**Novelty**: LIKELY NOVEL
- 搜索 "agent harness routing" 未找到直接相关工作
- Code as Agent Harness [P12] 描述了 harness 差异但未涉及路由
- 现有路由工作（P01-P10）都在模型级别

**Impact**: HIGH
- 直接解决 Task Router 的核心问题
- 为后续研究提供基准和基础设施

**Prof. He's 4-Dimension Filter**:
- Longevity (5/5): 随着更多 agent harness 出现，此问题会越来越重要
- Passion (4/5): 系统研究，符合 research 兴趣
- Application (5/5): 直接应用于 cost-aware coding-agent router
- Uniqueness (4/5): 首次在 harness 级别建模路由，但分类方法本身不新

**Composite**: 18/20

---

### IDEA-08: Contextual Bandit for Cost-Aware Agent Selection

**Feasibility**: FEASIBLE
- Contextual bandit 算法成熟（LinUCB, Thompson Sampling）
- 实现简单，不需要大量训练数据
- 可以快速验证

**Novelty**: NEEDS DEEPER CHECK
- Contextual bandit 在推荐系统中广泛应用
- 应用于 LLM 路由需要确认是否已有工作
- 关键 novelty 在于 cost-weighted reward 设计

**Impact**: MEDIUM
- 提供理论保证，但实际提升可能有限
- 适合快速原型验证

**Prof. He's 4-Dimension Filter**:
- Longevity (4/5): Bandit 是经典方法，长期有效
- Passion (4/5): 理论 + 系统，符合 research 兴趣
- Application (4/5): 可快速部署，但理论保证在实际中可能不完全成立
- Uniqueness (3/5): Bandit 应用到路由是增量创新

**Composite**: 15/20

---

### IDEA-09: Cascaded Harness Routing with Adaptive Escalation

**Feasibility**: FEASIBLE
- 级联策略实现简单
- 质量评估信号需要设计，但可用现有指标（编译、测试）
- 需要定义 harness 成本层级

**Novelty**: LIKELY NOVEL
- 模型级级联（P01, P03）已成熟，但 harness 级级联未被研究
- Harness 之间的异构差异使问题比模型级级联更复杂

**Impact**: MEDIUM
- 成本节省潜力大（35-50%），但依赖质量评估信号的准确性
- 如果质量评估不准，可能导致频繁升级，成本反而增加

**Prof. He's 4-Dimension Filter**:
- Longevity (4/5): 级联思想长期有效
- Passion (4/5): 系统优化，符合 research 兴趣
- Application (5/5): 直接可部署，成本节省明显
- Uniqueness (3/5): 级联方法成熟，harness 级应用是增量

**Composite**: 16/20

---

### IDEA-04: Code Structure-Aware Routing Signals

**Feasibility**: FEASIBLE WITH CAVEATS
- 需要代码解析工具（AST, 依赖图），有一定工程量
- 特征提取可能有性能开销，需要优化
- 部分特征（如依赖图复杂度）在任务执行前难以准确估计

**Novelty**: LIKELY NOVEL
- 现有路由器使用通用文本特征，未针对编码任务设计
- 代码结构特征在 SE 领域有研究，但未应用于路由

**Impact**: MEDIUM
- 提升路由准确性，但幅度需要实验验证
- 特征工程的贡献可能不够"研究级"

**Prof. He's 4-Dimension Filter**:
- Longevity (4/5): 代码结构特征随代码语言演进而变化，但核心思想长期有效
- Passion (3/5): 偏工程，research 深度有限
- Application (4/5): 直接提升路由准确性
- Uniqueness (4/5): 首次将代码结构特征用于路由

**Composite**: 15/20

---

### IDEA-05: Risk-Aware Routing with Uncertainty Calibration

**Feasibility**: FEASIBLE WITH CAVEATS
- 不确定性校准技术成熟（temperature scaling）
- 但"不确定性 ≈ 风险"的假设需要实验验证
- 如果假设不成立，需要额外的风险评估模块

**Novelty**: NEEDS DEEPER CHECK
- UCCI [P03] 已经用不确定性做级联，但不涉及风险
- 需要确认是否有人将不确定性与操作风险关联

**Impact**: MEDIUM
- 风险感知路由对生产环境很重要
- 但不确定性能否可靠地代理风险是关键问题

**Prof. He's 4-Dimension Filter**:
- Longevity (4/5): 风险感知是长期需求
- Passion (3/5): 偏应用，理论深度有限
- Application (4/5): 直接应用于生产环境
- Uniqueness (3/5): 不确定性校准已有成熟研究

**Composite**: 14/20

---

### IDEA-12: Predictive Cost Modeling for Pre-Routing Budget Allocation

**Feasibility**: FEASIBLE
- 成本预测模型可以用历史数据训练
- 实现简单，作为路由器的前置模块

**Novelty**: NEEDS DEEPER CHECK
- 成本预测在云计算领域有研究，但应用于 LLM 路由需要确认
- 关键 novelty 在于将预测成本作为路由信号

**Impact**: LOW
- 成本预测的准确性可能有限
- 作为独立贡献略显单薄

**Prof. He's 4-Dimension Filter**:
- Longevity (3/5): 成本预测随模型更新需要重新训练
- Passion (3/5): 偏工程
- Application (4/5): 有直接应用价值
- Uniqueness (3/5): 增量创新

**Composite**: 13/20

---

### IDEA-03: Joint Decomposition-Routing Optimization

**Feasibility**: FEASIBLE WITH CAVEATS
- 联合优化问题复杂，需要设计高效的求解算法
- 实验设计困难：需要对比独立分解+路由 vs 联合优化
- 数据需求大：需要复合任务的标注数据

**Novelty**: LIKELY NOVEL
- 搜索 "joint decomposition routing LLM" 未找到直接相关工作
- P11 的分解和 P01-P06 的路由都是独立设计的

**Impact**: HIGH
- 如果联合优化确实优于独立优化，将改变 Task Router 的设计范式
- 但"如果"是关键——需要严格实验验证

**Prof. He's 4-Dimension Filter**:
- Longevity (5/5): 联合优化是根本性问题，长期有效
- Passion (4/5): 优化理论 + 系统，符合 research 兴趣
- Application (4/5): 如果成功，直接提升 Task Router 性能
- Uniqueness (5/5): 首次将分解和路由联合优化

**Composite**: 18/20

---

### IDEA-10: Adversarial Robustness of Task Routers

**Feasibility**: FEASIBLE
- 对抗扰动生成技术成熟
- 鲁棒性评估方法有标准框架

**Novelty**: LIKELY NOVEL
- 搜索 "adversarial robustness LLM routing" 未找到直接相关工作
- 但 NLP 领域的对抗鲁棒性研究已很充分

**Impact**: LOW
- 对 Task Router 的实际部署影响有限
- 更多是"可靠性分析"而非"性能提升"

**Prof. He's 4-Dimension Filter**:
- Longevity (3/5): 鲁棒性研究随攻击手段演进而过时
- Passion (3/5): 偏分析，研究深度有限
- Application (2/5): 对实际部署影响有限
- Uniqueness (4/5): 首次研究 LLM 路由器的对抗鲁棒性

**Composite**: 12/20 (BORDERLINE)

---

### IDEA-07: Adaptive Few-Shot Routing via Task Similarity Retrieval

**Feasibility**: FEASIBLE
- 检索式方法实现简单
- 任务相似度度量需要设计

**Novelty**: NEEDS DEEPER CHECK
- 检索增强在 NLP 中已有广泛应用
- 应用于路由需要确认是否已有工作

**Impact**: MEDIUM
- 对冷启动场景有帮助
- 但长期运行后，在线学习方法可能更优

**Prof. He's 4-Dimension Filter**:
- Longevity (3/5): 随着历史数据积累，检索式方法的优势减弱
- Passion (3/5): 偏工程
- Application (3/5): 适合冷启动，但不是长期方案
- Uniqueness (3/5): 检索增强已有成熟研究

**Composite**: 12/20 (BORDERLINE)

---

### IDEA-06: Multi-Objective RL for Cost-Quality-Risk Tradeoff

**Feasibility**: FEASIBLE WITH CAVEATS
- 多目标 RL 技术成熟（PPO + 多目标奖励）
- 但训练成本高，需要大量交互数据
- 三目标优化的 Pareto 前沿可能难以可视化和解释

**Novelty**: LIKELY NOVEL
- 搜索 "multi-objective RL LLM routing" 未找到直接相关工作
- SCOPE [P04] 用 RL 但只优化单一目标

**Impact**: MEDIUM
- Pareto 最优策略集有理论价值
- 但实际部署中可能只需要一个策略

**Prof. He's 4-Dimension Filter**:
- Longevity (4/5): 多目标优化是长期有效的框架
- Passion (5/5): 优化理论 + ML，最符合 research 兴趣
- Application (3/5): Pareto 策略集的实际应用需要额外选择步骤
- Uniqueness (4/5): 首次在 LLM 路由中引入三目标优化

**Composite**: 16/20

---

## 筛选结论

**通过阈值 (>= 12/20) 的想法**: 11 个 (IDEA-01, 02, 03, 04, 05, 06, 07, 08, 09, 10, 12)
**筛除**: IDEA-11 (INFEASIBLE), IDEA-10 (BORDERLINE, 但保留供深度评审)

**Top 4 进入深度评审**:
1. IDEA-02: Harness-Level Routing (18/20) — 最直接解决核心问题
2. IDEA-03: Joint Decomposition-Routing (18/20) — 最高novelty但风险大
3. IDEA-01: Cost Ledger Feedback Loop (17/20) — 最高工程价值
4. IDEA-09: Cascaded Harness Routing (16/20) — 成本节省潜力最大

**备选** (如Top 4中有不通过者):
- IDEA-06: Multi-Objective RL (16/20)
- IDEA-08: Contextual Bandit (15/20)
- IDEA-04: Code Structure Features (15/20)
