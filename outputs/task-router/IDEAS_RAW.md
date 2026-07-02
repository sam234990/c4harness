# IDEA-GEN: Task Router 研究想法生成

**日期**: 2026-06-24
**输入**: landscape-task-router.md (7 gaps, 4 themes, 12 papers)
**目标**: 为 Task Router 模块生成 8-12 个具体研究想法

---

## 生成想法列表

### IDEA-01: Cost Ledger Feedback Loop for Self-Improving Task Routing

1. **Title**: Cost Ledger Feedback Loop for Self-Improving Task Routing
2. **Thesis**: We show that a task router can continuously improve its routing decisions by incorporating real execution cost data (token usage, latency, success rate) as online feedback, achieving 15-25% additional cost reduction over static routers.
3. **Problem**: Gap G3 — 现有路由器的训练与实际成本数据解耦，没有利用执行后的反馈来持续改进策略。
4. **Core mechanism**: 每次路由执行后，cost ledger 记录实际 token 用量、延迟、成功率等指标，与路由决策关联。定期用这些反馈数据更新路由器的策略（在线学习或定期微调）。
5. **Why non-obvious**: 现有工作都将路由视为一次性决策问题，忽略了执行后的闭环反馈。这不是简单的"apply online learning to routing"，因为编码任务的成本反馈信号是多维的（token、延迟、成功率、代码质量），且存在延迟反馈（任务执行需要时间）。
6. **Contribution type**: 系统 + 实验
7. **Risk level**: LOW
8. **Estimated effort**: 3 person-weeks
9. **Closest existing work + delta**: FrugalGPT [P01] 使用静态级联阈值；RouteLLM [P02] 用离线偏好数据训练。本工作的 delta 在于引入在线反馈闭环，路由器可以从自身错误中学习。

---

### IDEA-02: Harness-Level Routing with Code Agent Feature Engineering

1. **Title**: Harness-Level Routing: Selecting Between Codex, Claude CLI, and OpenCode Based on Task Characteristics
2. **Thesis**: We show that routing coding tasks between different agent harnesses (not just models) based on harness-specific features achieves 20-30% better cost-quality tradeoff than always using a single harness.
3. **Problem**: Gap G2 — 没有路由器在不同 agent harness 之间做选择。现有工作都在模型级别路由。
4. **Core mechanism**: 提取 harness-aware 特征（工具链能力、上下文窗口大小、成本结构、任务-工具匹配度），训练分类器选择最优 harness。
5. **Why non-obvious**: 这不是简单的"apply classification to harness selection"。Harness 之间的差异不仅是能力大小，而是质的不同——Codex 擅长文件操作，Claude CLI 擅长推理，OpenCode 擅长终端交互。路由信号需要捕获这种质的差异。
6. **Contribution type**: 系统 + 基准
7. **Risk level**: LOW
8. **Estimated effort**: 4 person-weeks
9. **Closest existing work + delta**: Code as Agent Harness [P12] 描述了 harness 差异但未涉及路由；Fang et al. [P10] 的本地-云端路由是模型级而非 harness 级。本工作的 delta 在于首次在 harness 级别建模路由问题。

---

### IDEA-03: Joint Decomposition-Routing Optimization

1. **Title**: Joint Optimization of Task Decomposition and Subtask Routing for Coding Agents
2. **Thesis**: We show that jointly optimizing task decomposition and subtask routing (rather than treating them as independent stages) reduces total cost by 18-30% while maintaining task completion quality.
3. **Problem**: Gap G4 — 分解策略和路由策略是独立设计的，没有联合优化。
4. **Core mechanism**: 将"分解 + 路由"建模为一个联合优化问题。分解决策影响路由选择（子任务数量和类型决定最优路由），路由结果反过来影响分解策略（某些 harness 更适合处理特定子任务）。
5. **Why non-obvious**: 现有工作（P11）将分解和路由视为独立阶段。联合优化可能产生非直觉的分解策略——例如，将一个 medium 任务分解为两个 simple 子任务，即使每个子任务单独看不需要分解，但组合起来路由到 cheap harness 更划算。
6. **Contribution type**: 理论 + 实验
7. **Risk level**: HIGH
8. **Estimated effort**: 6 person-weeks
9. **Closest existing work + delta**: Small Model as Master Orchestrator [P11] 做了分解但路由策略独立；GraphPlanner [P05] 做了多 agent 路由但不涉及分解。本工作的 delta 在于将两者作为一个联合优化问题。

