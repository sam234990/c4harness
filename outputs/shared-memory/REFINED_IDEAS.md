# Shared Memory 模块：精炼后的 Top 2 想法

**日期**: 2026-06-24
**精炼对象**: 想法 3 (Two-Phase Commit) + 想法 1 (Directed Access)
**精炼内容**: Problem anchor, Core contribution, Experimental design, Expected results, Positioning

---

## Refined Idea 1: Two-Phase Commit for Worker-Proposed Facts in Multi-Agent Coding Memory

### 1. Problem Anchor

**一句话定义问题**: Multi-agent coding 系统中的 shared memory 允许 agent 直接写入事实，但 worker 产生的 facts 中有多少是错误的？这些错误 facts 如何级联影响后续任务？

**问题的具体化**:
- MetaGPT 让 PM/Architect/QA agent 直接写入 shared message pool
- MemGPT 让 agent 直接修改 memory blocks
- MACLA 自动从 agent 交互中抽取 procedures
- 以上所有系统都假设 agent 写入的内容基本可靠

**但这个假设在 coding task 中不成立**:
- Worker 可能 hallucinate 一个不存在的 API（"函数 X 接受参数 Y"，但实际上不接受）
- Worker 可能误解上下文（"这个 bug 在第 42 行"，但实际在第 84 行）
- Worker 可能产生过时信息（"文件 X 有 100 行"，但 patch 后变成 120 行）

**级联效应**: 一个错误 fact 进入 memory 后，可能被后续 3-5 个任务引用，导致一系列错误决策。在 cost-aware routing 场景中，这意味着浪费 tokens 在基于错误前提的任务上。

**量化问题**: 在 SWE-bench 上，如果让 worker 直接写入 facts，错误率是多少？这些错误 facts 导致的下游任务失败率是多少？额外的验证成本是否能被下游节省的成本抵消？

**为什么现有方法不够**:
- MACLA 的 post-hoc refinement 是事后补救，错误 fact 已经污染了 memory
- MemGPT 的 memory 编辑是用户手动的，不适合自动化 routing
- 没有系统研究过"写入前验证"在 multi-agent coding memory 中的效果

### 2. Core Contribution

**贡献 1: 两步确认机制的设计与实现**
- Worker 返回结果时，提取 proposed facts（结构化：fact text, evidence ref, source agent, confidence）
- Verifier pipeline 检查每条 fact：
  - Contradiction check: 是否与 Track A 已有 facts 矛盾？
  - Evidence check: 是否有 evidence 支持（patch, log, test output）？
  - Relevance check: 是否与当前 task goal 相关？
  - Novelty check: 是否已经被已知 facts 包含？
- 只有通过所有检查的 facts 才写入 Track A（status: verified）
- 被拒 facts 记录 rejection reason，不写入 memory

**贡献 2: Verifier 错误率的系统分析**
- False accept rate: 错误 fact 被接受的比率
- False reject rate: 正确 fact 被拒绝的比率
- 与 verifier 类型的关系：LLM-based vs. rule-based vs. hybrid
- 与 task complexity 的关系：简单 task 的 fact 更容易验证

**贡献 3: Break-even 分析**
- 定义：在什么条件下，two-phase commit 的净收益为正？
- 设 V = 每次验证的 token cost
- 设 E = 错误 fact 导致的平均下游浪费
- 设 p = 无验证时的 fact error rate
- 设 q = verifier 的 false reject rate
- Break-even 条件：p * E > V * (1 + q) — 即验证成本 < 错误 fact 的期望损失
- 在 SWE-bench 上估算 p, E, V, q 的实际值

**贡献 4: Fact 粒度的精确定义**
- Coding task 中的 fact 类型：
  - Function signature fact: "函数 X 接受参数 (a: int, b: str) -> bool"
  - File structure fact: "文件 X 在路径 Y/Z 下"
  - Bug location fact: "bug 在文件 X 的第 N 行"
  - Dependency fact: "模块 A 依赖模块 B"
  - Test result fact: "测试 X 通过/失败"
- 每种类型的验证难度和错误率不同
- 需要 per-type analysis

### 3. Experimental Design

**Benchmark**: SWE-bench Verified (500 instances)

**Baselines**:
1. **Direct write**: Worker 产生的所有 facts 直接写入 memory（MetaGPT/MemGPT style）
2. **Post-hoc refinement**: Facts 直接写入，定期用 LLM 精炼（MACLA style）
3. **No memory**: Worker 不访问任何 memory（ablation baseline）

