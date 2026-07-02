# IDEA-SCREEN Deep: Task Router 研究想法深度评审

**日期**: 2026-06-24
**评审对象**: Top 4 ideas from IDEA-SCREEN
**评审标准**: Strong Reject=1, Reject=3, Weak Reject=4, Weak Accept=6, Accept=8, Strong Accept=10
**评审者**: 3 位模拟审稿人 + Meta-Review

---

## 评审者画像

- **Reviewer 1 (R1)**: Applied Researcher — 关注效率、可扩展性、工程实现
- **Reviewer 2 (R2)**: Empiricist — 关注实验严谨性、baseline、可复现性
- **Reviewer 3 (R3)**: Theoretician — 关注novelty、数学深度、理论贡献

---

## IDEA-02: Harness-Level Routing with Code Agent Feature Engineering

### R1 (Applied Researcher) — Score: 8 (Accept)

**Strengths**:
- 直接解决 Task Router 的核心问题：在不同 agent harness 之间做选择
- 工程实现路径清晰：特征提取 + 分类器
- 为后续研究提供基准和基础设施，有持续价值

**Weaknesses**:
- Harness 之间的能力差异可能随版本更新而变化，路由器需要定期重训
- 特征工程的泛化性需要验证——针对 Codex/Claude CLI/OpenCode 设计的特征，对新 harness 是否有效?

**Questions**:
- 如何处理 harness 版本更新导致的能力漂移?
- 特征提取的性能开销是多少? 是否影响路由延迟?

### R2 (Empiricist) — Score: 7 (Weak Accept)

**Strengths**:
- 需要创建新基准，这是有价值的基础设施贡献
- 实验设计可以很清晰：对比 always-best-harness vs learned routing

**Weaknesses**:
- 缺少明确的 baseline：没有现成的 harness-level routing 方法可对比
- 评测指标需要仔细设计：什么是"harness 选择正确"? 需要事后验证
- 数据收集可能有偏差：如果总是用最好的 harness，就无法获得差 harness 的反馈

**Questions**:
- 如何构建 ground truth（哪个 harness 最优）?
- 是否考虑 A/B 测试或在线评估?

### R3 (Theoretician) — Score: 5 (Weak Reject)

**Strengths**:
- 问题定义清晰，有实际价值

**Weaknesses**:
- 路由机制本身不新——本质上是一个多类分类问题
- 没有理论贡献：为什么 harness-level routing 比 model-level routing 更难/更有趣?
- 特征工程的贡献可能不够"研究级"——更像是工程优化

**Questions**:
- 是否有理论分析说明 harness-level routing 的最优性边界?
- 与 model-level routing 的理论关系是什么?

### Meta-Review

**综合评价**: 这是一个强应用贡献。问题定义清晰，工程价值高，但理论深度不足。关键挑战是：(1) 构建可靠的 ground truth；(2) 证明 harness-level routing 的独特价值（不仅仅是 model-level routing 的简单扩展）。

**建议**: 如果能补充理论分析（如 harness 能力空间的形式化、routing 最优性边界），可以提升到 Accept。

**最终评分**: (8 + 7 + 5) / 3 = **6.7 (Weak Accept)**

---

## IDEA-03: Joint Decomposition-Routing Optimization

### R1 (Applied Researcher) — Score: 6 (Weak Accept)

**Strengths**:
- 问题定义新颖，首次将分解和路由作为联合优化问题
- 如果成功，将改变 Task Router 的设计范式

**Weaknesses**:
- 实现复杂度高：联合优化需要同时考虑分解和路由的搜索空间
- 计算开销可能很大：每次路由决策需要 solve 一个优化问题
- 实验设计困难：如何对比独立分解+路由 vs 联合优化?

**Questions**:
- 联合优化的求解算法是什么? 计算复杂度如何?
- 是否有 relaxation 或近似方法降低计算开销?

### R2 (Empiricist) — Score: 5 (Weak Reject)

**Strengths**:
- 如果能展示联合优化优于独立优化，将有很强的说服力

**Weaknesses**:
- 实验设计存在 confounding：联合优化的提升可能来自"更多计算"而非"联合优化本身"
- 需要 controlled experiment：在相同计算预算下对比
- 数据需求大：需要复合任务的标注数据（哪些任务需要分解，如何分解）

**Questions**:
- 如何控制计算预算，确保公平对比?
- ground truth 分解策略如何获取?

### R3 (Theoretician) — Score: 9 (Strong Accept)

**Strengths**:
- 问题 formulation 有理论深度：分解和路由的联合优化可以建模为 bilevel optimization 或 bi-objective optimization
- 非直觉的分解策略（如将 medium 任务分解为两个 simple 子任务）有理论研究价值
- 首次挑战"分解和路由独立"的假设

**Weaknesses**:
- 需要更清晰的理论框架：联合优化的最优性条件是什么?
- 是否存在 closed-form solution 或需要 iterative algorithm?

**Questions**:
- 联合优化的 Pareto 前沿是什么形状?
- 是否有理论 bound 说明联合优化相对于独立优化的提升上限?

### Meta-Review

**综合评价**: 这是一个高风险高回报的想法。理论 novelty 最高（R3 给了 Strong Accept），但实验挑战也最大（R2 给了 Weak Reject）。关键问题是：(1) 如何设计公平的对比实验；(2) 如何降低联合优化的计算开销。

**建议**: 需要一个 tractable 的联合优化 formulation（如 bilevel relaxation），以及严格的 controlled experiment。如果能同时满足理论深度和实验严谨性，这是最有影响力的工作。

**最终评分**: (6 + 5 + 9) / 3 = **6.7 (Weak Accept)**

---

