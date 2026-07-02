# Literature Landscape: Task Router for Cost-Aware Coding-Agent Routing

**Date**: 2026-06-23
**Papers analyzed**: 12
**Sources**: 用户指定论文列表 + 领域知识
**模块定位**: cost-aware coding-agent router 中的 Task Router 子模块

---

## Executive Summary

Task Router 是 cost-aware coding-agent router 的核心决策组件：给定一个编码任务，它需要判断任务难度（simple/medium/hard）、评估风险等级（read_only/patch/sensitive），并决定将任务路由到哪个后端执行（codex_subagent、claude_cli、opencode_cli、或 main_agent）。这一问题在 LLM 路由（LLM routing）研究谱系中处于"请求级路由"与"任务级编排"的交叉地带。

当前 LLM 路由研究已形成三条主要技术路线：(1) **级联路由（Cascade Routing）**，以 FrugalGPT [P01] 为代表，通过多模型串联逐级提升质量，可实现 98% 的成本削减；(2) **偏好数据训练的分类路由**，以 RouteLLM [P02] 为代表，利用人类偏好数据训练轻量路由器，在强弱模型间动态选择；(3) **不确定性校准路由**，以 UCCI [P03] 为代表，通过模型输出的校准不确定性决定是否需要升级到更强模型。2026 年的新工作进一步扩展了这一图景：SCOPE [P04] 引入强化学习训练路由器实现零样本泛化，GraphPlanner [P05] 将图结构记忆与 MDP 结合用于多 agent 路由，ACAR [P06] 利用自一致性方差进行多模型集成路由。

然而，现有研究存在一个根本性盲区：**所有路由器都在请求级别（request-level）工作，不分解任务**。它们假设每个输入是一个原子请求，而非一个可以拆分为子任务的复合目标。此外，没有路由器在不同的 agent harness 之间做选择（如 Codex CLI vs Claude CLI vs OpenCode CLI），也没有路由器利用成本账本（cost ledger）反馈来持续改进路由策略。这些恰好是 Task Router 模块需要填补的空白。

本报告分析 12 篇关键论文，识别出 4 个主题和 7 个研究空白，为 Task Router 的设计提供文献基础。

---

## Paper Table

