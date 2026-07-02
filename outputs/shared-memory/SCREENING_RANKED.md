# Shared Memory 模块：深度评审（Top 4）

**日期**: 2026-06-24
**评审方式**: 3 位模拟审稿人 + Meta-Review
**入选想法**: 想法 3 (Two-Phase Commit), 想法 1 (Directed Access), 想法 2 (Dual-Track), 想法 9 (Cost-Driven Retention)

---

## 想法 3: Two-Phase Commit for Worker-Proposed Facts（总分 16）

### Reviewer A（系统/机制设计方向）

**Strengths**:
- 直击 multi-agent memory 的核心痛点：agent 直接写入导致的 fact 污染。这是 MetaGPT、MemGPT 等系统的已知问题，但从未被系统解决。
- 两步确认机制（proposed → verified → committed）借鉴了数据库事务的思想，有坚实的理论基础。
- 设计文档已经定义了 fact lifecycle（proposed → verified → used → superseded/stale/rejected），实现路径清晰。

**Weaknesses**:
- Verifier 本身也是 LLM，它可能犯错（false accept/reject）。论文需要系统分析 verifier 的错误率及其对 downstream 的影响。
- "验证"的标准是什么？与已有 facts 矛盾？有 evidence 支持？与 task goal 相关？这些标准需要精确定义，否则实验不可复现。
- 如果 verifier 太严格，有用 facts 被拒，memory 会变得"空"；如果太松，又回到了直接写入的问题。这个 trade-off 需要量化。

**Questions**:
1. Verifier 的成本如何？每次 fact 验证需要一次 LLM 调用吗？如果是，这个额外成本是否抵消了 memory 质量提升带来的收益？
2. 在什么 threshold 下，two-phase commit 的净收益为正？能否给出 break-even 分析？
3. 如何处理 verifier 自身的 hallucination？是否有 fallback 机制？

**Score**: 8/10 (Strong Accept)

### Reviewer B（LLM Agent / Empirical 方向）

**Strengths**:
- 实验设计清晰：对比 direct write vs. two-phase commit，度量 fact accuracy, task success rate, cost。
- 这是一个可以在 SWE-bench 上直接验证的假设，不需要新的 benchmark。
- 结果具有直接的工程价值——如果 two-phase commit 有效，所有 multi-agent memory 系统都可以采用。

**Weaknesses**:
- 实验的 baseline 需要仔细选择。"Direct write"是最简单的 baseline，但可能不公平——现实中的系统（如 MACLA）有事后精炼机制。应该加入"MACLA-style post-hoc refinement"作为更强的 baseline。
- Fact accuracy 的评估标准不明确。如何判断一个 fact 是"正确的"？需要 human annotation 或者 automated evaluation metric。
- 论文的 novelty 可能被质疑——two-phase commit 是数据库的老概念，只是换了个场景。

**Questions**:
1. 与 MACLA 的对比精炼相比，two-phase commit 的优势在哪？是更低的延迟？更高的准确率？
2. Fact accuracy 的 inter-annotator agreement 如何保证？
3. 如果 verifier 用规则而非 LLM，效果如何？（这与想法 11 相关）

**Score**: 7/10 (Accept)

### Reviewer C（理论/新颖性方向）

**Strengths**:
- 核心假设清晰且可证伪："two-phase commit 比 direct write 产生更可靠的 shared memory"。
- 与数据库 WAL 的类比有深度——不是简单的工程借鉴，而是揭示了 agent memory 和数据库事务的本质联系。
- 这是整个设计文档中最具"研究味道"的点。

**Weaknesses**:
- 论文可能被批评为"把数据库概念搬到 LLM"。需要证明这不是 trivial transfer，而是有非平凡的 insight。
- "Fact" 的定义在 coding task 中需要精确化。一个 diff 是 fact 吗？一个函数签名是 fact 吗？一个 error message 是 fact 吗？Fact 的粒度直接影响实验设计。
- 缺乏理论分析。Two-phase commit 的收益可以被形式化吗？比如，用信息论或决策论的框架？

