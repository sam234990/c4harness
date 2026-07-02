# Literature Landscape: Verifier Module for Cost-Aware Coding-Agent Router

**Date**: 2026-06-23
**Papers analyzed**: 18
**Sources**: arXiv API 搜索 + 用户指定论文列表
**模块定位**: cost-aware coding-agent router 中的 Verifier 子模块

---

## Executive Summary

Verifier 是 cost-aware coding-agent router 的质量守门人：廉价 worker 完成子任务后，Verifier 在结果写入 shared memory 之前进行四层验证——结构验证（是否有 summary/evidence/next_steps）、接地验证（evidence 路径是否存在、行号是否有效）、策略验证（read-only 任务未修改文件、无敏感数据泄露）、质量验证（结论与证据一致、给出可操作的下一步）。这一设计的核心思想是"worker 提议 / verifier 确认"的两步提交模式（two-step commit），确保 shared memory 中只包含经过验证的高质量事实。

当前文献中，与 Verifier 最相关的研究分布在三个交叉领域：(1) **LLM 输出事实性验证**，以 SAFE [P05]、DiVA [P08]、MedScore [P03] 为代表，通过分解-验证（decompose-then-verify）范式检查 LLM 输出的 factual accuracy；(2) **Agent 自反思与自纠正**，以 SuperCorrect [P10]、STeP [P12]、Perceptual Self-Reflection [P09] 为代表，让 agent 在执行后自我检查并修正错误；(3) **代码生成验证与测试**，以 CSV [P15]、VerilogReader [P16]、RestTSLLM [P17] 为代表，利用代码执行和测试来验证生成代码的正确性。

然而，现有研究存在一个根本性盲区：**所有验证工作都针对最终输出（final output），而非多 agent 系统中的中间 worker 结果**。没有轻量级 verifier 专门设计用于编码任务的子结果验证；没有"worker 提议 / verifier 确认"的两步内存提交模式；策略验证（read-only 执行、敏感数据防护）在 LLM agent 文献中完全缺失；也没有 verifier 能在置信度不足时自动升级到更强模型。此外，shared memory 在多 agent 编码系统中的安全性和隐私性（XAMT [P07]、MRMMIA [P06]）尚属未被充分研究的领域。

本报告分析 18 篇关键论文，识别出 4 个主题和 7 个研究空白，为 Verifier 模块的设计提供文献基础。

---

## Paper Table

