# Delegator Module: Deep Screening of Top 4 Ideas

**深度筛选**: 对 Tier 1 的 4 个想法进行 3 位审稿人模拟 + meta-review
**审稿人**: Applied Researcher (AR), Empiricist (EM), Theoretician (TH)

---

## Rank 1: Adaptive Fallback Chain for Backend Failures (17/20)

### Applied Researcher Review
- **Strengths**: 直接解决真实痛点——后端失败率 7-50% 是 Delegator 面临的最紧迫问题。circuit breaker 模式是成熟的工程实践，技术风险低。自适应调整降级顺序的想法有实际价值。
- **Weaknesses**: 可能过于工程化，学术贡献有限。circuit breaker 本身不是新东西，迁移贡献的 novelty 需要论证。
- **Score**: 8/10
- **Verdict**: Accept (工程贡献扎实，但需强调迁移创新)

### Empiricist Review
- **Strengths**: 可直接在现有 CLI 后端上实验。使用 Live API-Bench [P11] 作为评估基准是自然的选择。成功率提升和成本增加的权衡可以量化。
- **Weaknesses**: 需要真实的后端失败数据来训练自适应策略。模拟失败可能不够真实。评估指标需要仔细定义——什么算"成功降级"？
- **Score**: 7/10
- **Verdict**: Weak Accept (实验设计可行但需要真实数据)

### Theoretician Review
- **Strengths**: 问题定义清晰（后端失败是常态），技术路线成熟（circuit breaker + 自适应调整）。可以形式化为一个在线学习问题。
- **Weaknesses**: 理论深度有限。circuit breaker 的理论分析（收敛性、最优性）可能过于简单。与 Uno-Orchestra [P15] 的理论贡献相比差距明显。
- **Score**: 6/10
- **Verdict**: Weak Accept (工程价值明确但理论贡献不足)

### Meta-Review
- **综合评分**: 7.0/10
- **核心优势**: 问题紧迫、技术可行、效果可量化
- **核心风险**: 学术 novelty 可能不足，审稿人可能质疑"这不就是把 circuit breaker 搬过来吗"
- **建议**: 需要强调迁移贡献的创新点——(1) agent 后端的失败模式与传统微服务不同，需要专门的错误分类；(2) 自适应调整需要考虑任务特征而非仅看失败率；(3) 降级时的任务格式转换是新的技术挑战

---

## Rank 2: Task-Backend Affinity Learning (15/20)

### Applied Researcher Review
- **Strengths**: 数据驱动的后端选择是最自然的优化方向。Thompson Sampling/UCB 是成熟的技术。亲和性分数可以直接集成到现有 Delegator 中。
- **Weaknesses**: 冷启动问题严重——项目早期没有足够的执行数据。特征工程（如何描述任务复杂度？）是关键挑战，但论文中往往被轻描淡写。
- **Score**: 7/10
- **Verdict**: Weak Accept (方向正确但数据需求是硬伤)

### Empiricist Review
- **Strengths**: 可以设计清晰的实验：(1) 收集历史执行数据；(2) 离线评估亲和性预测准确率；(3) 在线 A/B 测试后端选择效果。评估指标明确：任务成功率、平均成本、延迟。
- **Weaknesses**: 需要大量执行数据（数百到数千次委派）才能训练可靠的模型。在项目早期，这些数据不存在。需要设计冷启动策略（如使用 Capability Cards 作为先验）。
- **Score**: 7/10
- **Verdict**: Accept (实验设计清晰但数据需求是瓶颈)

### Theoretician Review
- **Strengths**: 可以形式化为 contextual bandit 问题——上下文是任务特征，动作是后端选择，奖励是成功率减成本。Thompson Sampling 的理论保证（regret bound）是已知的。
- **Weaknesses**: contextual bandit 本身不是新东西。novelty 在于问题设定（异构 agent 后端）而非算法。与 Uno-Orchestra [P15] 的 RL 方法相比，理论贡献可能更弱。
- **Score**: 6/10
- **Verdict**: Weak Accept (问题设定新颖但算法本身是标准的)

### Meta-Review
- **综合评分**: 6.7/10
- **核心优势**: 数据驱动、可量化、有理论基础（contextual bandit）
- **核心风险**: 数据需求高、冷启动问题、novelty 有限
- **建议**: (1) 设计冷启动策略——使用 Capability Cards 作为先验，用少量执行数据快速校准；(2) 强调问题设定的 novelty——异构后端的成本结构差异使得标准 contextual bandit 需要修改；(3) 考虑与 Idea 10 组合——先用 fallback chain 保证基本可用性，再用 affinity learning 优化选择

---

## Rank 3: BackendAdapter Protocol-Agnostic Abstraction (15/20)