**Questions**:
1. 能否给出 two-phase commit 收益的理论 bound？比如，在什么条件下，验证后的 memory 一定优于未验证的？
2. Fact 的粒度如何确定？一个 patch 中有多少 facts？
3. 这个机制是否只在 coding task 上有效？其他 domain（如问答、规划）呢？

**Score**: 7/10 (Accept)

### Meta-Review: 想法 3

**综合评价**: 三位审稿人一致认为这是设计文档中最核心的创新点。主要顾虑集中在：(1) verifier 本身的可靠性和成本，(2) 与 MACLA 等事后精炼方法的区别，(3) 是否只是 trivial concept transfer。

**建议处理**:
- 必须加入 verifier cost analysis（Break-even point: 在什么 fact error rate 下，two-phase commit 的净收益为正？）
- 必须与 MACLA 做 head-to-head 对比
- 需要一个理论框架来论证 two-phase commit 的收益，不能只靠实验
- Fact 的定义和粒度需要在论文中精确定义

**最终排名**: #1 — 最强候选，直接验证设计核心。

---

## 想法 1: Directed Memory Access vs. Free Similarity Retrieval（总分 15）

### Reviewer A

**Strengths**:
- 直接挑战了 MemGPT 等系统的隐含假设（free retrieval 更好）。
- 实验设计简洁：directed vs. free，度量 token cost 和 task success。
- 如果 directed access 被证明更优，对整个 agent memory 领域有范式影响。

**Weaknesses**:
- "Directed access"的质量取决于主 agent 的 task understanding。如果主 agent 本身能力弱（比如用便宜模型），directed access 可能比 retrieval 更差。这个 condition 需要被研究。
- Baseline 的 retrieval 质量很重要。如果用很差的 embedding model，retrieval baseline 太弱，结论不公平。
- 论文需要定义"无关 fact 注入率"的 metric。如何判断一个 fact 是否"相关"？

**Questions**:
1. 主 agent 组装 context bundle 的 token cost 是否计入总成本？
2. 如果 task 很模糊（主 agent 不知道需要什么信息），directed access 是否还有效？
3. 是否考虑 hybrid 方案：directed + limited retrieval？

**Score**: 7/10 (Accept)

### Reviewer B

**Strengths**:
- 实验可行性高：SWE-bench 上可以做。
- 结果有直接工程价值——决定 memory 系统应该用 directed 还是 retrieval。
- Token 节省的量化对 cost-aware routing 项目非常相关。

**Weaknesses**:
- 新颖性有限——"显式指定比自动检索更精准"在很多领域是常识。需要证明在 coding agent memory 中，这个常识成立且收益显著。
- 实验的 external validity 需要讨论——在不同 coding benchmark 上结果是否一致？
- Directed access 需要主 agent 有足够的 task understanding。如果主 agent 本身用的是便宜模型（cost-aware routing 的场景），它的理解能力可能不够。

**Questions**:
1. 在 cost-aware routing 场景下，主 agent 用什么模型？如果用便宜模型，directed access 的质量如何保证？
2. 是否考虑 task complexity 的调节效应？简单 task 可能 directed 足够，复杂 task 可能需要 retrieval。
3. 混合方案（directed + selective retrieval）的效果如何？

**Score**: 6/10 (Weak Accept)

### Reviewer C

**Strengths**:
- 核心假设清晰可证伪。
- 如果结论是"directed 在 coding task 上更优"，这将改变 agent memory 的设计方向。
- 与设计文档的 directed access 原则直接对应。

**Weaknesses**:
- 实验设计需要非常小心。"Directed" 和 "retrieval" 不是互斥的——现实中可能是 directed + retrieval 的混合。
- 如果结论是"directed 更好"，需要证明这是因为 coding task 的结构化特性，而不是因为 retrieval baseline 太差。
- 缺乏理论分析——为什么 directed 更好？是因为 coding task 的信息结构？还是因为主 agent 的 task understanding？

**Questions**:
1. 能否给出 directed access 优于 retrieval 的充分条件？
2. 是否只在 coding task 上做实验？如果在其他 domain（如问答）上 directed 更差，说明什么？
3. 主 agent 的 context window 限制是否影响 directed access 的质量？

**Score**: 6/10 (Weak Accept)