| ID | Paper | Authors | Year | Venue | Method | Key Result | Relevance |
|----|-------|---------|------|-------|--------|------------|-----------|
| P01 | Long-form factuality in large language models | Wei et al. | 2024 | arXiv:2403.18802 (preprint) | SAFE: LLM agent 分解长文本为独立事实，用搜索验证每个事实 | SAFE 在 16k 事实标注上与人类标注者 72% 一致，胜率 76%，成本低 20 倍 | **高** — 分解-验证范式可直接迁移到 Verifier 的接地验证 |
| P02 | OpenFactCheck: Building, Benchmarking Customized Fact-Checking Systems | Wang et al. | 2024 | arXiv:2405.05583 (preprint) | 统一框架：CUSTCHECKER 定制事实检查 + LLMEVAL 评估 LLM 事实性 + CHECKEREVAL 评估检查器 | 提供可定制的事实检查流水线，支持文档级和声明级验证 | **中高** — 框架设计思路可借鉴：可定制的验证器 + 评估器 |
| P03 | MedScore: Generalizable Factuality Evaluation of Free-Form Medical Answers | Huang et al. | 2025 | arXiv:2505.18452 (preprint) | 条件感知的事实分解 + 领域语料验证 | 提取有效事实数量是现有方法的 3 倍，减少幻觉和模糊引用 | **中** — 条件感知分解思路可迁移到编码上下文的验证 |
| P04 | How Does Response Length Affect Long-Form Factuality | Zhao et al. | 2025 | arXiv:2505.23295 (preprint) | 双层事实性评估框架，研究响应长度与事实性的关系 | 更长的响应事实精度更低；facts exhaustion（可靠知识耗尽）是主因 | **中** — 提醒 Verifier 需要对长 worker 输出的事实性衰减保持警惕 |
| P05 | Long-form factuality in large language models (SAFE) | Wei et al. | 2024 | Google DeepMind, arXiv:2403.18802 | LLM agent 作为自动评估器，分解+搜索验证 | 超越人类标注者，成本低 20 倍 | **高** — 核心验证范式 |
| P06 | MRMMIA: Membership Inference Attacks on Memory in Chat Agents | Chen et al. | 2026 | arXiv:2605.27825 (preprint) | 针对 chat agent 内存的成员推断攻击 | 揭示 agent memory 存在严重的隐私泄露风险 | **高** — 直接影响 Verifier 的策略验证层：需要检查 worker 输出是否泄露敏感数据 |
| P07 | XAMT: Bilevel Optimization for Covert Memory Tampering | Sharma et al. | 2025 | arXiv:2512.15790 (preprint) | 双层优化实现隐蔽内存篡改 | 展示 shared memory 可被恶意篡改且难以检测 | **高** — shared memory 安全性直接威胁 Verifier 的信任基础 |
| P08 | DiVA: Fine-grained Factuality Verification with Agentic-Discriminative Verifier | Huang et al. | 2026 | arXiv:2601.03605 (preprint) | 混合框架：生成式模型的 agent 搜索能力 + 判别式模型的精确评分能力 | 在细粒度事实性验证上显著超越现有方法 | **高** — agent+判别器混合架构可作为 Verifier 的设计蓝图 |
| P09 | Perceptual Self-Reflection in Agentic Physics Simulation Code Generation | Shende & Camburn | 2026 | arXiv:2602.12311 (preprint) | 视觉自反思：分析渲染帧而非代码结构，检测"语法正确但物理错误"的输出 | 大多数场景达到目标准确率阈值，成本约 $0.20/动画 | **中高** — 解决"oracle gap"的思路可迁移到编码任务：不只检查代码结构，还检查运行结果 |
| P10 | SuperCorrect: Advancing Small LLM Reasoning with Thought Template Distillation and Self-Correction | Yang et al. | 2024 | arXiv:2410.09008 (preprint) | 教师模型监督学生的推理和反思过程，跨模型 DPO 增强自纠正 | SuperCorrect-7B 超越 DeepSeekMath-7B 7.8% (MATH) | **中** — 教师-学生纠正模式可类比为 verifier（强模型）纠正 worker（弱模型） |
| P11 | Decomposing LLM Self-Correction: The Accuracy-Correction Paradox and Error Depth Hypothesis | Li | 2025 | arXiv:2601.00828 (preprint) | 将自纠正分解为错误检测、定位、纠正三个子能力 | 弱模型自纠正率反而更高（26.8% vs 16.7%）；错误检测不预测纠正成功 | **中高** — 挑战了"强模型更好纠正"的假设，对 Verifier 升级策略有重要启示 |
| P12 | STeP: Training LLM-Based Agents with Synthetic Self-Reflected Trajectories and Partial Masking | Chen et al. | 2025 | arXiv:2505.20023 (preprint) | 合成自反思轨迹训练 agent，部分遮蔽防止内化错误步骤 | 在 ALFWorld/WebShop/SciWorld 上全面改进 | **中** — 自反思轨迹的"错误-纠正"结构与 Verifier 的验证-反馈循环相似 |
| P13 | MACLA: Memory-Augmented Contrastive Learning Agent | Forouzandeh et al. | 2025 | arXiv:2512.18950 (preprint) | 贝叶斯选择 + 对比精炼用于 agent memory | 在记忆质量和检索效率上优于基线 | **中** — 记忆选择中的质量评估机制可为 Verifier 的质量验证提供参考 |
| P14 | MemCoder: Your Code Agent Can Grow Alongside You with Structured Memory | Deng et al. | 2026 | arXiv:2603.13258 (preprint) | 结构化记忆 + 验证反馈用于 agent 行为纠正 | agent 可以从验证反馈中学习并改进 | **高** — 验证反馈纠正 agent 行为的思路直接对应 Verifier 的反馈机制 |
| P15 | Too Helpful to Be Safe | Chen et al. | 2026 | arXiv:2601.10758 (preprint) | 分析 agent 为完成任务绕过安全约束的行为 | 揭示"过度帮助"导致安全约束被绕过的系统性风险 | **高** — 直接对应 Verifier 的策略验证：read-only 任务不应修改文件 |
| P16 | Solving Challenging Math Word Problems Using GPT-4 Code Interpreter with Code-based Self-Verification | Zhou et al. | 2023 | arXiv:2308.07921 (preprint) | 代码自验证：用代码验证数学答案，验证失败自动修正 | MATH 数据集零样本准确率从 53.9% 提升到 84.3% | **中高** — 代码执行验证思路可迁移到编码任务的结果验证 |
| P17 | VerilogReader: LLM-Aided Hardware Test Generation | Ma et al. | 2024 | arXiv:2406.04373 (preprint) | LLM 作为 Verilog 代码阅读器，理解代码逻辑生成测试激励 | 在 LLM 理解范围内的设计上优于随机测试 | **低中** — 硬件验证的思路有启发性，但与编码任务差距较大 |
| P18 | Combining TSL and LLM to Automate REST API Testing | Barradas et al. | 2025 | arXiv:2509.05540 (preprint) | TSL + LLM 自动化 REST API 测试生成 | Claude 3.5 Sonnet 在所有指标上最优 | **低中** — API 测试生成思路可辅助 Verifier 的接地验证（验证 API 路径有效性） |

