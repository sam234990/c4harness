# Shared Memory 模块：原始研究想法

**日期**: 2026-06-24
**来源**: landscape-memory.md + memory-design.md 的 gap 分析
**想法数量**: 12

---

## 想法 1: Directed Memory Access vs. Free Similarity Retrieval for Coding Tasks

**Thesis**: 主 agent 显式指定的 directed context bundle 比 worker 自主做的 similarity retrieval 更省 token、更少噪声。

**Problem**: MemGPT、Zep/Graphiti 等系统默认使用 embedding similarity 检索 memory，但在 coding task 中，主 agent 已经知道任务的 repo、path、task type，让它指定 context 比让 worker 自己搜更精准。这个假设从未被实证验证过（G3）。

**Core mechanism**: 主 agent 根据 task metadata（repo, path, task type, dependencies）从 Track A 组装 context bundle，直接发给 worker。Baseline 是 worker 自己做 RAG retrieval。对比 token 消耗、无关 fact 注入率、下游任务准确率。

**Non-obvious reason**: "Directed access"听起来像工程优化，但它实质上是关于 memory 控制权的归属问题——是 agent 自治检索，还是 orchestrator 集中控制。这影响整个系统的信息流架构。大多数研究假设"更多检索 = 更好"，但 coding task 的结构化特性（路径、日志、diff）可能让 directed access 更优。

**Contribution type**: Empirical study（首个对比 directed vs. free retrieval 在 coding tasks 上的实证研究）

**Risk**: Medium — 主 agent 组装 context bundle 本身也消耗 token，如果 task 很模糊，directed access 可能不如 retrieval 灵活。

**Effort**: 中等（2-3 月）。需要实现两种 memory access 模式 + 在 SWE-bench 上跑实验。

**Closest work + delta**: MemGPT (P09) 用层次化 memory + 相似度检索。Delta: 我们不做检索，由 orchestrator 显式推送；面向 coding task 而非通用对话。

---

## 想法 2: Dual-Track Memory Reduces Context Pollution

**Thesis**: 将 memory 分成 Structured Facts (Track A) 和 Artifacts (Track B) 比单一 message pool 更能减少 context pollution。

**Problem**: MetaGPT/ChatDev 用单一 message pool，所有 agent 共享全部信息。当任务复杂时，不相关的对话、过时的日志、冗余的 patch 会混入 worker 上下文，导致"迷失在中间"和幻觉（G2）。"Context pollution"这个概念在 multi-agent memory 中没有被量化研究过。

**Core mechanism**: Track A 只存经过 verifier 确认的 structured facts（小而精），Track B 存大体积 artifacts（日志、patch、transcript），默认不注入。Baseline 是单一 message pool（所有信息混在一起）。对比 context pollution 指标（无关信息占比）、hallucination rate、task success rate。

**Non-obvious reason**: 双轨设计看似是工程分层，但它实际上是在测试一个认知假设：agent 的 working memory 应该像人类一样，区分"已确认知识"和"参考资料"。单轨系统把两者混在一起，等于让 agent 同时处理 signal 和 noise。

**Contribution type**: Empirical study + system design（首个量化 context pollution 在 multi-agent coding 中的影响）

**Risk**: Low-Medium — 双轨设计增加系统复杂度，如果 Track A 太小可能丢关键信息。

**Effort**: 中等（2-3 月）。需要实现双轨和单轨两种 memory 模式 + 定义 pollution metric。

**Closest work + delta**: MetaGPT (P07) 的 message pool。Delta: 我们把 memory 分成 verified facts 和 raw artifacts，不是所有信息同等对待；引入 pollution metric。

---

## 想法 3: Two-Phase Commit for Worker-Proposed Facts

**Thesis**: Worker 提出 → Verifier 确认的两步机制比直接写入或自动抽取更能提升 shared memory 中的事实可靠性。

**Problem**: 现有系统（MetaGPT, MemGPT, MACLA）让 agent 直接写入 memory，或自动抽取事实。但 worker 可能产生错误事实（hallucination、误解上下文），直接写入会污染整个 shared memory（G4）。两步确认机制从未在 multi-agent memory 中被系统研究。

**Core mechanism**: Worker 返回结果时，提取 proposed facts。Verifier（可以是另一个 LLM 调用或规则引擎）逐条检查：(1) 是否与已有 facts 矛盾？(2) 是否有 evidence 支持？(3) 是否与 task goal 相关？只有通过检查的 facts 才写入 Track A。测量 proposed → verified 的过滤率、误拒率、最终 fact 准确率。

**Non-obvious reason**: 两步确认看似增加延迟和成本，但它可能节省下游成本——因为错误 fact 一旦进入 memory，会级联影响所有后续任务。这类似于数据库的 WAL（Write-Ahead Log）思想：先验证再提交。