| ID | Paper | Authors | Year | Venue | Method | Key Result | Relevance |
|----|-------|---------|------|-------|--------|------------|-----------|
| P01 | FrugalGPT: How to Use Large Language Models While Reducing Cost and Improving Performance | Chen et al. | 2023 | arXiv:2305.05176 (preprint) | LLM 级联：多模型串联，逐级升级直到置信度达标 | 在多种任务上实现高达 98% 的成本削减，同时保持或超越最佳单模型性能 | **高** — 级联思想可直接应用于 Task Router 的难度升级策略 |
| P02 | RouteLLM: Learning to Route LLMs with Preference Data | LMSYS (Ong et al.) | 2024 | arXiv (preprint) | 基于人类偏好数据训练轻量路由器，在强弱模型间选择 | 路由器仅用 1% 额外 FLOPs 即可保留 95% 以上的强模型质量 | **高** — 训练范式可迁移：用任务难度标签替代偏好数据 |
| P03 | UCCI: A Universal Calibrated Uncertainty Cascade Framework for LLM Routing | Kotte | 2026 | arXiv:2605.18796 (preprint) | 校准不确定性级联：用校准后的不确定性分数决定是否升级模型 | 在多个基准上实现 31% 成本削减，同时保持质量 | **高** — 不确定性校准可作为 Task Router 难度判断的信号之一 |
| P04 | SCOPE: Self-Consistency based Routing for LLMs with Reinforcement Learning | Cao et al. | 2026 | arXiv:2601.22323 (preprint) | RL 训练路由器，基于自一致性信号，零样本泛化到新模型 | 无需目标模型的标注数据即可路由，零样本泛化能力显著 | **中高** — 零样本泛化对新增后端（新 agent harness）有实际价值 |
| P05 | GraphPlanner: Graph Memory and MDP for Multi-Agent LLM Routing | Feng et al. | 2026 | arXiv:2604.23626 (preprint) | 图结构记忆 + MDP 建模，多 agent 间的任务分配与路由 | 在多 agent 协作场景中显著提升任务完成率和成本效率 | **高** — 最接近 Task Router 的多后端路由场景，图记忆可存储任务特征 |
| P06 | ACAR: Adaptive Consistency-Aware Routing for Multi-Model Ensembles | Kumaresan | 2026 | arXiv:2602.21231 (preprint) | 自一致性方差作为路由信号，自适应选择模型子集进行集成 | 在多个基准上优于静态集成，成本更低 | **中** — 方差信号可辅助判断任务难度，但编码任务的自一致性特征需验证 |
| P07 | A Unified Approach to Routing and Cascading for LLMs | Dekoninck et al. | 2024 | arXiv:2410.10347 (preprint) | 理论框架统一路由与级联，证明最优级联的理论性质 | 给出了级联路由的理论上界和最优策略 | **中** — 理论基础，可用于分析 Task Router 策略的最优性边界 |
| P08 | Dynamic Model Routing and Cascading for LLMs: A Survey | Moslem & Kelleher | 2026 | arXiv:2603.04445 (preprint) | 综述：系统梳理 LLM 路由与级联的方法分类 | 提出统一分类法：基于特征的路由、基于置信度的路由、基于学习的路由 | **中** — 提供方法分类框架，帮助定位 Task Router 的技术路线 |
| P09 | Routing, Cascades, and User Choice for LLMs | Mahmood | 2026 | arXiv:2602.09902 (preprint) | 博弈论分析：建模路由系统中的用户选择行为与策略交互 | 揭示路由策略与用户行为之间的纳什均衡结构 | **低中** — 理论性强，对 Task Router 的直接指导有限，但提供了策略分析视角 |
| P10 | Bridging On-Device and Cloud LLMs: RL-Based Routing | Fang et al. | 2025 | arXiv:2509.24050 (preprint) | RL 训练的本地-云端路由，在延迟和质量间权衡 | 在保持质量的前提下将 60% 以上请求路由到本地模型 | **中高** — 本地 vs 云端路由与 Task Router 的后端选择高度类比 |
| P11 | Small Model as Master Orchestrator: Lightweight Orchestration with Parallel Subtask Decomposition | Yuan et al. | 2026 | arXiv:2604.17009 (preprint) | 小模型作为主编排器，将任务分解为并行子任务并分配给不同模型 | 小模型编排器在复杂任务上接近大模型性能，成本大幅降低 | **高** — 直接对应 Task Router 的"分解 + 路由"双重职责 |
| P12 | Code as Agent Harness: A Survey | Ning et al. | 2026 | arXiv:2605.18747 (preprint) | 综述：代码作为 agent 基础设施的设计模式与能力边界 | 系统梳理 code agent 的架构模式，包括 harness 层的设计选择 | **高** — 直接描述 Task Router 需要选择的各类 agent harness |

---

## Thematic Analysis

### Theme 1: 级联路由与成本优化（Cascade Routing & Cost Optimization）

**Status**: mature（基础方法已确立，2026 年仍在持续改进）
**Dominant approach**: 多模型串联，逐级升级，直到输出置信度超过阈值
**Papers**: P01, P03, P07

级联路由是 LLM 成本优化最经典的技术路线。FrugalGPT [P01] 首次系统性地展示了级联策略的巨大潜力：先用廉价模型处理简单请求，仅在置信度不足时升级到更强模型，在多个基准上实现 98% 的成本削减。这一思想的核心假设是：任务难度分布是长尾的，大多数请求可以被弱模型解决。

UCCI [P03] 在此基础上引入了校准不确定性（calibrated uncertainty）作为级联触发信号，解决了原始级联方法中置信度校准不准的问题。通过温度缩放等校准技术，UCCI 在 31% 成本削减的同时保持了输出质量。Dekoninck et al. [P07] 则从理论角度证明了最优级联策略的性质，给出了路由收益的理论上界。

对 Task Router 的启示：级联思想可以迁移到 agent harness 选择中——先尝试低成本的 codex_subagent，仅在任务被判定为 hard 或 sensitive 时升级到 main_agent。但现有级联工作都在模型级别操作，尚未扩展到 agent harness 级别。

### Theme 2: 学习型路由器（Learned Routers）

**Status**: active（2024-2026 年快速发展，多种训练范式涌现）
**Dominant approach**: 用标注数据或偏好数据训练轻量分类器作为路由器
**Papers**: P02, P04, P05, P06

RouteLLM [P02] 开创了用人类偏好数据训练路由器的范式：给定一对强弱模型的输出，训练一个轻量分类器判断哪个模型更适合当前请求。该方法仅需 1% 额外 FLOPs 即可保留 95% 以上的强模型质量。SCOPE [P04] 进一步引入强化学习训练路由器，并利用自一致性（self-consistency）作为路由信号，实现了对未见过模型的零样本泛化。

GraphPlanner [P05] 将路由问题建模为图结构上的 MDP（马尔可夫决策过程），用图记忆存储任务特征和历史路由结果，适合多 agent 场景。ACAR [P06] 则关注多模型集成场景，用自一致性方差自适应地选择模型子集。