### Meta-Review: 想法 1

**综合评价**: 实验清晰，工程价值高，但新颖性被质疑。主要风险是结论可能太 trivial（"指定比自动检索更精准"是常识）。

**建议处理**:
- 需要理论框架来解释"为什么 directed 更好"，不能只靠实验
- 必须考虑 hybrid 方案（directed + selective retrieval）作为更强的 baseline
- 需要在不同 task complexity 下做分层分析
- 需要讨论 cost-aware routing 场景下主 agent 模型能力的约束

**最终排名**: #2 — 价值清晰，但需要增强新颖性论证。

---

## 想法 2: Dual-Track Memory Reduces Context Pollution（总分 15）

### Reviewer A

**Strengths**:
- Context pollution 是 multi-agent memory 的真实问题，但从未被量化。
- 双轨设计（Track A: facts, Track B: artifacts）有清晰的信息论解释：分离 signal 和 noise。
- 实验设计直接：single-track vs. dual-track，度量 pollution metric 和 task success。

**Weaknesses**:
- "Context pollution"需要精确的 metric 定义。是无关 token 占比？是 hallucination rate？是 task confusion？不同 metric 可能给出不同结论。
- 双轨设计增加了系统复杂度。如果 Track A 太小，可能丢失关键信息；如果太大，又接近 single-track。这个 trade-off 需要量化。
- Baseline 的 single-track 需要仔细设计——是"所有信息混在一起"还是"按时间截断"？

**Questions**:
1. Context pollution 的 metric 如何定义和计算？
2. Track A 和 Track B 的最优大小比例是多少？
3. 是否考虑过"1.5-track"方案：single track + noise filter？

**Score**: 7/10 (Accept)

### Reviewer B

**Strengths**:
- 与设计文档的双轨架构直接对应。
- 实验可行性高。
- 结果对所有 multi-agent memory 系统有参考价值。

**Weaknesses**:
- 可能被审稿人质疑为"工程分层"而非"研究贡献"。需要证明双轨不只是"分开存"，而是有认知或信息论上的道理。
- MetaGPT 的 message pool 已经做了某种程度的分层（PRD vs. code vs. test）。双轨的增量贡献需要明确。
- Context pollution 的量化本身可能就是一篇论文的贡献。

**Questions**:
1. 与 MetaGPT 的结构化文档相比，双轨的增量贡献是什么？
2. 如果 single-track 也做 noise filtering（比如只保留 verified facts），双轨还有优势吗？
3. 在什么条件下双轨设计优于 single-track + filtering？

**Score**: 6/10 (Weak Accept)

### Reviewer C

**Strengths**:
- 与人类认知的"工作记忆 vs. 参考资料"区分有类比深度。
- 如果能形式化"context pollution"并给出理论 bound，这将是一个很强的贡献。
- 双轨设计是 directed access 的基础设施——没有双轨，directed access 的"directed"就没有意义。

**Weaknesses**:
- 论文需要证明双轨的收益不是来自于"更少的信息"（即 Track A 比 single-track 小），而是来自于"更纯的信息"。
- 这可能需要一个 ablation study：single-track (small) vs. single-track (large) vs. dual-track。
- 缺乏理论分析。

**Questions**:
1. 双轨的收益是否可以被形式化为 information gain？
2. 如果 Track A 和 single-track 的大小相同，双轨还有优势吗？
3. 是否考虑过把 context pollution 定义为"无关 token 的 entropy"？

**Score**: 7/10 (Accept)

### Meta-Review: 想法 2

**综合评价**: Context pollution 是真实问题，双轨设计有直觉吸引力。主要风险是被质疑为"工程分层"。

**建议处理**:
- 必须精确定义 context pollution metric
- 需要 ablation study: single-track (small) vs. single-track (large) vs. dual-track，证明收益来自"纯度"而非"大小"
- 需要信息论或认知科学的理论框架
- 需要与 MetaGPT 的结构化文档做对比

**最终排名**: #3 — 有价值但需要更强的理论支撑。

---

## 想法 9: Cost-Driven Memory Retention Policy（总分 14）

### Reviewer A