**Treatment**:
4. **Two-phase commit**: Worker proposed → LLM verifier → commit to Track A

**Metrics**:
- **Primary**: Task success rate (on SWE-bench)
- **Secondary**:
  - Fact accuracy (human annotation on 10% sample)
  - False accept rate / False reject rate
  - Total token cost (including verifier cost)
  - Downstream task failure rate attributed to memory errors
  - Context pollution (无关 fact 占比)

**Protocol**:
1. 对每个 SWE-bench instance，用主 agent (Claude) 拆分为 2-5 个子任务
2. 每个子任务分配给 worker (Claude CLI 或 Qwen)
3. Worker 执行任务，返回结果 + proposed facts
4. 在 "direct write" 条件下，facts 直接写入 Track A
5. 在 "two-phase commit" 条件下，facts 先经过 verifier
6. 后续子任务从 Track A 读取 context
7. 度量每个条件下的 task success rate 和 fact accuracy

**Statistical analysis**:
- Paired t-test (同一 instance 在不同条件下的表现)
- Bootstrap confidence intervals
- Per-type fact accuracy analysis

### 4. Expected Results

**假设 1**: Two-phase commit 的 fact accuracy > direct write
- 预期：direct write 的 fact error rate ~15-25%，two-phase commit 降到 ~3-8%
- 依据：LLM hallucination rate 在 coding task 中约 15-30%（SWE-bench 相关研究），verifier 可以过滤大部分

**假设 2**: Two-phase commit 的 task success rate >= direct write
- 预期：two-phase commit 提升 3-8% 的 task success rate
- 依据：错误 fact 的级联效应会导致后续任务失败，减少错误 fact 应该提升成功率
- 但：如果 verifier 太严格（false reject rate 高），可能拒绝有用 facts，反而降低成功率

**假设 3**: Two-phase commit 的净 token cost <= direct write
- 预期：verifier cost 约增加 10-20% 的 token，但下游任务节省 15-30%
- 依据：错误 fact 导致的下游任务重试和升级是主要成本来源
- Break-even point: 当 fact error rate > 10% 时，two-phase commit 的净收益为正

**假设 4**: LLM-based verifier 优于 rule-based verifier
- 预期：LLM-based 的 false reject rate 更低（更灵活），但 cost 更高
- Hybrid 方案（rule 先过滤 + LLM 再判断）可能是最优

**最可能被审稿人挑战的预期**:
- "3-8% 的 task success rate 提升是否足够显著？" — 需要 effect size 和 power analysis
- "Verifier cost 是否被低估？" — 需要详细的 token accounting
- "Fact accuracy 的评估标准是否客观？" — 需要 inter-annotator agreement

### 5. Positioning

**论文标题（候选）**:
- "Commit or Reject? Two-Phase Fact Verification for Multi-Agent Coding Memory"
- "Don't Trust Your Workers: Verifier-Gated Memory for Cost-Aware Coding Agents"
- "Towards Reliable Shared Memory in Multi-Agent Code Generation"

**相关工作的定位**:
- **vs. MetaGPT/ChatDev**: 它们用 direct write，我们用 two-phase commit。我们是首个在 multi-agent coding memory 中引入写入前验证的。
- **vs. MemGPT**: 它用层次化 memory + 自由检索，我们用双轨 + directed access + 写入验证。我们在 memory 质量控制上更进一步。
- **vs. MACLA**: 它用 post-hoc refinement，我们用 pre-commit verification。我们在错误传播的源头（写入时）而非下游（使用时）解决问题。
- **vs. FrugalGPT/RouteLLM**: 它们做 cost-aware routing 但不管 memory 质量。我们证明 memory 质量直接影响 routing 的成本效率。

**投稿目标**: EMNLP 2026 / ACL 2027 (main conference), 或 NeurIPS 2026 (Datasets and Benchmarks track)

**卖点**:
1. 首个系统研究 multi-agent coding memory 中 fact 可靠性的工作
2. 提出 two-phase commit 机制，有数据库事务的理论支撑
3. 提供 break-even 分析，有直接的工程指导价值
4. 在 SWE-bench 上的实证结果，可复现

---

## Refined Idea 2: Directed Memory Access for Cost-Aware Coding Agents