**Contribution type**: Mechanism design + empirical validation（首个在 multi-agent memory 中引入两步确认机制的系统研究）

**Risk**: Medium — Verifier 本身也可能出错（false reject/accept），需要校准。延迟增加可能影响吞吐。

**Effort**: 中等（2-3 月）。需要实现 verifier pipeline + 设计 evaluation protocol。

**Closest work + delta**: MACLA (P10) 用对比精炼管理 memory。Delta: 我们不是事后精炼，而是写入前验证；引入 verifier 角色作为 memory gatekeeper。

---

## 想法 4: Cost Ledger Feedback for Routing Policy Optimization

**Thesis**: 记录每次 delegation 的成本/结果，用历史数据反向优化 routing policy，比静态路由策略更优。

**Problem**: FrugalGPT/RouteLLM 做了 cost-aware routing，但都是 request-level 的静态策略。没有系统研究过"routing decision 的结果反馈到 memory，memory 反过来优化 routing"这个闭环（G5）。在 coding agent 场景中，"哪个 harness 处理哪类 task 更划算"这个知识应该被记忆和复用。

**Core mechanism**: 每次 delegation 记录：task type, chosen harness, token cost, task success/failure, escalation events。这些数据存入 Track A 作为 routing experience。Routing policy 定期从 memory 中学习，更新 cost-performance model。对比 static routing vs. memory-informed routing 的总成本和成功率。

**Non-obvious reason**: 这不只是"在线学习"——memory 中的 routing experience 是跨 session 的、可解释的。主 agent 可以直接读取"上次同类任务用 Codex 花了 5000 tokens 但失败了，用 Claude 花了 8000 但成功"，不需要重新训练路由器。

**Contribution type**: System design + empirical（首个在 coding agent routing 中引入 memory-informed policy 的研究）

**Risk**: High — 需要大量 task 才能学到有意义的 routing policy；冷启动问题。

**Effort**: 高（3-4 月）。需要跑大量 routing 实验 + 实现 policy learning。

**Closest work + delta**: FrugalGPT (P01)。Delta: 我们不只是级联，而是用 memory 记录 routing outcomes 并反馈给 policy；面向 agent harness 而非模型。

---

## 想法 5: Context Bundle Composition Ablation

**Thesis**: Context bundle 中不同组件（facts, path hints, dependency graph, prior errors）对 worker 性能的贡献不同，存在最优组合。

**Problem**: Directed access 的核心是组装 context bundle，但"bundle 里应该放什么"没有研究指导。是放更多 facts 好，还是放 dependency graph 好？prior errors 有没有帮助？这是 directed access 设计的具体化问题。

**Core mechanism**: 在 SWE-bench 上，系统性地 ablate context bundle 的各个组件（facts only, paths only, dependencies only, errors only, 全组合），测量 worker 的 task success rate 和 token consumption。

**Non-obvious reason**: 这看起来像标准 ablation study，但它实际上在探测 coding agent 的"认知负荷"——哪些信息真正帮助 agent 理解任务，哪些只是噪声。结果可能颠覆"越多越好"的直觉。

**Contribution type**: Empirical study（首个对 coding agent context bundle 组件做系统 ablation 的研究）

**Risk**: Low — 纯实验性，技术风险小。但结论可能太 task-specific，泛化性存疑。

**Effort**: 低-中（1.5-2 月）。主要是实验。

**Closest work + delta**: Context Engineering (P14) 讨论了多组件协作。Delta: 我们做系统 ablation，不是经验性描述；面向 directed memory access 场景。

---

## 想法 6: Provenance-Weighted Verification for Cross-Harness Facts

**Thesis**: 不同 harness 产生的事实可靠性不同，verifier 应该根据 fact 的来源（provenance）调整接受阈值。

**Problem**: 在跨 harness 场景中，Claude CLI 和 Qwen subagent 产生的 fact 质量可能不同。如果 verifier 对所有来源一视同仁，要么太松（接受低质量 facts），要么太严（拒绝高质量 facts）（G4 + G6 交叉）。

**Core mechanism**: 为每个 harness 维护一个 reliability score（基于历史 proposed → accepted 的比率）。Verifier 在检查 fact 时，根据来源 harness 的 reliability score 调整接受阈值。可靠性高的 harness 阈值低（更容易接受），可靠性低的阈值高。

**Non-obvious reason**: 这本质上是给每个 agent 建立"信誉系统"。但与传统的 reputation system 不同，这里的信誉直接影响 memory 写入权限——信誉低的 agent 的提案需要更多证据才能进入 shared memory。

**Contribution type**: Mechanism design（首个在 multi-agent memory 中引入 provenance-weighted verification 的研究）

