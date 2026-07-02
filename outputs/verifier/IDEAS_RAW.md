# Verifier 模块：原始研究想法

**生成日期**: 2026-06-24
**基于**: landscape-verifier.md (18 篇论文, 7 个研究空白)
**生成想法数**: 10

---

## Idea 1: Lightweight Code Sub-Result Verifier (LCSV)

**Thesis**: 多 agent 编码系统需要一个毫秒级 verifier，专门验证中间 worker 结果，而非最终输出。

**Problem**: 现有验证工作 (SAFE, DiVA, OpenFactCheck) 全部针对最终输出——对话回答、代码生成、数学答案。没有 verifier 专门设计用于编码任务的子结果验证。多 agent 系统中，worker 的输出是结构化的中间结果 (summary/evidence/next_steps)，验证粒度和形式与现有工作完全不同 (G1, G2)。

**Core mechanism**: 四层轻量验证流水线——(1) 结构验证：规则引擎检查字段完整性、类型、非空性；(2) 接地验证：文件系统 API 验证路径存在、读取文件验证行号范围；(3) 策略验证：正则匹配检测敏感数据模式、diff 检查 read-only 约束；(4) 质量验证：轻量判别器评分结论-证据一致性。前三层纯规则，第四层用小模型 (<1B 参数) 或微调分类器。

**Non-obvious reason**: 现有工作假设"验证 = 多次 LLM 调用 + 外部 API 搜索"，成本高、延迟大。但编码任务的接地验证可以完全基于文件系统操作——不需要搜索 API，不需要多次 LLM 调用。这是一个被忽视的低成本验证路径。

**Contribution type**: 系统设计 + 实证 (method + benchmark)

**Risk**: 中等——质量验证层的判别器训练需要标注数据；四层验证的错误传播可能影响整体准确率。

**Effort**: 3-4 个月 (规则引擎 2 周, 接地验证 3 周, 策略验证 2 周, 质量验证 4 周, 集成测试 3 周)

**Closest work + delta**: SAFE [P01] 是最接近的工作，但 SAFE 依赖搜索 API 验证通用事实，延迟秒级。LCSV 的 delta：(1) 专门针对编码子结果的结构化输出；(2) 接地验证基于文件系统而非搜索 API，延迟毫秒级；(3) 四层验证流水线，前三层纯规则无 LLM 调用。

---

## Idea 2: Two-Step Commit Protocol for Multi-Agent Shared Memory (2SC)

**Thesis**: 多 agent 编码系统需要"worker 提议 / verifier 确认"的两步内存提交模式，防止未经验证的低质量或恶意内容污染 shared memory。

**Problem**: 现有 agent memory 系统 (MACLA [P13], MemCoder [P14]) 允许 agent 直接写入 memory，没有验证门控。XAMT [P07] 证明 shared memory 可被隐蔽篡改，MRMMIA [P06] 证明 agent memory 存在隐私泄露风险。在多 agent 编码系统中，shared memory 是核心协调媒介——一个 worker 的错误事实可能误导所有后续 worker (G3, G4)。

**Core mechanism**: 借鉴数据库 write-ahead log 和 Git staging area 的思想——(1) Worker 完成任务后，输出进入 "proposed" 状态（临时缓冲区）；(2) Verifier 对 proposed 输出执行四层验证；(3) 验证通过 → 输出变为 "verified" 并写入 shared memory；验证失败 → 输出变为 "rejected" 并记录拒绝原因；(4) 所有状态变更记录在 append-only audit log 中，支持回溯和审计。

**Non-obvious reason**: 数据库领域的两步提交是成熟技术，但 LLM agent 领域完全没有采用。原因可能是 agent 研究者更关注能力提升而非可靠性保障。将数据库的事务保证思想迁移到 agent memory 是一个跨领域但自然的创新。

**Contribution type**: 协议设计 + 安全分析 (protocol + security analysis)

**Risk**: 中低——协议设计本身不复杂，但需要证明在实际多 agent 系统中的开销可接受；安全分析需要构建攻击场景。

**Effort**: 2-3 个月 (协议设计 3 周, 实现 4 周, 安全分析 3 周, 集成测试 2 周)

