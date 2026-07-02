# Delegator Module: Filtered Research Ideas

**筛选标准**: Feasibility + Novelty + Impact + Prof. He 4-dimension（阈值 12/20）
**评分**: 每项 1-5 分，总分 20 分

---

## 评分矩阵

| # | Idea | Feasibility | Novelty | Impact | Prof.He | Total | Result |
|---|------|-------------|---------|--------|---------|-------|--------|
| 1 | BackendAdapter Protocol-Agnostic Abstraction | 4 | 3 | 4 | 4 | 15 | PASS |
| 2 | Attested Backend Capability Cards | 3 | 4 | 4 | 3 | 14 | PASS |
| 3 | Structured Error Taxonomy for CLI Delegation | 4 | 3 | 4 | 4 | 15 | PASS |
| 4 | Unified Output Normalization Protocol | 4 | 3 | 4 | 4 | 15 | PASS |
| 5 | Async Delegation with Progress Callbacks | 3 | 3 | 3 | 3 | 12 | PASS (borderline) |
| 6 | Cost-Aware Delegation Policy via RL | 2 | 4 | 4 | 3 | 13 | PASS |
| 7 | Privilege-Minimal Backend Selection | 3 | 3 | 3 | 3 | 12 | PASS (borderline) |
| 8 | Delegation Contract Protocol | 4 | 3 | 3 | 3 | 13 | PASS |
| 9 | Provenance-Aware Delegation Audit Trail | 3 | 3 | 3 | 3 | 12 | PASS (borderline) |
| 10 | Adaptive Fallback Chain for Backend Failures | 4 | 4 | 5 | 4 | 17 | PASS (top) |
| 11 | Task-Backend Affinity Learning | 3 | 4 | 5 | 3 | 15 | PASS |
| 12 | Speculative Parallel Delegation | 2 | 4 | 3 | 3 | 12 | PASS (borderline) |

---

## 通过筛选的想法（10/12）

### Tier 1: 强通过（>=15 分）

**Idea 10: Adaptive Fallback Chain for Backend Failures** (17/20)
- Feasibility 4: circuit breaker 是成熟模式，自适应调整有工程基础
- Novelty 4: 将容错领域的成熟技术迁移到 agent 后端委派是新颖的
- Impact 5: 直接解决后端失败率高（7-50%）的核心痛点
- Prof.He 4: 问题定义清晰，技术路线成熟，有明确的工程价值

**Idea 1: BackendAdapter Protocol-Agnostic Abstraction** (15/20)
- Feasibility 4: 技术路线清晰，ToolRegistry [P09] 提供了参考
- Novelty 3: 扩展已有工作到 harness 级，增量创新
- Impact 4: 统一接口是整个 Delegator 的基础
- Prof.He 4: 系统设计贡献，有明确的工程价值

**Idea 3: Structured Error Taxonomy for CLI Delegation** (15/20)
- Feasibility 4: 错误分类是成熟工程实践
- Novelty 3: 系统化分类在 agent 领域是新的
- Impact 4: 直接提升 Delegator 的鲁棒性
- Prof.He 4: 问题定义清晰，有实证基础

**Idea 4: Unified Output Normalization Protocol** (15/20)
- Feasibility 4: 协议设计是工程问题
- Novelty 3: 格式统一看似简单但语义对齐有深度
- Impact 4: 是上层模块（cost ledger, router）的基础
- Prof.He 4: 协议规范贡献，有明确的工程价值

**Idea 11: Task-Backend Affinity Learning** (15/20)
- Feasibility 3: 需要足够的执行数据
- Novelty 4: 从实际执行数据学习任务-后端匹配是新颖的
- Impact 5: 直接优化成本和成功率
- Prof.He 3: 机器学习贡献，但数据需求是风险

### Tier 2: 通过（12-14 分）

**Idea 2: Attested Backend Capability Cards** (14/20)
- Feasibility 3: 需要足够的执行数据建立能力画像
- Novelty 4: 将来源悖论 [P13] 具体化到后端能力声明
- Impact 4: 提升 Delegator 的路由决策质量
- Prof.He 3: 机制设计贡献，但冷启动是风险

**Idea 6: Cost-Aware Delegation Policy via RL** (13/20)
- Feasibility 2: 需要大量训练数据，RL 训练不稳定
- Novelty 4: 异构后端成本结构下的 RL 委派是新颖的
- Impact 4: 直接优化成本-成功率权衡
- Prof.He 3: 算法贡献，但数据和训练是主要风险

**Idea 8: Delegation Contract Protocol** (13/20)
- Feasibility 4: 合约格式设计是工程问题
- Novelty 3: 具体化 Prakash [P13] 的概念
- Impact 3: 提升可审计性和可预测性
- Prof.He 3: 协议设计贡献

**Idea 5: Async Delegation with Progress Callbacks** (12/20)
- Feasibility 3: 不同后端的进度报告能力差异大
- Novelty 3: A2A [P04] 已提出类似概念
- Impact 3: 对长时任务重要但非核心痛点
- Prof.He 3: 系统设计贡献

**Idea 7: Privilege-Minimal Backend Selection** (12/20)
- Feasibility 3: 权限级别定义可能过于粗糙
- Novelty 3: 将 Yang et al. [P10] 迁移到后端选择
- Impact 3: 安全改进但非核心痛点
- Prof.He 3: 安全机制贡献

**Idea 9: Provenance-Aware Delegation Audit Trail** (12/20)
- Feasibility 3: 密码学技术成熟但集成有挑战
- Novelty 3: 扩展 HDP [P14] 到 agent 委派
- Impact 3: 合规和数据收集价值
- Prof.He 3: 安全协议贡献

**Idea 12: Speculative Parallel Delegation** (12/20)
- Feasibility 2: 并行执行的资源消耗和协调复杂度高
- Novelty 4: 投机执行在 agent 委派中是新颖的
- Impact 3: 延迟优化但成本可能过高
- Prof.He 3: 算法贡献

---

## 淘汰的想法（2/12）

无。所有 12 个想法均通过 12/20 阈值。但 Idea 5, 7, 9, 12 处于边界，深度筛选阶段可能被淘汰。

---

## 关键观察

1. **工程导向 vs 学术新颖性**: 通过筛选的想法中，工程导向（Idea 1, 3, 4, 8）占比较高。这反映了 Delegator 模块的本质——它是一个系统模块，而非纯算法问题。
2. **数据依赖**: Idea 2, 6, 11 都依赖足够的执行数据。在项目早期，这些想法可能难以充分验证。
3. **核心痛点**: Idea 10（自适应降级链）得分最高，因为它直接解决了后端失败率高这一核心痛点，且技术路线成熟。
4. **组合价值**: 多个想法可以组合——例如 Idea 1（统一接口）+ Idea 4（统一输出）+ Idea 10（降级链）构成一个完整的 Delegator 核心架构。