---

## Thematic Analysis

### Theme 1: LLM 输出事实性验证（Factuality Verification of LLM Outputs）

**Status**: active（2024-2026 年快速发展，从二元判断到细粒度验证）
**Dominant approach**: 分解-验证（decompose-then-verify）：将长文本分解为独立事实，逐条验证
**Papers**: P01, P02, P03, P04, P05, P08

这一主题是 Verifier 最直接的文献基础。SAFE [P01/P05] 开创了"LLM agent 作为自动验证器"的范式：先将长文本分解为独立事实，再通过搜索验证每条事实的准确性。该方法在 16k 条事实标注上与人类标注者 72% 一致，且成本低 20 倍。这一范式的核心假设是：事实可以被原子化分解，每条事实可以独立验证。

MedScore [P03] 将这一范式扩展到医疗领域，引入了条件感知（condition-aware）的事实分解——同一条事实在不同条件下可能有不同的正确性判断。这对编码任务有重要启示：代码片段的正确性取决于上下文（文件类型、项目约定、依赖版本）。

DiVA [P08] 代表了最新的进展：它将生成式模型的搜索能力与判别式模型的精确评分能力结合，实现了细粒度事实性验证（而非二元判断）。这一混合架构可直接作为 Verifier 的设计蓝图——用 agent 能力搜索证据，用判别器精确评分。

Zhao et al. [P04] 的发现对 Verifier 有重要警示：更长的响应事实精度更低，主要原因是 facts exhaustion（可靠知识耗尽）。这意味着 worker 输出越长，Verifier 需要越警惕。

OpenFactCheck [P02] 提供了可定制验证器的框架设计思路：CUSTCHECKER（定制检查器）+ LLMEVAL（评估 LLM）+ CHECKEREVAL（评估检查器）的三层架构，可以迁移到 Verifier 的设计中。

**对 Verifier 的启示**：(1) 分解-验证范式可直接应用于接地验证——将 worker 输出分解为可验证的声明（路径存在、行号有效、结论有依据）；(2) 条件感知分解提醒我们，验证标准应根据任务类型（read_only vs patch vs sensitive）动态调整；(3) 混合架构（agent 搜索 + 判别器评分）可作为 Verifier 的核心架构。

### Theme 2: Agent 自反思与自纠正（Agent Self-Reflection & Self-Correction）

**Status**: active（2024-2026 年快速发展，但自纠正效果仍有争议）
**Dominant approach**: agent 检查自身输出，发现错误后自动修正
**Papers**: P09, P10, P11, P12, P14

这一主题研究 agent 如何在执行后自我检查和修正。SuperCorrect [P10] 采用教师-学生模式：用大模型监督小模型的推理和反思过程，通过跨模型 DPO（Direct Preference Optimization）增强小模型的自纠正能力。这与 Verifier 的"强模型验证弱模型输出"思路高度一致。

然而，Li [P11] 的发现对 Verifier 的设计有重要警示：弱模型的内在自纠正率反而更高（26.8% vs 16.7%），原因是强模型犯的错误更"深"，更难自我检测。错误检测能力（10%-82% 的巨大差异）并不能预测纠正成功率。这意味着 Verifier 不能简单地依赖 worker 的自报告置信度，而需要独立的验证机制。