**Risk**: Medium — Reliability score 的更新策略需要仔细设计，避免 cold start 和 feedback loop 问题。

**Effort**: 中等（2-3 月）。需要实现 reliability tracking + 多 harness 实验。

**Closest work + delta**: 无直接先例。最接近的是 XAMT (P17) 关于 memory tampering 的安全研究。Delta: 我们不是做攻击，而是做防御——通过 provenance weighting 提升 memory 可靠性。

---

## 想法 7: Adaptive Fact Expiry and Staleness Detection

**Thesis**: Coding task 中的事实有半衰期——过时的 facts 如果不及时标记为 stale，会误导后续任务。

**Problem**: 现有 memory 系统（MemGPT, MACLA）要么不过期，要么用简单的时间窗口。但在 coding 场景中，一个 fact（如"文件 X 的第 42 行有 bug"）在 patch 被 applied 后就过时了。如果不检测 staleness，后续任务可能基于过时 fact 做出错误决策。设计文档中提到了 fact lifecycle（proposed → verified → used → superseded/stale），但没有研究过检测策略。

**Core mechanism**: 当新 fact 写入时，检查是否与已有 facts 语义矛盾（用 embedding similarity + LLM judge）。如果矛盾，将旧 fact 标记为 superseded。同时，对长期未被引用的 facts 标记为 stale。对比 no expiry vs. time-based vs. semantic contradiction detection 的 memory 准确率。

**Non-obvious reason**: Fact expiry 看起来像 TTL 缓存，但"语义矛盾检测"实际上是在问：LLM 能否做 memory consistency checking？这与数据库的 view maintenance 问题同构，但用自然语言表达。

**Contribution type**: Mechanism design + empirical（首个在 multi-agent coding memory 中研究语义级 fact expiry 的工作）

**Risk**: Low-Medium — 语义矛盾检测本身可能出错（false positive/negative）。

**Effort**: 中等（2 月）。需要实现 contradiction detection + 设计 evaluation。

**Closest work + delta**: Zep/Graphiti 的时间感知图。Delta: 我们不只用时间，还用语义矛盾检测；面向 coding task 的 fact lifecycle。

---

## 想法 8: Memory-Aware Task Routing

**Thesis**: Routing decision 应该考虑 memory 状态——如果某个 harness 已经有相关 context，优先路由给它。

**Problem**: 现有 routing（FrugalGPT, RouteLLM, GraphPlanner）只考虑 query difficulty 和 model capability，不考虑 memory。但在连续 coding session 中，如果 Codex 刚处理过同一个文件的相关任务，它的 KV cache 或 context 中可能有残留信息，路由给它更高效（G5 扩展）。

**Core mechanism**: Routing 时，除了 task difficulty 和 harness capability，还加入 memory overlap score——"该 harness 之前处理过多少相关 facts"。对比 memory-aware routing vs. memory-oblivious routing 的总 token cost 和 success rate。

**Non-obvious reason**: 这把 memory 从"被动存储"变成了"routing signal"。Memory 不只是给 worker 提供 context，还给 router 提供决策依据。这可能是 directed access 架构最有价值的副产品。

**Contribution type**: System design + empirical（首个将 memory 状态纳入 agent routing 决策的研究）

**Risk**: High — Memory overlap 的计算可能比 task routing 本身更贵；需要大量连续 session 数据。

**Effort**: 高（3-4 月）。需要实现 memory-aware router + 跑连续 session 实验。

**Closest work + delta**: GraphPlanner (P05) 用图 memory 做路由。Delta: 我们用 task memory（facts, decisions）做路由信号，不是 workflow graph；面向 cost optimization。

---

## 想法 9: Cost-Driven Memory Retention Policy

**Thesis**: Memory 淘汰策略应该考虑 routing cost——从昂贵 harness 获取的 facts 应该保留更久，从便宜 harness 获取的可以更快淘汰。

**Problem**: 现有 memory 系统用 LRU 或时间窗口做淘汰。但在 cost-aware routing 场景中，一个 fact 的"获取成本"不同——用 Claude Opus 花了 10000 tokens 验证的 fact，和用 Qwen 花了 500 tokens 的 fact，淘汰代价不同（G5 + 设计文档 cost ledger 联动）。

**Core mechanism**: 每个 fact 记录其获取成本（token cost + harness cost）。淘汰时，按 cost-utility score 排序：utility 高 + cost 低的优先保留，utility 低 + cost 高的优先淘汰。对比 LRU vs. cost-aware retention 的下游 task success rate 和总 cost。

**Non-obvious reason**: 这把经济学引入 memory management——fact 有"沉没成本"，淘汰它等于浪费之前的投入。但也要避免"sunk cost fallacy"——过时的 fact 即使获取成本高也不该保留。

