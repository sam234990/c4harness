# Shared Memory 模块：筛选后想法

**日期**: 2026-06-24
**筛选标准**: Feasibility + Novelty + Impact + Prof. He 四维度，每维度 1-5 分，总分 >= 12/20 通过
**Prof. He 维度定义**: 是否能产出可发表的研究贡献（理论洞察、实证发现、或系统创新）

---

## 评分表

| ID | 想法 | Feasibility | Novelty | Impact | Prof. He | 总分 | 结果 |
|----|------|:-----------:|:-------:|:------:|:--------:|:----:|:----:|
| 1 | Directed vs. Free Retrieval | 4 | 3 | 4 | 4 | **15** | PASS |
| 2 | Dual-Track Reduces Pollution | 4 | 3 | 4 | 4 | **15** | PASS |
| 3 | Two-Phase Commit | 4 | 4 | 4 | 4 | **16** | PASS |
| 4 | Cost Ledger Feedback | 3 | 3 | 3 | 4 | **13** | PASS |
| 5 | Context Bundle Ablation | 4 | 2 | 3 | 3 | **12** | PASS |
| 6 | Provenance-Weighted Verification | 3 | 4 | 3 | 4 | **14** | PASS |
| 7 | Adaptive Fact Expiry | 3 | 3 | 3 | 4 | **13** | PASS |
| 8 | Memory-Aware Routing | 2 | 4 | 3 | 3 | **12** | PASS |
| 9 | Cost-Driven Retention | 3 | 4 | 3 | 4 | **14** | PASS |
| 10 | Cross-Harness Consistency | 3 | 3 | 2 | 3 | **11** | FAIL |
| 11 | Verifier Gatekeeper Ablation | 4 | 3 | 3 | 4 | **14** | PASS |
| 12 | Memory Compression | 4 | 2 | 3 | 3 | **12** | PASS |

---

## 淘汰的想法（总分 < 12）

### 想法 10: Cross-Harness Memory Consistency Protocol — 11/20

**淘汰理由**:
- **Feasibility 3**: 需要构造冲突场景，现实中冲突率可能很低
- **Novelty 3**: 分布式一致性是老问题，只是换了个场景
- **Impact 2**: 大多数 coding task 是独立的，冲突场景有限
- **Prof. He 3**: 贡献更偏工程而非研究洞察

**核心问题**: 把分布式系统的一致性协议搬到 multi-agent memory 听起来合理，但在"Single Writer, Few Readers"的并发模型下，真正的 fact 冲突很少发生。这个想法在"多个 worker 并行处理同一个文件"的场景下才有意义，但这种场景在 cost-aware routing 中会被刻意避免（主 agent 会协调依赖关系）。投入产出比不高。

---

## 通过的想法概览（总分 >= 12）

### Tier 1: 高分想法（14-16 分）— 核心验证

| ID | 想法 | 总分 | 核心价值 |
|----|------|:----:|----------|
| 3 | Two-Phase Commit | **16** | 验证设计文档最核心的创新点（worker 提案 → verifier 确认） |
| 1 | Directed vs. Free Retrieval | **15** | 验证 directed access 的核心假设（G3） |
| 2 | Dual-Track Reduces Pollution | **15** | 验证双轨架构的设计假设（G2） |
| 6 | Provenance-Weighted Verification | **14** | 跨 harness 场景的独特贡献 |
| 9 | Cost-Driven Retention | **14** | 成本与 memory 的交叉创新 |
| 11 | Verifier Gatekeeper Ablation | **14** | 直接指导 verifier 实现选型 |

### Tier 2: 中分想法（12-13 分）— 有价值的补充

| ID | 想法 | 总分 | 核心价值 |
|----|------|:----:|----------|
| 4 | Cost Ledger Feedback | **13** | 长期学习闭环，但需要大量数据 |
| 7 | Adaptive Fact Expiry | **13** | Fact lifecycle 的具体化，但较窄 |
| 5 | Context Bundle Ablation | **12** | directed access 的实操指导，但新颖性一般 |
| 8 | Memory-Aware Routing | **12** | 有创意但工程风险高 |
| 12 | Memory Compression | **12** | 实用但研究贡献有限 |

---

## 维度分析

### Feasibility 分布
- 4 分（易实现）: 想法 1, 2, 3, 5, 11, 12 — 这些主要需要实验设计，不需要复杂的系统改动
- 3 分（中等）: 想法 4, 6, 7, 9, 10 — 需要更复杂的机制实现或多 harness 协调
- 2 分（困难）: 想法 8 — 需要大量连续 session 数据和 memory-aware router 实现

### Novelty 分布
- 4 分（高度新颖）: 想法 3, 6, 8, 9 — 这些在现有文献中没有直接先例
- 3 分（中等新颖）: 想法 1, 2, 4, 7, 10, 11 — 核心思想有先例但应用场景新颖
- 2 分（新颖性有限）: 想法 5, 12 — 类似工作已有，只是换了场景

### Impact 分布
- 4 分（高影响）: 想法 1, 2, 3 — 这三个直接验证设计文档的核心假设
- 3 分（中等影响）: 想法 4, 5, 6, 7, 8, 9, 11, 12 — 有价值但影响范围有限
- 2 分（影响有限）: 想法 10 — 场景受限

### Prof. He 维度分布
- 4 分: 想法 1, 2, 3, 4, 6, 7, 9, 11 — 能产出可发表的理论洞察或实证发现
- 3 分: 想法 5, 8, 10, 12 — 贡献更偏工程或实操

---

## 筛选结论

共 12 个想法，通过 11 个（>= 12 分），淘汰 1 个（想法 10）。

**关键发现**:
1. **想法 3（Two-Phase Commit）得分最高（16）**，因为它直接测试设计文档最核心的创新——worker 提案 → verifier 确认的两步机制。这是整个 shared memory 设计的"杀手特性"，如果被证明有效，整个架构就有坚实基础。

2. **想法 1 和 2 并列第二（15）**，分别验证 directed access 和双轨架构。这三个想法（1, 2, 3）构成了对设计文档三大支柱的系统验证。

3. **Novelty 最高的想法是 3, 6, 8, 9**，其中想法 6（Provenance-Weighted Verification）和想法 9（Cost-Driven Retention）是跨 harness 场景独有的贡献，现有工作完全没涉及。

4. **Feasibility 最高的想法是 1, 2, 3, 5, 11, 12**，这些主要依赖实验设计，不需要复杂的系统改动，适合作为第一批验证目标。

**建议**: 进入深度评审的 top 3-4 应该从 Tier 1 中选择，优先选那些既高分又能互补覆盖设计支柱的想法。