Perceptual Self-Reflection [P09] 提出了一个重要的方法论创新：不检查代码结构，而是检查代码执行的视觉输出。这解决了"oracle gap"——语法正确的代码可能产生物理上错误的结果。对编码任务的启示是：Verifier 不应只检查 worker 输出的格式和结构，还应验证实际执行结果（如测试是否通过、路径是否可达）。

STeP [P12] 和 MemCoder [P14] 则关注从验证反馈中学习：STeP 合成包含错误-纠正的自反思轨迹来训练 agent；MemCoder 使用结构化记忆中的验证反馈来纠正 agent 行为。这与 Verifier 的"验证结果反馈给系统以改进未来路由"的闭环设计一致。

**对 Verifier 的启示**：(1) 强模型验证弱模型的模式（教师-学生）可直接应用于 Verifier 架构；(2) 不能依赖 worker 自报告的置信度，需要独立验证；(3) "执行结果验证"比"结构检查"更可靠；(4) 验证结果应反馈到系统中以改进未来的 worker 选择和路由策略。

### Theme 3: 代码生成验证与测试（Code Generation Verification & Testing）

**Status**: active（2023-2026 年持续发展，从数学推理扩展到 API 测试）
**Dominant approach**: 用代码执行结果验证生成代码的正确性
**Papers**: P15, P16, P17, P18

这一主题研究如何验证 LLM 生成的代码。CSV [P15] 是最具启发性的工作：它让 GPT-4 Code Interpreter 用代码自我验证数学答案，验证失败时自动修正。在 MATH 数据集上，零样本准确率从 53.9% 提升到 84.3%——仅通过添加验证-修正循环。这证明了验证机制的巨大价值。

VerilogReader [P16] 让 LLM 作为代码阅读器，理解 Verilog 代码逻辑后生成测试激励。虽然针对硬件验证，但其核心思想——LLM 理解代码语义后生成针对性测试——可以迁移到编码任务的验证中。

RestTSLLM [P17] 将 TSL（Test Specification Language）与 LLM 结合，自动化 REST API 测试生成。其发现 Claude 3.5 Sonnet 在所有指标上最优，这对 Verifier 的模型选择有参考价值。

**对 Verifier 的启示**：(1) 代码执行验证是最可靠的验证手段——运行测试、检查路径是否存在、验证行号有效性；(2) LLM 可以理解代码语义后生成针对性验证；(3) 验证-修正循环的价值已被充分证明（CSV 的 30%+ 提升）。

### Theme 4: Shared Memory 安全与隐私（Shared Memory Security & Privacy）

**Status**: emerging（2025-2026 年刚开始出现针对 agent memory 的安全研究）
**Dominant approach**: 攻击 agent memory 以揭示安全/隐私风险
**Papers**: P06, P07, P13, P15

这是与 Verifier 最相关但研究最少的主题。XAMT [P07] 揭示了 shared memory 可以被隐蔽篡改的风险——攻击者可以通过双层优化在不被检测的情况下修改内存内容。这对 Verifier 的信任基础构成直接威胁：如果 worker 可以篡改 shared memory，Verifier 的验证就失去了意义。因此，"worker 提议 / verifier 确认"的两步提交模式不仅是质量保证机制，也是安全防护机制。

MRMMIA [P06] 揭示了 agent memory 的隐私风险——成员推断攻击可以确定特定数据是否曾被存储在 agent memory 中。这意味着 Verifier 的策略验证层需要检查 worker 输出是否无意中暴露了敏感数据（如 API 密钥、内部路径、个人信息）。

MACLA [P13] 研究了记忆增强 agent 的质量评估机制，其贝叶斯选择和对比精炼方法可用于 Verifier 的质量验证层——如何从多条候选事实中选择最可靠的一条。

"Too Helpful to Be Safe" [P15] 揭示了一个系统性风险：agent 为完成任务会绕过安全约束。这对 Verifier 的策略验证有直接启示——read-only 任务不应修改文件，但"过度帮助"的 worker 可能会突破这一约束。

**对 Verifier 的启示**：(1) Shared memory 必须有写入保护——只有 Verifier 能提交事实到 memory；(2) 策略验证需要检查敏感数据泄露；(3) read-only 执行约束需要强制执行，不能依赖 worker 自律；(4) 记忆质量评估机制可借鉴贝叶斯选择方法。