---

### IDEA-04: Code Structure-Aware Routing Signals

1. **Title**: Beyond Text Embeddings: Code Structure as Routing Signal for Task Difficulty Assessment
2. **Thesis**: We show that code-structural features (AST depth, dependency graph complexity, file scope, cyclomatic complexity) outperform text-based features for coding task difficulty prediction by 12-20%.
3. **Problem**: Gap G5 — 现有路由器使用通用特征（文本嵌入、logit 置信度），未利用编码任务的结构化信号。
4. **Core mechanism**: 从任务描述和代码上下文中提取结构化特征（AST 深度、依赖图复杂度、文件数量、读写模式），作为路由决策的输入信号。
5. **Why non-obvious**: 这不是简单的"add more features"。编码任务的结构信号与自然语言任务的信号有本质不同——一个"修改 3 个文件"的任务和一个"修改 1 个文件"的任务，文本描述可能非常相似，但难度差异巨大。
6. **Contribution type**: 实验 + 特征工程
7. **Risk level**: MEDIUM
8. **Estimated effort**: 4 person-weeks
9. **Closest existing work + delta**: RouteLLM [P02] 使用文本嵌入；UCCI [P03] 使用 logit 置信度。本工作的 delta 在于引入代码结构特有的路由信号。

---

### IDEA-05: Risk-Aware Routing with Uncertainty Calibration

1. **Title**: Risk-Aware Task Routing: Calibrated Uncertainty as a Signal for Operation Risk Assessment
2. **Thesis**: We show that calibrated uncertainty scores from the router's own predictions can reliably distinguish between read_only, patch, and sensitive operations, enabling risk-appropriate routing without explicit risk labels.
3. **Problem**: Gap G6 — 没有路由器考虑操作风险（读文件 vs 写文件 vs 修改生产配置）。
4. **Core mechanism**: 对路由器的难度预测进行不确定性校准（temperature scaling），高不确定性自动触发保守路由（选择更可靠的后端）。不确定性水平与操作风险等级正相关。
5. **Why non-obvious**: 现有工作（P03）用不确定性做级联触发，但未将不确定性与操作风险关联。假设是：路由器对某个任务"不确定"，往往意味着该任务有特殊风险（如边界情况、敏感操作）。
6. **Contribution type**: 理论 + 实验
7. **Risk level**: MEDIUM
8. **Estimated effort**: 4 person-weeks
9. **Closest existing work + delta**: UCCI [P03] 用校准不确定性做级联，但仅考虑质量不考虑风险。本工作的 delta 在于将不确定性校准与操作风险评估结合。

---

### IDEA-06: Multi-Objective RL for Cost-Quality-Risk Tradeoff

1. **Title**: Multi-Objective Reinforcement Learning for Joint Cost, Quality, and Risk Optimization in Task Routing
2. **Thesis**: We show that multi-objective RL (Pareto optimization over cost, quality, and risk) discovers routing strategies that dominate single-objective approaches on the Pareto frontier.
3. **Problem**: Gap G3 + G6 — 现有路由器只优化成本或质量，不考虑风险；且不使用在线反馈。
4. **Core mechanism**: 用多目标 RL 训练路由器，奖励函数同时考虑成本（token 用量）、质量（任务成功率）、风险（敏感操作的保守程度）。输出 Pareto 最优策略集。
5. **Why non-obvious**: 现有工作都将路由建模为单目标优化（成本最小化或质量最大化）。多目标优化可能揭示非直觉的权衡——例如，某些场景下略微增加成本可以大幅降低风险。
6. **Contribution type**: 理论 + 实验
7. **Risk level**: HIGH
8. **Estimated effort**: 6 person-weeks
9. **Closest existing work + delta**: SCOPE [P04] 用 RL 训练路由器但只优化单一目标；Fang et al. [P10] 考虑延迟-质量权衡但不涉及风险。本工作的 delta 在于引入三目标 Pareto 优化。

---

### IDEA-07: Adaptive Few-Shot Routing via Task Similarity Retrieval