**Contribution type**: Mechanism design（首个在 agent memory 中引入 cost-aware retention 的研究）

**Risk**: Medium — Cost-utility 的定义需要仔细设计，utility 很难量化。

**Effort**: 中等（2 月）。需要实现 cost tracking + retention policy 实验。

**Closest work + delta**: 无直接先例。最接近的是 OS 的 page replacement algorithms。Delta: 我们把 cost 引入 utility function；面向 LLM agent memory。

---

## 想法 10: Cross-Harness Memory Consistency Protocol

**Thesis**: 当多个 harness 并行工作时，需要显式的一致性协议来防止 memory 冲突。

**Problem**: 设计文档的并发模型是"Single Writer, Few Readers"，但当多个 worker 并行处理相关子任务时，可能产生冲突的 facts（如 worker A 说"函数 X 返回 int"，worker B 说"函数 X 返回 str"）。如果没有一致性协议，这些冲突会同时存在于 memory 中（G6 扩展）。

**Core mechanism**: 当 verifier 收到冲突 facts 时，触发 resolution protocol：(1) 检查 evidence 强度，(2) 如果无法判断，escalate 给主 agent，(3) 记录 conflict resolution decision。对比 no resolution vs. automatic resolution vs. human-in-the-loop 的 memory 一致性。

**Non-obvious reason**: 这把分布式系统的一致性问题引入了 multi-agent memory。虽然只有"少量 writer"，但冲突的影响被放大——因为错误 fact 会级联影响所有后续任务。

**Contribution type**: Protocol design + empirical（首个在 multi-agent coding memory 中研究事实冲突解决的协议）

**Risk**: Low-Medium — 冲突率可能很低（大多数任务不相关），需要构造冲突场景。

**Effort**: 中等（2 月）。需要实现 conflict detection + resolution protocol。

**Closest work + delta**: 数据库 concurrency control。Delta: 我们处理的是自然语言 facts 而非结构化数据；面向 LLM agent memory。

---

## 想法 11: Verifier as Memory Gatekeeper — Ablation Study

**Thesis**: Verifier 的过滤能力是 shared memory 质量的关键瓶颈，不同 verifier 策略（LLM-based vs. rule-based vs. hybrid）效果差异大。

**Problem**: 想法 3 提出了两步确认机制，但 verifier 本身的实现方式未被研究。用 LLM 做 verifier 成本高但灵活，用规则做 verifier 便宜但死板。最优策略是什么？

**Core mechanism**: 对比三种 verifier：(1) LLM-based（用 GPT-4 判断 fact 是否合理），(2) Rule-based（检查是否与已有 facts 矛盾、是否有 evidence ref），(3) Hybrid（规则先过滤，LLM 再判断）。测量 precision, recall, cost, latency。

**Non-obvious reason**: Verifier 是整个 two-phase commit 的"单点瓶颈"——它太松则 memory 被污染，太严则有用 facts 被拒。这个 ablation 直接决定设计文档中 verifier 的实现选型。

**Contribution type**: Empirical study（首个对 multi-agent memory verifier 做系统 ablation 的研究）

**Risk**: Low — 纯实验性。

**Effort**: 低（1-1.5 月）。主要是实验。

**Closest work + delta**: MACLA (P10) 的对比精炼。Delta: 我们不是精炼 memory，而是在写入前过滤；系统比较不同 verifier 策略。

---

## 想法 12: Memory Compression for Context Budget Optimization

**Thesis**: 在 context window 有限时，对 context bundle 做智能压缩（保留关键 facts，丢弃低价值信息）比简单截断更有效。

**Problem**: Directed access 组装的 context bundle 可能超过 worker 的 context window。简单截断（从头或从尾丢弃）会丢失关键信息。需要一个 compression 策略，保留对当前 task 最有价值的 facts（G3 的实际约束）。

**Core mechanism**: 对比三种 compression 策略：(1) 截断（baseline），(2) LLM-based summarization，(3) Relevance scoring（给每个 fact 打分，保留 top-k）。测量压缩后 worker 的 task success rate 和 token usage。

**Non-obvious reason**: Memory compression 本质上是"有损编码"——在有限带宽（context window）内传递最多有用信息。这与 rate-distortion theory 同构，但用自然语言表达。

**Contribution type**: Empirical study（首个在 directed memory access 中研究 context bundle compression 的工作）

**Risk**: Low — 技术风险小。但 compression 本身消耗 token，需要权衡。

**Effort**: 低-中（1.5 月）。主要是实验。

**Closest work + delta**: MemGPT (P09) 的虚拟上下文管理。Delta: 我们面向 directed context bundle，不是全局 context；研究 compression 策略而非分层管理。
