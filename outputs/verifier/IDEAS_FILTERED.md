# Verifier 模块：过滤后的研究想法

**过滤日期**: 2026-06-24
**过滤标准**: Feasibility + Novelty + Impact + Prof. He 4-dimension (阈值 12/20)
**通过阈值**: 12/20

---

## 评分维度说明

| 维度 | 权重 | 说明 |
|------|------|------|
| Feasibility | /5 | 技术可行性、资源需求、时间成本 |
| Novelty | /5 | 与现有工作的差异化程度 |
| Impact | /5 | 对领域和实际应用的潜在影响 |
| Prof. He 4-dim | /5 | Prof. He 的四维评估（问题重要性、方法新颖性、实验充分性、写作清晰性） |
| **总分** | **/20** | |

---

## 全部想法评分

| ID | Title | Feasibility | Novelty | Impact | He-4dim | Total | Verdict |
|----|-------|-------------|---------|--------|---------|-------|---------|
| I1 | Lightweight Code Sub-Result Verifier (LCSV) | 4 | 4 | 4 | 4 | **16** | PASS |
| I2 | Two-Step Commit Protocol (2SC) | 5 | 5 | 4 | 3 | **17** | PASS |
| I3 | Policy Verification Layer (PVL) | 5 | 4 | 4 | 2 | **15** | PASS |
| I4 | Execution-Based Grounding Verification (EBGV) | 3 | 3 | 4 | 3 | **13** | PASS |
| I5 | Confidence-Adaptive Verification Escalation (CAVE) | 4 | 5 | 4 | 4 | **17** | PASS |
| I6 | Adversarial Robustness of Verifier (ARV) | 3 | 3 | 4 | 3 | **13** | PASS |
| I7 | Contrastive Multi-Worker Fact Selection (CMFS) | 4 | 3 | 3 | 2 | **12** | PASS (边界) |
| I8 | CodeTask Grounding Verification Benchmark (CGVB) | 5 | 3 | 3 | 2 | **13** | PASS |
| I9 | Verifier-in-the-Loop Worker Self-Improvement (VLWSI) | 3 | 4 | 4 | 3 | **14** | PASS |
| I10 | Atomic Claim Decomposition for Granular Verification (ACDGV) | 4 | 3 | 3 | 3 | **13** | PASS |

---

## 过滤结果

**通过**: 10/10（全部通过阈值 12/20）

**说明**: 所有想法均达到阈值。这是因为 landscape 分析已经识别了明确的研究空白 (G1-G7)，每个想法都针对特定空白，具有清晰的问题定义和解决路径。

---

## 第二轮过滤：深度筛选 Top 4

基于综合评分和战略考量，选择 Top 4 进入深度筛选：

### Tier 1 (Top 2): 直接进入精炼

| Rank | ID | Title | Total | 选择理由 |
|------|-----|-------|-------|---------|
| 1 | I2 | Two-Step Commit Protocol (2SC) | 17 | 最高的新颖性得分；解决 shared memory 安全这一被忽视的核心问题；协议设计清晰，实现可行 |
| 2 | I5 | Confidence-Adaptive Verification Escalation (CAVE) | 17 | 最高的新颖性得分；直接挑战"强模型更好"的假设；有 Li [P11] 的实证支持 |

### Tier 2 (Next 2): 进入深度筛选

| Rank | ID | Title | Total | 选择理由 |
|------|-----|-------|-------|---------|
| 3 | I1 | Lightweight Code Sub-Result Verifier (LCSV) | 16 | 最实用的想法；直接解决 G1/G2 空白；可作为其他想法的基础设施 |
| 4 | I3 | Policy Verification Layer (PVL) | 15 | 独特的安全视角；"过度帮助"是新型风险；与 2SC 互补 |

### 未进入深度筛选的想法

| ID | Title | Total | 淘汰理由 |
|----|-------|-------|---------|
| I9 | VLWSI | 14 | 依赖其他验证组件，更适合作为后续工作 |
| I4 | EBGV | 13 | 沙箱执行的安全风险较高，且不是所有输出都可执行 |
| I6 | ARV | 13 | 攻击策略定义可能不全面，问题范围较窄 |
| I8 | CGVB | 13 | 基础设施贡献，论文影响力有限 |
| I10 | ACDGV | 13 | 与 LCSV 高度重叠，LCSV 更全面 |
| I7 | CMFS | 12 | 边界通过；多 worker 冗余执行的假设不一定成立 |

---

## 战略分析

### 最佳组合

**I2 (2SC) + I5 (CAVE)** 作为主攻方向：
- I2 解决"如何安全地写入 shared memory"（协议层）
- I5 解决"如何高效地验证 worker 输出"（算法层）
- 两者互补，可构成完整的 verifier 架构

**I1 (LCSV) + I3 (PVL)** 作为备选方向：
- I1 是基础设施（四层验证流水线）
- I3 是安全增强（策略验证层）
- 更偏工程，但实用性更强

### 风险提示

1. **I2 的风险**: 协议设计可能被认为"不够 AI"——需要强调其在 LLM agent 系统中的新颖应用
2. **I5 的风险**: 置信度校准的技术难度可能被低估——需要充分的实验验证
3. **I1 的风险**: 可能被认为贡献不够新颖——需要强调"中间结果验证"这一新问题定义
4. **I3 的风险**: "过度帮助"的定义可能有争议——需要清晰的形式化定义