### 1. Problem Anchor

**一句话定义问题**: Multi-agent coding 系统的 memory 访问应该由 worker 自主检索（RAG），还是由 orchestrator 显式指定（directed）？在 coding task 中，哪种方式更省 token、更少噪声？

**问题的具体化**:
- MemGPT 用 embedding similarity 检索 memory
- Zep/Graphiti 用图查询检索相关 facts
- 所有这些系统假设"检索"是获取 memory 的默认方式

**但 coding task 有特殊性**:
- 任务有明确的 scope：repo, path, file, function
- 主 agent 通常知道"这个子任务需要什么信息"
- Worker 自主检索可能引入不相关的 facts（因为 embedding 相似度 ≠ 任务相关性）
- Retrieval 本身消耗 tokens（embedding 计算 + LLM reranking）

**核心假设**: 在 coding task 中，主 agent 的 task understanding > embedding similarity 作为 memory 访问的信号。

**为什么这个假设值得验证**:
- 如果成立，整个 agent memory 的设计范式可以从"retrieval-first"转向"directed-first"
- 对 cost-aware routing 特别重要：directed access 意味着主 agent 控制信息流，更容易做 cost optimization
- 但这个假设从未被实证验证——"directed access"在现有文献中甚至没有作为一个正式概念被提出

### 2. Core Contribution

**贡献 1: Directed Memory Access 的形式化定义**
- 定义：主 agent 根据 task metadata（repo, path, task type, dependencies）从 Track A 选择相关的 facts，组装成 context bundle，直接推送给 worker
- 对比 Free Retrieval：worker 根据自己的 query 做 embedding similarity search
- 对比 Hybrid：主 agent 指定 scope（repo, path），worker 在 scope 内做 retrieval
- 形式化：directed access = f(task_metadata, Track_A) → context_bundle
- 形式化：free retrieval = g(worker_query, Track_A) → context_bundle

**贡献 2: Context Bundle 组件的 Ablation Study**
- Context bundle 可以包含：
  - Verified facts (from Track A)
  - Path/file hints
  - Dependency graph snippet
  - Prior errors (同 repo 的历史失败记录)
  - Task goal 和 constraints
- Ablation: 逐一添加/移除组件，度量 worker performance
- 目标：找到 context bundle 的"最小有效集合"

**贡献 3: Task Complexity 的调节效应分析**
- 假设：简单 task（如 single-file bug fix）适合 directed access，复杂 task（如 multi-file refactoring）可能需要 retrieval
- 定义 task complexity metric：涉及文件数、依赖深度、代码行数
- 分层分析：在不同 complexity level 下，directed vs. retrieval 的表现

**贡献 4: Cost Accounting 的完整性**
- Directed access 的成本 = 主 agent 理解 task + 组装 bundle 的 tokens
- Free retrieval 的成本 = embedding 计算 + retrieval + worker 自己筛选的 tokens
- 需要完整的 cost accounting 来公平比较

### 3. Experimental Design

**Benchmark**: SWE-bench Verified (500 instances) + HumanEval (补充)

**Conditions** (2x2 + ablation):

| Condition | Memory Access | Context Bundle |
|-----------|:-------------:|:--------------:|
| A1 | Directed | Facts only |
| A2 | Directed | Full bundle (facts + paths + deps + errors) |
| B1 | Free Retrieval | Top-k by similarity |
| B2 | Free Retrieval | Top-k + reranking |
| C1 | Hybrid | Directed scope + retrieval within scope |
| D1 | No memory | Worker receives only task goal |

**Metrics**:
- **Primary**: Task success rate (pass@1 on SWE-bench)
- **Secondary**:
  - Total token cost (including orchestrator and worker)
  - Irrelevant fact injection rate (human annotation)
  - Context utilization rate (worker 实际使用了多少 context bundle 中的信息)
  - Orchestrator overhead (directed access 的额外成本)

**Protocol**:
1. 对每个 SWE-bench instance，主 agent 拆分子任务
2. 在 directed 条件下，主 agent 从 Track A 组装 context bundle
3. 在 retrieval 条件下，worker 用自己的 query 检索 Track A
4. Worker 接收 context + task goal，执行任务
5. 度量 task success rate, token cost, irrelevant fact rate

**Control variables**:
- 同一个 LLM 作为 worker（消除模型差异）
- 同一个 Track A 内容（消除 memory 内容差异）
- 同一个 task decomposition（消除拆分策略差异）