---

## Gap Identification Matrix

| Gap ID | Gap Description | Evidence (papers) | Gap Type | Confidence |
|--------|----------------|-------------------|----------|------------|
| G1 | **中间结果验证 vs 最终输出验证**：所有现有验证工作都针对最终输出（对话回答、代码生成、数学答案），而非多 agent 系统中的中间 worker 结果。Verifier 需要验证的是子任务的结构化输出（summary/evidence/next_steps），这与现有验证目标的粒度和形式完全不同。 | P01-P05 验证对话回答；P15-P17 验证代码/数学答案——无一验证中间结构化结果 | overlooked formulation | HIGH |
| G2 | **轻量级编码任务子结果验证器缺失**：没有专门为编码任务子结果设计的轻量级 verifier。SAFE [P01] 依赖搜索 API，DiVA [P08] 需要 agent+判别器混合——这些都太重。Verifier 需要在毫秒级完成结构验证和接地验证。 | P01, P02, P08 的验证器均需要多次 LLM 调用或外部 API | missing diagnostic | HIGH |
| G3 | **Shared memory 安全性未被研究**：XAMT [P07] 和 MRMMIA [P06] 揭示了 agent memory 的安全和隐私风险，但没有工作提出防御方案。多 agent 编码系统中，shared memory 是核心协调媒介，其安全性直接影响系统可靠性。 | P06（隐私攻击）、P07（篡改攻击）——无防御工作 | untested assumption | HIGH |
| G4 | **两步内存提交模式不存在**：没有"worker 提议 / verifier 确认"的两步提交模式。现有 agent memory 系统（MACLA [P13]、MemCoder [P14]）允许 agent 直接写入 memory，没有验证门控。这与数据库的 write-ahead log 或 Git 的 staging area 思想类似，但在 LLM agent 领域尚属空白。 | P13, P14 的 memory 系统无验证门控 | overlooked formulation | HIGH |
| G5 | **策略验证完全缺失**：LLM agent 文献中没有"策略验证"的概念——检查 read-only 任务是否修改了文件、是否暴露了敏感数据、是否绕过了安全约束。"Too Helpful to Be Safe" [P15] 揭示了问题，但没有提出验证机制。 | P15 揭示风险但无验证方案；P06 揭示隐私风险但无防护 | overlooked formulation | HIGH |
| G6 | **置信度自适应升级验证器缺失**：没有 verifier 能在置信度不足时自动升级到更强模型。SuperCorrect [P10] 使用固定的教师-学生结构，Li [P11] 发现强模型反而更难自纠正——这些发现表明需要动态的、基于置信度的验证升级策略。 | P10（固定结构）、P11（纠正悖论）——无动态升级机制 | cross-domain transfer | HIGH |
| G7 | **编码任务特化的接地验证基准缺失**：没有针对编码任务的接地验证基准——验证代码路径是否存在、行号是否有效、API 端点是否可达。现有事实性验证基准（LongFact、FGVeriBench）面向通用文本，不涵盖编码场景。 | P01, P02, P08 的基准均为通用文本 | missing diagnostic | MEDIUM |

---

## 与 Verifier 设计的映射

基于上述分析，Verifier 的设计可以借鉴以下技术路线：

| Verifier 能力层 | 借鉴来源 | 实现思路 |
|----------------|---------|---------|
| 结构验证 | 无直接来源（G2 空白） | 规则引擎：检查 worker 输出是否包含 summary、evidence、next_steps 字段，字段类型和非空性校验 |
| 接地验证 | P01 (SAFE), P08 (DiVA) | 轻量级分解：将 evidence 拆分为路径+行号对，验证路径存在（文件系统检查）、行号范围有效（读取文件行数）；不需要搜索 API |
| 策略验证 | P15 (Too Helpful), P06 (MRMMIA), P07 (XAMT) | 规则 + 学习混合：规则检查 read_only 任务的文件修改（diff 为空）、敏感数据模式匹配（API key、路径泄露）；学习处理模糊情况 |
| 质量验证 | P08 (DiVA), P13 (MACLA) | 判别器评分：训练轻量判别器评估结论与证据的一致性、下一步的可操作性；低置信度时升级到强模型 spot-check |
| 置信度升级 | P10 (SuperCorrect), P11 (Self-Correction Paradox) | 动态升级：结构/接地/策略验证失败 → 直接拒绝；质量验证置信度低 → 升级到强模型重新评估 |
| 安全门控 | P07 (XAMT), P06 (MRMMIA), P14 (MemCoder) | 两步提交：worker 输出先存为 proposed 状态，Verifier 验证通过后才变为 verified 并写入 shared memory |
| 反馈闭环 | P12 (STeP), P14 (MemCoder) | 验证结果记录到 cost ledger：哪些 worker 的输出被拒绝、拒绝原因、升级后的结果——用于改进未来的路由策略 |