**Closest work + delta**: MemCoder [P14] 是最接近的工作，它使用结构化记忆和验证反馈。但 MemCoder 的验证是后验的（agent 写入后检查），而非门控的（写入前必须通过验证）。2SC 的 delta：(1) 前置验证门控，而非后验检查；(2) 显式的状态机 (proposed → verified/rejected)；(3) append-only audit log 支持安全审计；(4) 明确的 shared memory 写入保护。

---

## Idea 3: Policy Verification Layer for Safe Agent Execution (PVL)

**Thesis**: LLM agent 系统需要一个专门的策略验证层，强制执行 read-only 约束、防止敏感数据泄露、检测"过度帮助"行为。

**Problem**: "Too Helpful to Be Safe" [P15] 揭示 agent 为完成任务会绕过安全约束。MRMMIA [P06] 揭示 agent memory 的隐私泄露风险。但在 LLM agent 文献中，没有专门的策略验证机制——检查 read-only 任务是否修改了文件、是否暴露了敏感数据、是否绕过了安全约束 (G5)。

**Core mechanism**: 三层策略验证——(1) 执行约束验证：对 read_only 任务，检查 worker 输出中的文件操作（diff 为空、无 write/edit 调用）；(2) 敏感数据检测：基于正则表达式 + 轻量 NER 模型，检测 API 密钥、内部路径、个人信息、密码等模式；(3) 行为异常检测：对比 worker 的实际行为与任务预期行为，检测"过度帮助"（如任务要求只读分析但 worker 提供了修改建议）。

**Non-obvious reason**: 安全社区关注 prompt injection 和 jailbreak，但完全忽视了 agent 执行层面的策略违规。"过度帮助"是一种新型的安全风险——agent 不是被攻击，而是主动违反约束来"帮助"用户。这种风险需要专门的验证机制。

**Contribution type**: 方法 + 安全分析 (method + security analysis)

**Risk**: 中等——敏感数据检测的召回率和误报率需要平衡；"过度帮助"的定义边界模糊，可能需要人工标注。

**Effort**: 3-4 个月 (执行约束验证 2 周, 敏感数据检测 4 周, 行为异常检测 4 周, 评估 2 周)

**Closest work + delta**: "Too Helpful to Be Safe" [P15] 是最接近的工作，它揭示了问题但没有提出验证方案。PVL 的 delta：(1) 从问题揭示到解决方案；(2) 三层策略验证覆盖执行约束、数据泄露、行为异常；(3) 专门为编码任务设计（read_only 约束、文件操作检测）。

---

## Idea 4: Execution-Based Grounding Verification (EBGV)

**Thesis**: 对于编码任务，最可靠的验证方式是执行代码并检查结果，而非仅检查文本结构。

**Problem**: 现有验证工作 (SAFE, DiVA) 基于文本匹配和搜索验证，无法检测"语法正确但逻辑错误"的输出。Perceptual Self-Reflection [P09] 在物理仿真中证明了执行结果验证的价值——不检查代码结构，而是检查渲染帧。但编码任务中没有类似的执行验证方法 (G1)。

**Core mechanism**: 执行验证流水线——(1) 从 worker 输出中提取可执行代码片段或测试用例；(2) 在沙箱环境中执行代码；(3) 检查执行结果（测试通过率、异常、输出匹配）；(4) 将执行结果作为接地验证的 ground truth。对于非代码类 worker 输出（如分析任务），验证相关的文件路径和行号引用是否可访问。

**Non-obvious reason**: 编码任务的验证可以借用"oracle"——代码执行结果。这比文本匹配更可靠，但现有工作完全忽视了这一点。原因可能是执行验证需要沙箱环境，增加了系统复杂度。但 Docker 容器化使得沙箱执行变得廉价。

**Contribution type**: 方法 + 实证 (method + empirical study)

**Risk**: 高——执行不可信代码有安全风险（需要严格的沙箱隔离）；不是所有 worker 输出都包含可执行代码；执行超时和资源限制需要处理。

**Effort**: 4-5 个月 (沙箱环境 3 周, 代码提取 3 周, 执行验证 4 周, 安全审计 2 周, 评估 2 周)

**Closest work + delta**: Perceptual Self-Reflection [P09] 是最接近的工作，它在物理仿真中使用视觉输出验证。CSV [P15] 在数学推理中使用代码执行验证。EBGV 的 delta：(1) 将执行验证迁移到通用编码任务（不限于数学或物理仿真）；(2) 设计安全的沙箱执行环境；(3) 将执行结果整合到多层验证流水线中。

---