### 4. Expected Results

**假设 1**: Directed access 的 irrelevant fact injection rate < free retrieval
- 预期：directed 的无关 fact 占比 ~5-10%，retrieval 的 ~15-30%
- 依据：embedding 相似度不等于任务相关性，coding task 的 scope 很明确

**假设 2**: Directed access 的 total token cost <= free retrieval
- 预期：directed 的 orchestrator overhead ~500-1000 tokens，但节省 worker 端的 retrieval + filtering ~1500-3000 tokens
- 净节省：~500-2000 tokens per subtask
- 但：如果 task 很复杂，主 agent 需要更多 tokens 来理解 task，可能抵消节省

**假设 3**: Directed access 的 task success rate >= free retrieval
- 预期：directed 提升 2-5%（因为更少的无关 facts = 更少的干扰）
- 但：如果主 agent 遗漏了关键 facts，directed 可能比 retrieval 差
- 这取决于主 agent 的 task understanding 能力

**假设 4**: Hybrid 方案可能最优
- 预期：directed scope + retrieval within scope 可能结合两者优势
- 主 agent 指定大致范围（repo, path），worker 在范围内做精确检索

**假设 5**: Task complexity 调节 directed vs. retrieval 的效果
- 低复杂度 task: directed >= retrieval
- 高复杂度 task: directed < retrieval（主 agent 理解不完整）

**最可能被审稿人挑战的预期**:
- "Directed access 的优势可能只在主 agent 能力很强时成立" — 需要做主 agent 模型能力的调节效应分析
- "Hybrid 方案使 directed vs. retrieval 的对比变得复杂" — 需要清晰的 condition 设计
- "Task success rate 的提升可能不显著" — 需要 power analysis

### 5. Positioning

**论文标题（候选）**:
- "Don't Search, I'll Tell You: Directed Memory Access for Multi-Agent Coding"
- "Directed vs. Retrieval: Memory Access Patterns for Cost-Aware Coding Agents"
- "When to Push, When to Pull: Memory Access Strategies for Multi-Agent Code Generation"

**相关工作的定位**:
- **vs. MemGPT**: 它用 free retrieval（embedding similarity），我们用 directed access（主 agent 指定）。我们在 coding task 上证明 directed 更高效。
- **vs. Zep/Graphiti**: 它用图查询做 retrieval，我们不做检索而是推送。我们在 cost efficiency 上更有优势。
- **vs. RAG 系列工作**: RAG 假设检索是获取外部知识的默认方式。我们提出在 coding task 中，"推送"可能比"拉取"更好。
- **vs. Context Engineering (P14)**: 它讨论了多组件协作，我们做系统 ablation，给出定量的 context bundle 设计指导。

**投稿目标**: EMNLP 2026 / NAACL 2027 / COLM 2027

**卖点**:
1. 首个形式化定义并实证验证 directed memory access 的工作
2. 对 RAG 范式在 coding agent 场景下的适用性提出挑战
3. Context bundle ablation 给出直接的工程设计指导
4. 与 cost-aware routing 项目直接契合

---

## 两篇论文的关系

**论文 1 (Two-Phase Commit)** 解决"写入什么"的问题——如何保证进入 memory 的 facts 是可靠的。
**论文 2 (Directed Access)** 解决"读取什么"的问题——如何高效地把 memory 中的信息传递给 worker。

**两者的关系**:
- 论文 1 是论文 2 的前置条件——如果 memory 中的 facts 不可靠（没有 two-phase commit），directed access 推送的也是垃圾
- 论文 2 是论文 1 的下游验证——two-phase commit 验证后的 facts 通过 directed access 传递给 worker，形成完整的信息流

**建议的论文顺序**:
1. 先发论文 1（Two-Phase Commit）— 验证 memory 质量的基础
2. 再发论文 2（Directed Access）— 在论文 1 的基础上研究访问模式
3. 后续可以扩展到想法 9（Cost-Driven Retention）— memory 生命周期管理

**也可以合并为一篇大论文**:
- Title: "Reliable and Efficient Shared Memory for Cost-Aware Coding Agents"
- Contribution 1: Two-phase commit for fact verification
- Contribution 2: Directed access for context delivery
- Contribution 3: Cost-driven retention policy
- 这样一篇论文可以覆盖整个 shared memory 设计