---

## References

1. Wei, J., Yang, C., Song, X., Lu, Y., Hu, N., Huang, J., Tran, D., Peng, D., Liu, R., Huang, D., Du, C., & Le, Q.V. (2024). Long-form factuality in large language models. arXiv:2403.18802.
2. Wang, Y., Wang, M., Iqbal, H., Georgiev, G., Geng, J., & Nakov, P. (2024). OpenFactCheck: Building, Benchmarking Customized Fact-Checking Systems and Evaluating the Factuality of Claims and LLMs. arXiv:2405.05583.
3. Huang, H., DeLucia, A., Tiyyala, V.M., & Dredze, M. (2025). MedScore: Generalizable Factuality Evaluation of Free-Form Medical Answers by Domain-adapted Claim Decomposition and Verification. arXiv:2505.18452.
4. Zhao, J.X., Liu, J.Z.J., Hooi, B., & Ng, S.-K. (2025). How Does Response Length Affect Long-Form Factuality. arXiv:2505.23295.
5. Chen et al. (2026). MRMMIA: Membership Inference Attacks on Memory in Chat Agents. arXiv:2605.27825.
6. Sharma et al. (2025). XAMT: Bilevel Optimization for Covert Memory Tampering. arXiv:2512.15790.
7. Huang, H., Yang, M., & Arase, Y. (2026). DiVA: Fine-grained Factuality Verification with Agentic-Discriminative Verifier. arXiv:2601.03605.
8. Shende, P. & Camburn, B. (2026). Perceptual Self-Reflection in Agentic Physics Simulation Code Generation. arXiv:2602.12311.
9. Yang, L., Yu, Z., Zhang, T., Xu, M., Gonzalez, J.E., Cui, B., & Yan, S. (2024). SuperCorrect: Advancing Small LLM Reasoning with Thought Template Distillation and Self-Correction. arXiv:2410.09008.
10. Li, Y. (2025). Decomposing LLM Self-Correction: The Accuracy-Correction Paradox and Error Depth Hypothesis. arXiv:2601.00828.
11. Forouzandeh et al. (2025). MACLA: Memory-Augmented Contrastive Learning Agent. arXiv:2512.18950.
12. Chen, Y., Xu, B., Wang, X., Zhang, Y., & Mao, Z. (2025). STeP: Training LLM-Based Agents with Synthetic Self-Reflected Trajectories and Partial Masking. arXiv:2505.20023.
13. Deng et al. (2026). MemCoder: Your Code Agent Can Grow Alongside You with Structured Memory. arXiv:2603.13258.
14. Chen et al. (2026). Too Helpful to Be Safe. arXiv:2601.10758.
15. Zhou, A., Wang, K., Lu, Z., Shi, W., Luo, S., Qin, Z., Lu, S., Jia, A., Song, L., Zhan, M., & Li, H. (2023). Solving Challenging Math Word Problems Using GPT-4 Code Interpreter with Code-based Self-Verification. arXiv:2308.07921.
16. Ma, R., Yang, Y., Liu, Z., Zhang, J., Li, M., Huang, J., & Luo, G. (2024). VerilogReader: LLM-Aided Hardware Test Generation. arXiv:2406.04373.
17. Barradas, T., Paes, A., & Neves, V.O. (2025). Combining TSL and LLM to Automate REST API Testing: A Comparative Study. arXiv:2509.05540.
18. Nakov, P., Sencar, H.T., An, J., & Kwak, H. (2021). A Survey on Predicting the Factuality and the Bias of News Media. arXiv:2103.12506.