**Strengths**:
- 把经济学引入 memory management，有跨学科吸引力。
- 与设计文档的 cost ledger 直接关联。
- 实现简单：给每个 fact 记录获取成本，淘汰时按 cost-utility 排序。

**Weaknesses**:
- "Fact 的获取成本"如何计算？是 token cost？是 harness 的 API cost？还是包含主 agent 的 coordination cost？
- "Utility"的定义更难。一个 fact 的 utility 如何量化？是被引用次数？是对下游 task success 的贡献？
- 可能过度复杂化了一个简单问题——如果 fact 过时了，不管获取成本多高都该淘汰。

**Questions**:
1. Cost-utility function 的具体形式是什么？
2. 与简单的 LRU + staleness detection 相比，cost-aware retention 的边际收益有多大？
3. 是否考虑 sunk cost fallacy——高成本的 fact 可能更不应该被保留（因为获取它本身就说明任务困难）？

**Score**: 6/10 (Weak Accept)

### Reviewer B

**Strengths**:
- Novelty 高：现有 memory 系统没有考虑 fact 的获取成本。
- 与 cost-aware routing 项目高度契合。
- 可以与想法 7（fact expiry）结合，形成更完整的 retention framework。

**Weaknesses**:
- 实验设计有挑战：需要构造不同 cost 结构的 task 流，才能看出 cost-aware vs. LRU 的差异。
- 如果大部分 fact 的获取成本差不多（同一 harness 产生的），cost-aware retention 退化为 LRU。
- 结论可能太 task-specific。

**Questions**:
1. 在什么条件下 cost-aware retention 显著优于 LRU？
2. 如何处理来自同一 harness 的 facts（成本相同）？
3. 是否考虑 fact 的"沉没成本"问题？

**Score**: 5/10 (Borderline Accept)

### Reviewer C

**Strengths**:
- 与 OS 的 page replacement 有深刻的类比，有理论基础可挖。
- 如果能给出 cost-aware retention 的最优性条件，这将是一个 nice 的理论贡献。
- 与 directed access 形成互补：directed 解决"读什么"，cost-aware 解决"留什么"。

**Weaknesses**:
- Utility 的量化是核心难题。如果 utility 无法准确度量，整个框架就是空中楼阁。
- 可能被批评为"过度工程化"——简单的 staleness detection 可能就够了。
- 需要大量 routing 数据才能验证。

**Questions**:
1. Utility 的定义是否可以被形式化？
2. 与 Belady's optimal algorithm（需要未来知识）相比，cost-aware retention 的 competitive ratio 是多少？
3. 是否考虑 online learning 来更新 cost-utility model？

**Score**: 6/10 (Weak Accept)

### Meta-Review: 想法 9

**综合评价**: 有创意，与 cost-aware routing 高度契合，但 utility 量化是核心难题。主要风险是过度复杂化。

**建议处理**:
- 需要给出 cost-utility function 的具体形式
- 需要与 LRU + staleness detection 做 head-to-head 对比
- 需要讨论 sunk cost fallacy 的问题
- 可以与想法 7 结合，形成更完整的 retention framework

**最终排名**: #4 — 有创意但实现难度高，建议作为想法 3 的扩展而非独立论文。

---

## 最终排名

| 排名 | 想法 | 分数 | 定位 |
|:----:|------|:----:|------|
| 1 | 想法 3: Two-Phase Commit | 16 | **主论文** — 验证设计核心 |
| 2 | 想法 1: Directed Access | 15 | **第二论文** — 访问模式对比 |
| 3 | 想法 2: Dual-Track | 15 | **与想法 1 合并或作为 ablation** |
| 4 | 想法 9: Cost-Driven Retention | 14 | **扩展工作** — 作为想法 3 的后续 |

**战略性建议**:
- **想法 3 是最优先的**：它直接测试设计文档最核心的创新（two-phase commit），如果被证明有效，整个架构就有论文基础。
- **想法 1 和 2 可以合并**：它们分别测试 directed access 和 dual-track，可以作为同一论文的两个 experiment。
- **想法 9 是长期方向**：需要大量 routing 数据，适合在想法 3 验证后再做。