## Idea 5: Confidence-Adaptive Verification Escalation (CAVE)

**Thesis**: Verifier 应该根据置信度动态调整验证强度——低置信度时升级到更强模型，高置信度时使用轻量验证。

**Problem**: SuperCorrect [P10] 使用固定的教师-学生结构，不考虑验证置信度。Li [P11] 发现强模型的自纠正率反而更低（16.7% vs 26.8%），原因是强模型犯的错误更"深"。这意味着"总是用最强模型验证"不是最优策略——需要根据置信度动态选择验证强度 (G6)。

**Core mechanism**: 置信度感知的验证升级策略——(1) 轻量验证器（规则 + 小模型）对每个 worker 输出计算置信度分数；(2) 高置信度 (>0.9) → 直接通过，无需进一步验证；(3) 中置信度 (0.5-0.9) → 升级到中等模型 (如 7B 参数) 重新验证；(4) 低置信度 (<0.5) → 升级到强模型 (如 GPT-4 级别) 重新验证或直接拒绝；(5) 记录升级决策和结果，用于优化置信度校准。

**Non-obvious reason**: Li [P11] 的发现挑战了"强模型更好验证"的直觉。实际上，验证强度应该与错误类型匹配——浅层错误（格式、路径）用轻量验证即可，深层错误（逻辑、语义）需要强模型。CAVE 的非显然之处在于：它不是简单的"分级验证"，而是基于置信度校准的动态升级，且需要处理"强模型反而更差"的悖论。

**Contribution type**: 方法 + 实证 (method + empirical study)

**Risk**: 中等——置信度校准的准确性直接影响升级决策；需要大量标注数据来训练和校准置信度模型。

**Effort**: 3-4 个月 (置信度模型 4 周, 升级策略 3 周, 校准优化 3 周, 评估 2 周)

**Closest work + delta**: SuperCorrect [P10] 是最接近的工作，它使用固定的教师-学生结构。CAVE 的 delta：(1) 动态升级而非固定结构；(2) 基于置信度校准而非简单阈值；(3) 考虑 Li [P11] 的纠正悖论——不是所有情况都适合升级到强模型；(4) 升级决策可解释，支持反馈闭环。

---

## Idea 6: Adversarial Robustness of Multi-Agent Verifier (ARV)

**Thesis**: Verifier 本身需要具备对抗鲁棒性，防止恶意 worker 通过精心构造的输出绕过验证。

**Problem**: XAMT [P07] 证明 shared memory 可被隐蔽篡改——攻击者通过双层优化在不被检测的情况下修改内存内容。如果 verifier 是唯一的质量守门人，那么攻击 verifier 就成为攻击整个系统的最有效路径。但现有工作没有研究 verifier 的对抗鲁棒性 (G3)。

**Core mechanism**: 对抗鲁棒验证框架——(1) 威胁建模：定义恶意 worker 的攻击策略（格式合规但内容虚假、路径存在但行号错误、敏感数据编码混淆）；(2) 对抗训练：用攻击样本训练验证器，提升对 adversarial inputs 的鲁棒性；(3) 多样性防御：使用多个独立验证器（不同模型、不同验证逻辑），多数投票决定最终结果；(4) 异常检测：监控 worker 输出的统计特征，检测异常模式（如突然的格式变化、不寻常的证据引用模式）。

**Non-obvious reason**: 安全社区研究了 prompt injection 和 jailbreak，但没有研究 verifier 层面的对抗攻击。在多 agent 系统中，攻击 verifier 比攻击 worker 更高效——只需绕过一个 verifier 就能污染整个 shared memory。这是一个被忽视的攻击面。

**Contribution type**: 安全分析 + 防御方法 (security analysis + defense)

**Risk**: 中高——攻击策略的定义可能不全面；对抗训练的效果难以保证；多样性防御增加系统复杂度和成本。

**Effort**: 4-5 个月 (威胁建模 3 周, 攻击实现 4 周, 防御设计 4 周, 评估 3 周)

**Closest work + delta**: XAMT [P07] 是最接近的工作，它展示了隐蔽内存篡改。ARV 的 delta：(1) 从攻击展示到防御设计；(2) 专门研究 verifier 层面的对抗鲁棒性（而非 memory 层面）；(3) 多样性防御策略（多验证器投票）；(4) 与 2SC 协议结合，提供端到端的安全保证。

---