Fang et al. [P10] 的本地-云端路由与 Task Router 的后端选择高度类比：他们用 RL 训练路由器，在本地小模型和云端大模型之间动态选择，在保持质量的前提下将 60% 以上请求路由到本地模型。

对 Task Router 的启示：(1) RouteLLM 的偏好数据训练范式可以迁移——用"任务特征 → 最优后端"的标注数据训练路由器；(2) SCOPE 的零样本泛化能力对新增后端（如未来引入新的 agent harness）有实际价值；(3) GraphPlanner 的图记忆可以存储任务特征-路由结果的历史对应关系。

### Theme 3: 任务分解与编排（Task Decomposition & Orchestration）

**Status**: emerging（2026 年刚开始出现将分解与路由结合的工作）
**Dominant approach**: 用轻量模型将复杂任务拆分为子任务，再分配给不同模型执行
**Papers**: P11, P12

这一主题与 Task Router 的关系最为直接。Yuan et al. [P11] 提出用小模型作为主编排器（master orchestrator），将复杂任务分解为可并行执行的子任务，再分配给不同能力的模型。这与 Task Router 的"分解 + 路由"双重职责高度一致。他们的实验表明，小模型编排器在复杂任务上可以接近大模型的性能，同时大幅降低成本。

Ning et al. [P12] 的综述系统梳理了 code agent 的架构模式，将 agent harness 定义为"代码作为 agent 基础设施"的设计层。该综述涵盖了 Codex、Claude CLI、OpenCode 等不同 harness 的能力边界和适用场景，为 Task Router 的后端选择提供了直接参考。

对 Task Router 的启示：(1) Task Router 可以借鉴 [P11] 的"小模型编排"思路，用轻量模型做任务分解和子任务路由；(2) [P12] 的 harness 分类可以直接映射到 Task Router 的后端枚举（codex_subagent, claude_cli, opencode_cli, main_agent）；(3) 但现有工作都没有将分解和路由耦合在一起优化——分解策略和路由策略是独立设计的。

### Theme 4: 路由理论与策略分析（Routing Theory & Strategy Analysis）

**Status**: active（理论分析持续推进，但与实践的差距较大）
**Dominant approach**: 博弈论、信息论、最优化理论建模路由策略
**Papers**: P07, P08, P09

Moslem & Kelleher [P08] 的综述提出了 LLM 路由与级联的统一分类法，将现有方法分为基于特征的路由（feature-based）、基于置信度的路由（confidence-based）和基于学习的路由（learning-based）三大类。这一分类框架帮助我们定位 Task Router 的技术路线：它需要同时利用任务特征（文件范围、读写模式、风险等级）和学习到的路由策略。

Mahmood [P09] 从博弈论角度分析路由系统，建模了路由策略与用户行为之间的策略交互，揭示了纳什均衡结构。虽然理论性强，但它提醒我们：路由系统的设计不能忽略用户（或主 agent）对路由结果的反应和适应。

对 Task Router 的启示：(1) [P08] 的分类法可用于设计 Task Router 的模块架构——特征提取器、置信度评估器、策略学习器；(2) [P09] 的博弈论视角提醒我们，Task Router 的策略会受到主 agent 行为的影响，需要考虑策略的稳定性。

---

## Gap Identification Matrix