### Applied Researcher Review
- **Strengths**: 统一接口是整个 Delegator 的基础工程。ToolRegistry [P09] 提供了工具级参考，扩展到 harness 级是自然的下一步。开源实现有直接的工程价值。
- **Weaknesses**: 工程贡献大于学术贡献。`BackendAdapter` trait 的设计可能因后端差异过大而变得过于复杂。需要处理大量边界情况。
- **Score**: 7/10
- **Verdict**: Accept (工程基础扎实但学术 novelty 有限)

### Empiricist Review
- **Strengths**: 可以通过集成多个后端（Codex 子 agent、Claude CLI、OpenCode CLI）来验证抽象的有效性。评估指标：集成代码量减少比例、新后端接入时间、错误处理覆盖率。
- **Weaknesses**: 评估比较主观——"集成代码减少 60-80%" 这样的指标需要仔细定义基线。不同后端的差异可能使统一接口变得过于臃肿。
- **Score**: 6/10
- **Verdict**: Weak Accept (评估指标需要精心设计)

### Theoretician Review
- **Strengths**: 可以形式化为接口抽象问题——定义最小完备的接口签名，证明其能表达所有后端的操作语义。
- **Weaknesses**: 理论深度有限。接口设计更多是工程决策而非理论问题。与 ToolRegistry [P09] 的贡献区分度不够。
- **Score**: 5/10
- **Verdict**: Borderline (工程价值明确但学术贡献不足)

### Meta-Review
- **综合评分**: 6.0/10
- **核心优势**: 是 Delegator 的基础工程，其他想法都依赖于它
- **核心风险**: 学术 novelty 不足，可能被视为"工程实现"而非"研究贡献"
- **建议**: (1) 强调 harness 级抽象与 tool 级抽象的本质差异——进程生命周期管理、配置生成、工作区隔离；(2) 设计形式化的接口完备性分析；(3) 考虑作为系统论文的一部分而非独立论文

---

## Rank 4: Unified Output Normalization Protocol (15/20)

### Applied Researcher Review
- **Strengths**: 统一输出格式是 Delegator 上层模块（cost ledger, router）的基础需求。协议设计简单明确，实现成本低。
- **Weaknesses**: 看似简单的格式统一实际上涉及深层语义映射——不同后端的"成功"定义不同。但这个问题可能被高估。
- **Score**: 7/10
- **Verdict**: Accept (基础需求，实现简单)

### Empiricist Review
- **Strengths**: 可以通过对比不同后端的输出格式来验证协议的表达能力。评估指标：信息保留率（规范化后是否丢失关键信息）、转换开销。
- **Weaknesses**: 评估可能过于简单——本质上是格式设计问题，不需要复杂的实验。
- **Score**: 6/10
- **Verdict**: Weak Accept (评估简单但贡献也有限)

### Theoretician Review
- **Strengths**: 可以形式化为信息保持映射——证明规范化过程不丢失语义信息。
- **Weaknesses**: 理论深度非常有限。本质上是工程规范问题。
- **Score**: 5/10
- **Verdict**: Borderline (贡献太小)

### Meta-Review
- **综合评分**: 6.0/10
- **核心优势**: 基础需求、实现简单、其他模块依赖
- **核心风险**: 贡献太小，不足以作为独立论文
- **建议**: (1) 与 Idea 1（BackendAdapter）合并为一个系统设计论文；(2) 如果独立发表，需要强调语义对齐的挑战而非格式设计

---

## 最终排名

| Rank | Idea | Meta-Score | Recommendation |
|------|------|------------|----------------|
| 1 | Adaptive Fallback Chain | 7.0/10 | **Strong Accept** — 作为主要研究方向 |
| 2 | Task-Backend Affinity Learning | 6.7/10 | **Accept** — 作为第二研究方向，与 Rank 1 组合 |
| 3 | BackendAdapter Abstraction | 6.0/10 | **Weak Accept** — 作为系统论文的一部分 |
| 4 | Unified Output Normalization | 6.0/10 | **Weak Accept** — 合并到系统论文中 |

---

## 组合建议

最佳论文组合方案：

**方案 A: 系统论文 + 算法论文**
- 论文 1（系统）: BackendAdapter + Unified Output + Delegation Contract → "A Unified Delegation Framework for Heterogeneous Agent Backends"
- 论文 2（算法）: Adaptive Fallback Chain + Task-Backend Affinity Learning → "Cost-Aware Delegation with Adaptive Fallback and Affinity Learning"

**方案 B: 单一综合论文**
- Adaptive Fallback Chain 作为核心贡献，BackendAdapter 作为系统基础，Affinity Learning 作为优化方向
- 标题: "ResilientDelegation: Adaptive Fallback Chains for Cost-Aware Agent Backend Routing"

**推荐**: 方案 B（单一综合论文）更适合当前项目阶段——贡献点集中、实验设计统一、故事线清晰。