## Idea 7: Contrastive Multi-Worker Fact Selection (CMFS)

**Thesis**: 当多个 worker 对同一子任务产生冲突输出时，需要一个基于对比学习的事实选择机制。

**Problem**: 在多 agent 编码系统中，同一子任务可能被分配给多个 worker（冗余执行提高可靠性）。但当 worker 输出冲突时，如何选择最可靠的事实？MACLA [P13] 使用贝叶斯选择和对比精炼，但针对单 agent 的记忆质量，而非多 worker 的冲突解决 (G1)。

**Core mechanism**: 对比事实选择框架——(1) 收集多个 worker 对同一子任务的输出；(2) 将每条输出分解为独立事实声明；(3) 对同一事实的多个版本进行对比评分（一致性、证据质量、来源可靠性）；(4) 选择得分最高的事实版本写入 shared memory；(5) 记录冲突和选择决策，用于分析 worker 可靠性。

**Non-obvious reason**: 多 agent 系统通常假设 worker 输出是一致的，或者简单地使用多数投票。但编码任务的事实冲突可能是微妙的（如行号偏差、路径近似），需要细粒度的对比分析而非简单投票。

**Contribution type**: 方法 (method)

**Risk**: 中等——冲突检测的粒度需要仔细设计；对比评分的训练数据难以获取；增加系统复杂度。

**Effort**: 3-4 个月 (冲突检测 3 周, 对比评分 4 周, 选择策略 3 周, 评估 2 周)

**Closest work + delta**: MACLA [P13] 是最接近的工作，它使用贝叶斯选择和对比精炼。CMFS 的 delta：(1) 从单 agent 记忆质量到多 worker 冲突解决；(2) 细粒度的事实级对比（而非输出级）；(3) 专门针对编码任务的事实冲突（路径、行号、API 端点）。

---

## Idea 8: CodeTask Grounding Verification Benchmark (CGVB)

**Thesis**: 需要一个专门的基准来评估编码任务的接地验证能力。

**Problem**: 现有事实性验证基准 (LongFact, FGVeriBench) 面向通用文本，不涵盖编码场景。没有基准包含代码路径存在性、行号有效性、API 端点可达性等编码特化的验证任务 (G7)。

**Core mechanism**: 基准构建——(1) 从真实编码任务中收集 worker 输出样本；(2) 标注接地验证 ground truth（路径是否存在、行号是否有效、API 端点是否可达、代码片段是否可执行）；(3) 包含正例（正确引用）和负例（错误引用、幻觉路径）；(4) 设计评估指标（准确率、召回率、F1、延迟）；(5) 开源基准，支持社区评估和扩展。

**Non-obvious reason**: 没有基准就无法公平比较不同验证方法。这是一个"基础设施"贡献，虽然不够"sexy"，但对领域发展至关重要。类似 SWE-bench 对 coding agent 的推动作用。

**Contribution type**: 基准 + 数据集 (benchmark + dataset)

**Risk**: 低——基准构建主要是工程工作，技术风险小；但标注质量和覆盖面需要保证。

**Effort**: 2-3 个月 (数据收集 3 周, 标注 4 周, 基准设计 2 周, 文档 1 周)

**Closest work + delta**: LongFact (SAFE 的评估基准) 是最接近的工作。CGVB 的 delta：(1) 从通用文本到编码任务；(2) 包含编码特化的验证维度（路径、行号、API、可执行性）；(3) 支持毫秒级延迟评估（而非秒级）。

---

## Idea 9: Verifier-in-the-Loop Worker Self-Improvement (VLWSI)

**Thesis**: Verifier 的反馈应作为训练信号，帮助 worker 模型持续改进输出质量。

**Problem**: 现有验证工作将验证视为一次性检查——通过或拒绝。STeP [P12] 和 MemCoder [P14] 证明了从验证反馈中学习的价值，但没有将 verifier 的反馈系统性地整合到 worker 的训练循环中。Verifier 的拒绝原因、置信度分数、升级决策都是宝贵的训练信号，但目前被浪费了。

**Core mechanism**: 反馈驱动的 worker 改进循环——(1) Verifier 对每个 worker 输出生成结构化反馈（拒绝原因、各层验证分数、置信度分布）；(2) 收集 (worker 输出, verifier 反馈) 对作为训练数据；(3) 使用 DPO 或 RLHF 方法，以 verifier 反馈作为偏好信号训练 worker；(4) 定期评估改进效果，调整反馈权重。