1. **Title**: Adaptive Few-Shot Routing: Retrieval-Augmented Task Routing via Historical Task Similarity
2. **Thesis**: We show that retrieving similar historical tasks and adapting their routing decisions achieves competitive performance with zero training data, outperforming cold-start learned routers by 10-15%.
3. **Problem**: Gap G3 — 路由器需要大量标注数据训练，无法快速适应新场景。
4. **Core mechanism**: 用任务嵌入在历史任务库中检索最相似的 k 个任务，基于它们的路由结果和执行成本做决策（k-NN 路由 + 权重调整）。
5. **Why non-obvious**: 这不是简单的"k-NN classification"。关键在于任务相似度的定义——两个任务文本相似但代码结构不同，路由决策可能完全不同。需要设计 code-aware 的相似度度量。
6. **Contribution type**: 系统 + 实验
7. **Risk level**: MEDIUM
8. **Estimated effort**: 4 person-weeks
9. **Closest existing work + delta**: GraphPlanner [P05] 用图记忆存储历史，但需要 MDP 训练。本工作的 delta 在于零训练的检索式路由，可即时部署。

---

### IDEA-08: Contextual Bandit for Cost-Aware Agent Selection

1. **Title**: Contextual Bandit Formulation for Cost-Aware Coding Agent Selection
2. **Thesis**: We show that formulating harness selection as a contextual bandit problem with cost-weighted rewards achieves near-optimal cost-quality tradeoff with minimal exploration overhead.
3. **Problem**: Gap G3 — 需要在线学习路由策略，但 RL 训练成本高。
4. **Core mechanism**: 将每次路由决策建模为 contextual bandit：context 是任务特征，action 是 harness 选择，reward 是质量减去成本。用 LinUCB 或 Thompson Sampling 做探索-利用权衡。
5. **Why non-obvious**: 现有工作要么用离线训练（P02）要么用完整 RL（P04）。Contextual bandit 恰好适合路由问题——每次决策独立（不像 RL 需要考虑长期回报），且有成熟的理论保证。
6. **Contribution type**: 理论 + 实验
7. **Risk level**: LOW
8. **Estimated effort**: 3 person-weeks
9. **Closest existing work + delta**: SCOPE [P04] 用 RL 但训练成本高；RouteLLM [P02] 用离线训练但无法在线适应。本工作的 delta 在于用轻量 bandit 替代重量级 RL。

---

### IDEA-09: Cascaded Harness Routing with Adaptive Escalation

1. **Title**: Cascaded Harness Routing: Adaptive Escalation from Cheap to Expensive Agent Harnesses
2. **Thesis**: We show that a cascaded strategy across agent harnesses (start with cheapest, escalate on failure) reduces average cost by 35-50% compared to always using the most capable harness.
3. **Problem**: Gap G1 + G2 — 将级联思想从模型级扩展到 harness 级。
4. **Core mechanism**: 定义 harness 的成本层级（codex_subagent < opencode_cli < claude_cli < main_agent），先尝试最便宜的，仅在输出质量不达标时升级。质量评估用轻量信号（如编译通过、测试通过、自一致性）。
4. **Why non-obvious**: 现有级联工作（P01, P03）在模型级别操作。Harness 级级联的非直觉之处在于：harness 之间的能力差异不是简单的"更强/更弱"，而是"擅长不同东西"。级联策略需要考虑任务-harness 匹配度，而不仅仅是能力大小。
6. **Contribution type**: 系统 + 实验
7. **Risk level**: MEDIUM
8. **Estimated effort**: 4 person-weeks
9. **Closest existing work + delta**: FrugalGPT [P01] 的模型级级联；UCCI [P03] 的校准级联。本工作的 delta 在于 harness 级级联，需要处理异构能力差异。

---

### IDEA-10: Adversarial Robustness of Task Routers