| Gap ID | Gap Description | Evidence (papers) | Gap Type | Confidence |
|--------|----------------|-------------------|----------|------------|
| G1 | **请求级路由 vs 任务级路由**：所有现有路由器都在请求级别工作，将每个输入视为原子请求，不进行任务分解。Task Router 需要先判断任务是否需要分解，再对子任务分别路由。 | P01, P02, P03, P04, P05, P06 均假设原子请求；P11 虽涉及分解但路由策略独立于分解策略 | overlooked formulation | HIGH |
| G2 | **Agent harness 选择空白**：没有路由器在不同 agent harness（如 Codex CLI vs Claude CLI vs OpenCode CLI）之间做选择。现有工作都在模型级别路由，而 Task Router 需要在 harness 级别路由，每个 harness 有不同的工具链、上下文窗口、成本结构。 | P01-P10 均在模型级别路由；P12 描述了 harness 差异但未涉及路由 | cross-domain transfer | HIGH |
| G3 | **Cost ledger 反馈闭环缺失**：没有路由器利用实际执行的成本数据（token 用量、延迟、成功率）来持续改进路由策略。现有方法要么用静态阈值，要么用离线训练的分类器。 | P01-P06 的路由器训练与实际成本数据解耦 | untested assumption | HIGH |
| G4 | **分解与路由未耦合优化**：P11 的任务分解和 P01-P06 的路由策略是独立设计的。没有工作将"如何分解"和"分解后如何路由"作为一个联合优化问题来处理。 | P11（分解）vs P01-P06（路由）——无交叉 | overlooked formulation | HIGH |
| G5 | **编码任务特征未被利用**：现有路由器使用的特征（文本嵌入、logit 置信度、自一致性方差）是通用的。编码任务有独特的信号：文件范围（scope）、读写模式（read_only/patch/sensitive）、依赖图复杂度、测试覆盖需求等，这些未被任何路由器使用。 | P01-P10 均未针对编码任务设计特征 | cross-domain transfer | HIGH |
| G6 | **风险感知路由缺失**：没有路由器考虑操作风险（如写文件 vs 读文件 vs 修改生产配置）。Task Router 需要将风险等级纳入路由决策：高风险操作应路由到更可靠的后端。 | P01-P10 均以质量/成本为优化目标，未考虑风险 | overlooked formulation | MEDIUM |
| G7 | **多后端异构路由缺乏基准**：现有路由基准（如 LMSYS 的 RouteLLM 评测）只涉及模型选择，不涉及 agent harness 选择。缺乏一个涵盖 Codex/Claude CLI/OpenCode 等异构后端的路由评测基准。 | P02, P04, P06 的评测均在模型级别 | missing diagnostic | HIGH |

---

## 与 Task Router 设计的映射

基于上述分析，Task Router 的设计可以借鉴以下技术路线：

| Task Router 能力 | 借鉴来源 | 实现思路 |
|-----------------|---------|---------|
| 难度分类 (simple/medium/hard) | P02 (RouteLLM), P03 (UCCI) | 用任务特征训练轻量分类器，或用校准不确定性作为代理信号 |
| 风险评估 (read_only/patch/sensitive) | 无直接来源（G6 空白） | 基于规则 + 学习混合：规则捕获明确模式（如修改 .env = sensitive），学习处理模糊情况 |
| 后端选择 | P05 (GraphPlanner), P10 (Fang et al.) | 图记忆存储历史路由结果，RL 训练后端选择策略 |
| 任务分解决策 | P11 (Small Model as Master Orchestrator) | 小模型判断是否需要分解，输出子任务 DAG |
| 成本反馈学习 | G3 空白（需创新） | Cost ledger 记录每次路由的实际成本/质量，定期更新路由策略 |

---

## References

```
[P01]  Chen, L., Zaharia, M., & Zou, J. (2023). FrugalGPT: How to Use Large Language
       Models While Reducing Cost and Improving Performance. arXiv:2305.05176.

[P02]  Ong, I., et al. (2024). RouteLLM: Learning to Route LLMs with Preference Data.
       arXiv (LMSYS).

[P03]  Kotte, V. (2026). UCCI: A Universal Calibrated Uncertainty Cascade Framework
       for LLM Routing. arXiv:2605.18796.

[P04]  Cao, Y., et al. (2026). SCOPE: Self-Consistency based Pruning and Efficient
       Routing for LLMs with Reinforcement Learning. arXiv:2601.22323.

[P05]  Feng, Y., et al. (2026). GraphPlanner: Graph Memory and MDP for Multi-Agent
       LLM Routing. arXiv:2604.23626.

[P06]  Kumaresan, A. (2026). ACAR: Adaptive Consistency-Aware Routing for Multi-Model
       Ensembles. arXiv:2602.21231.

[P07]  Dekoninck, J., et al. (2024). A Unified Approach to Routing and Cascading for
       LLMs. arXiv:2410.10347.

[P08]  Moslem, Y. & Kelleher, J. D. (2026). Dynamic Model Routing and Cascading for
       LLMs: A Survey. arXiv:2603.04445.

[P09]  Mahmood, A. (2026). Routing, Cascades, and User Choice for LLMs.
       arXiv:2602.09902.

[P10]  Fang, Y., et al. (2025). Bridging On-Device and Cloud LLMs: RL-Based Routing.
       arXiv:2509.24050.

[P11]  Yuan, S., et al. (2026). Small Model as Master Orchestrator: Lightweight
       Orchestration with Parallel Subtask Decomposition. arXiv:2604.17009.

[P12]  Ning, Y., et al. (2026). Code as Agent Harness: A Survey.
       arXiv:2605.18747.
```

---

*本文档为 Task Router 模块的文献基础，后续设计决策应参考上述空白分析（尤其是 G1-G5）来确保创新性。*