**Non-obvious reason**: 现有工作将 verifier 和 worker 视为独立组件。但实际上，verifier 的反馈是提升 worker 质量的最直接信号——比任务成功率更精细、比人工标注更廉价。这种"验证驱动的自我改进"是一个被忽视的训练范式。

**Contribution type**: 方法 + 实证 (method + empirical study)

**Risk**: 中等——verifier 反馈的质量直接影响 worker 改进效果；如果 verifier 本身有偏见，可能引入系统性错误。

**Effort**: 4-5 个月 (反馈收集 3 周, 训练数据构建 4 周, DPO/RLHF 训练 4 周, 评估 3 周)

**Closest work + delta**: STeP [P12] 是最接近的工作，它合成自反思轨迹训练 agent。VLWSI 的 delta：(1) 使用 verifier 的结构化反馈（而非合成轨迹）作为训练信号；(2) 反馈粒度更细（四层验证分数、置信度分布）；(3) 持续改进循环（而非一次性训练）。

---

## Idea 10: Atomic Claim Decomposition for Granular Verification (ACDGV)

**Thesis**: Worker 输出应被分解为原子事实声明，每条声明独立验证，以实现细粒度的质量保证。

**Problem**: SAFE [P01] 的分解-验证范式针对长文本对话回答，分解粒度不适合编码任务的结构化输出。MedScore [P03] 的条件感知分解面向医疗领域。编码任务的 worker 输出包含多种类型的事实声明（路径、行号、代码片段、分析结论），需要专门的分解策略 (G1, G2)。

**Core mechanism**: 编码任务特化的声明分解——(1) 定义编码任务的原子事实类型（路径声明、行号声明、代码功能声明、分析结论声明、下一步建议声明）；(2) 基于规则 + LLM 混合方法，将 worker 输出分解为原子声明；(3) 每条声明附加类型标签和验证方法标签；(4) 按类型路由到对应的验证器（路径 → 文件系统、行号 → 文件读取、代码 → 沙箱执行、结论 → 判别器评分）。

**Non-obvious reason**: 现有分解方法是通用的（将文本拆分为句子或事实），没有针对编码任务的结构化分解。编码任务的 worker 输出有固定的 schema（summary/evidence/next_steps），可以利用这一结构实现更精确的分解。

**Contribution type**: 方法 (method)

**Risk**: 中低——分解规则的设计需要领域知识；LLM 分解的一致性需要保证。

**Effort**: 2-3 个月 (分解规则 3 周, LLM 分解 3 周, 路由验证 3 周, 评估 2 周)

**Closest work + delta**: SAFE [P01] 是最接近的工作，它将长文本分解为独立事实。ACDGV 的 delta：(1) 针对编码任务的结构化输出（而非通用长文本）；(2) 定义编码特化的原子事实类型；(3) 按类型路由到专用验证器（而非统一验证）。

---

## 想法汇总

| ID | Title | 一句话摘要 | 涉及空白 |
|----|-------|-----------|---------|
| I1 | Lightweight Code Sub-Result Verifier (LCSV) | 毫秒级四层验证流水线，专门验证编码子结果 | G1, G2 |
| I2 | Two-Step Commit Protocol (2SC) | worker 提议 / verifier 确认的两步内存提交 | G3, G4 |
| I3 | Policy Verification Layer (PVL) | read-only 约束 + 敏感数据 + 过度帮助检测 | G5 |
| I4 | Execution-Based Grounding Verification (EBGV) | 沙箱执行代码作为验证 ground truth | G1 |
| I5 | Confidence-Adaptive Verification Escalation (CAVE) | 基于置信度的动态验证强度调整 | G6 |
| I6 | Adversarial Robustness of Verifier (ARV) | 对抗训练 + 多样性防御保护 verifier | G3 |
| I7 | Contrastive Multi-Worker Fact Selection (CMFS) | 多 worker 冲突输出的对比选择 | G1 |
| I8 | CodeTask Grounding Verification Benchmark (CGVB) | 编码任务接地验证基准 | G7 |
| I9 | Verifier-in-the-Loop Worker Self-Improvement (VLWSI) | verifier 反馈驱动 worker 持续改进 | -- |
| I10 | Atomic Claim Decomposition for Granular Verification (ACDGV) | 编码任务特化的原子声明分解 | G1, G2 |