## IDEA-01: Cost Ledger Feedback Loop for Self-Improving Task Routing

### R1 (Applied Researcher) — Score: 8 (Accept)

**Strengths**:
- 工程价值最高：直接降低运营成本
- 实现路径清晰：在现有路由器外加一层反馈收集
- 可量化：反馈闭环 vs 静态路由器的成本差异

**Weaknesses**:
- 在线学习可能导致路由器频繁变化，影响稳定性
- 需要处理延迟反馈：任务执行需要时间，反馈不是即时的

**Questions**:
- 如何处理延迟反馈? 是否使用 bandit 的 delayed reward 框架?
- 路由器更新频率如何控制? 是否需要 A/B 测试验证?

### R2 (Empiricist) — Score: 6 (Weak Accept)

**Strengths**:
- 实验设计清晰：对比 static router vs feedback loop router
- 可以 ablate 不同反馈信号（token 用量、延迟、成功率）的贡献

**Weaknesses**:
- 需要长期运行才能看到反馈闭环的效果，短期实验可能不充分
- 如何评估"质量"? 成功率是粗糙的指标

**Questions**:
- 实验周期多长? 需要多少路由决策才能看到统计显著的改进?
- 质量评估指标是什么?

### R3 (Theoretician) — Score: 6 (Weak Accept)

**Strengths**:
- 在线学习 formulation 有理论基础（regret minimization）
- 延迟反馈的处理有理论挑战

**Weaknesses**:
- 理论贡献有限：在线学习已有成熟理论
- 关键 novelty 在于"应用"而非"理论"

**Questions**:
- 是否有 regret bound 分析?
- 延迟反馈对 regret 的影响是什么?

### Meta-Review

**综合评价**: 这是一个工程价值最高的想法。实现简单，效果可量化，部署风险低。但理论贡献有限，需要在实验设计上下功夫（长期运行、ablation study、延迟反馈处理）。

**建议**: 作为系统论文投稿很合适。如果想提升理论深度，可以补充 regret bound 分析和延迟反馈的理论处理。

**最终评分**: (8 + 6 + 6) / 3 = **6.7 (Weak Accept)**

---

## IDEA-09: Cascaded Harness Routing with Adaptive Escalation

### R1 (Applied Researcher) — Score: 8 (Accept)

**Strengths**:
- 成本节省潜力最大（35-50%）
- 实现简单：级联策略 + 质量评估信号
- 直接可部署

**Weaknesses**:
- 质量评估信号的准确性是关键——如果评估不准，频繁升级会增加成本
- Harness 之间的能力差异不是简单的"更强/更弱"，级联策略需要考虑任务-harness 匹配度

**Questions**:
- 质量评估信号是什么? 编译通过? 测试通过? 自一致性?
- 如何处理 harness 之间的"擅长不同东西"而非"能力大小"的差异?

### R2 (Empiricist) — Score: 7 (Weak Accept)

**Strengths**:
- 实验设计清晰：对比 always-best-harness vs cascaded routing
- 可以 ablate 不同质量评估信号的效果

**Weaknesses**:
- 需要定义 harness 的成本层级——这本身可能有争议
- 成本节省的估计依赖于任务难度分布的假设

**Questions**:
- 成本层级如何定义? 是否考虑任务-harness 匹配度?
- 任务难度分布的假设是什么? 是否在不同分布下验证?

### R3 (Theoretician) — Score: 5 (Weak Reject)

**Strengths**:
- 级联理论有成熟基础（P07）

**Weaknesses**:
- 级联方法已很成熟（P01, P03），harness 级应用是增量创新
- 没有新的理论贡献
- "擅长不同东西"的 harness 差异使标准级联理论不直接适用，但没有新的理论处理

**Questions**:
- 如何形式化 harness 之间的"擅长不同东西"的差异?
- 标准级联理论（P07）是否直接适用?

### Meta-Review

**综合评价**: 这是一个高工程价值、低理论深度的想法。成本节省潜力大，实现简单，但理论 novelty 不足。关键挑战是：(1) 如何处理 harness 之间的异构差异；(2) 质量评估信号的准确性。

**建议**: 如果能补充对 harness 异构差异的形式化分析（不仅仅是"更强/更弱"），可以提升理论深度。

**最终评分**: (8 + 7 + 5) / 3 = **6.7 (Weak Accept)**

---

## 最终排名

| 排名 | Idea ID | Title | R1 | R2 | R3 | **Average** | 评级 |
|------|---------|-------|----|----|-----|-------------|------|
| 1 | IDEA-02 | Harness-Level Routing | 8 | 7 | 5 | **6.7** | Weak Accept |
| 2 | IDEA-03 | Joint Decomposition-Routing | 6 | 5 | 9 | **6.7** | Weak Accept |
| 3 | IDEA-01 | Cost Ledger Feedback Loop | 8 | 6 | 6 | **6.7** | Weak Accept |
| 4 | IDEA-09 | Cascaded Harness Routing | 8 | 7 | 5 | **6.7** | Weak Accept |

**注意**: 四个想法的平均分相同（6.7），但审稿人评分分布不同：
- IDEA-02 和 IDEA-09: Applied Researcher 和 Empiricist 给高分，Theoretician 给低分 → 偏应用
- IDEA-03: Theoretician 给最高分（Strong Accept），其他给低分 → 偏理论
- IDEA-01: 三个审稿人评分最均衡 → 平衡型

**选择 Top 2 的策略**:
- 选择 IDEA-02（最直接解决核心问题，工程价值高）
- 选择 IDEA-03（理论 novelty 最高，有改变范式的潜力）

这两个想法形成互补：IDEA-02 是"稳扎稳打"的应用贡献，IDEA-03 是"高风险高回报"的理论贡献。