1. **Title**: On the Adversarial Robustness of Task Routers: Can Small Perturbations Flip Routing Decisions?
2. **Thesis**: We show that existing task routing approaches are vulnerable to adversarial perturbations in task descriptions, and that adversarial training improves routing robustness by 40-60% with minimal cost increase.
3. **Problem**: 未被现有工作覆盖 — 路由器的鲁棒性从未被研究。
4. **Core mechanism**: 对任务描述施加小扰动（同义词替换、格式变化、上下文微调），测试路由器决策的稳定性。用对抗训练提升鲁棒性。
5. **Why non-obvious**: 这是一个"元研究"——不是改进路由，而是研究路由本身的可靠性。如果路由器对"请帮我修改 config 文件"和"请帮我修改配置文件"给出不同路由，说明路由器不可靠。
6. **Contribution type**: 分析 + 实验
7. **Risk level**: MEDIUM
8. **Estimated effort**: 4 person-weeks
9. **Closest existing work + delta**: 无直接相关工作。NLP 领域有对抗鲁棒性研究，但未应用于路由。本工作的 delta 在于首次研究 LLM 路由器的对抗鲁棒性。

---

### IDEA-11: Meta-Learning for Cross-Domain Task Routing

1. **Title**: Meta-Learning a Task Router: Cross-Domain Generalization for Coding Agent Routing
2. **Thesis**: We show that meta-learning a router across diverse coding domains (web, systems, data, ML) enables rapid adaptation to new domains with only 10-20 examples, outperforming domain-specific routers trained on 100+ examples.
3. **Problem**: Gap G3 + G5 — 路由器在新领域需要大量标注数据。
4. **Core mechanism**: 用 MAML 或 Prototypical Networks 在多个编码领域上元训练路由器，学习一个"好的初始化"，使得在新领域只需少量样本即可适应。
5. **Why non-obvious**: 现有路由器在单一领域训练。元学习的非直觉之处在于：不同编码领域的路由模式可能有共性（如"涉及多文件修改的任务更难"），元学习可以捕获这种跨领域共性。
6. **Contribution type**: 理论 + 实验
7. **Risk level**: HIGH
8. **Estimated effort**: 6 person-weeks
9. **Closest existing work + delta**: SCOPE [P04] 的零样本泛化是针对新模型而非新领域。本工作的 delta 在于跨领域元学习，目标是快速适应新的编码领域。

---

### IDEA-12: Predictive Cost Modeling for Pre-Routing Budget Allocation

1. **Title**: Predictive Cost Modeling: Pre-Routing Budget Allocation Based on Task Complexity Estimation
2. **Thesis**: We show that predicting the expected cost of a task before routing (based on task features) enables budget-aware routing that maximizes quality under a fixed cost budget.
3. **Problem**: Gap G3 — 现有路由器不预测成本，只在事后记录。
4. **Core mechanism**: 训练一个成本预测模型，输入任务特征，输出预期 token 用量和延迟。将预测成本作为路由决策的约束条件（预算内选最优）。
5. **Why non-obvious**: 这不是简单的"加一个成本特征"。关键洞察是：成本预测本身就是一个有价值的信号——如果模型预测某个任务成本很高，可能意味着任务复杂，需要更强的 harness。
6. **Contribution type**: 系统 + 实验
7. **Risk level**: LOW
8. **Estimated effort**: 3 person-weeks
9. **Closest existing work + delta**: FrugalGPT [P01] 用成本作为优化目标但不预测成本。本工作的 delta 在于将成本预测作为路由决策的前置信号。

---

## 想法质量自检

| 检查项 | 结果 |
|--------|------|
| 是否有"apply X to Y"但无surprising mechanism? | IDEA-11 (Meta-Learning) 有此风险，但跨领域迁移本身有non-trivial挑战 |
| 负结果是否同样可发表? | IDEA-03, IDEA-06, IDEA-10 的负结果有发表价值 |
| 是否挑战假设? | IDEA-03 (挑战分解-路由独立假设), IDEA-05 (挑战不确定性≠风险假设), IDEA-10 (挑战路由器可靠假设) |
| 风险分布 | LOW: 4 (01, 02, 08, 12), MEDIUM: 5 (04, 05, 07, 09, 10), HIGH: 3 (03, 06, 11) |
| 是否覆盖所有gaps? | G1: 03, 09; G2: 02, 09; G3: 01, 06, 07, 08; G4: 03; G5: 04; G6: 05, 06; G7: 未直接覆盖 (可作为future work) |

G7 (多后端异构路由基准缺失) 未直接覆盖，因为基准建设本身不是研究想法，而是基础设施工作。可在 IDEA-02 中作为附带贡献。
