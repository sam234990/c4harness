# 文献全景：Multi-Agent Shared Memory 与 Cost-Aware Task Routing

**日期**: 2026-06-23
**分析论文数**: 18
**来源**: arXiv, WebSearch

## Executive Summary

当前 LLM multi-agent 系统的研究可以分为三个层次：(1) 单一框架内的多 agent 协作（如 MetaGPT、ChatDev、AutoGen），(2) 模型级路由与级联（如 RouteLLM、FrugalGPT），(3) 跨 harness 的异构 agent 编排。前两个方向已有大量工作，但第三个方向——**不同 agent harness（Codex、Claude Code、OpenCode）之间的成本感知调度与共享 memory**——几乎是空白。

在 memory 方面，现有工作主要集中在：单 agent 的层次化 memory（MemGPT/Letta）、多 agent 共享 message pool（MetaGPT、ChatDev）、以及 KV cache 共享（PolyKV）。但"面向 coding task 的多层图 memory + directed access + verifier-confirmed facts"这种设计尚无直接先例。

在路由方面，FrugalGPT 和 RouteLLM 证明了"按难度分流到不同模型"可以大幅降本（最高 98%），但它们只做 request-level 路由，不做 task decomposition + agent harness 选择 + 结果验收。GraphPlanner 是最接近的工作——它用图 memory 做 multi-agent LLM 路由——但它不涉及跨 harness 协作。

**关键发现**：你的项目（cost-aware coding-agent router with multi-layer graph memory）在现有文献中没有直接竞品。最接近的工作分散在三个方向，但没有一个把它们整合起来。

## Paper Table

| ID | Paper | Authors | Year | Venue | Method | Key Result | Relevance | Source |
|----|-------|---------|------|-------|--------|------------|-----------|--------|
| P01 | FrugalGPT: How to Use LLMs While Reducing Cost | Chen, Zaharia, Zou | 2023 | arXiv | LLM cascade: 学习哪些查询用哪个模型 | 匹配 GPT-4 性能的同时降低 98% 成本 | 高：证明了按难度路由的降本潜力 | arXiv |
| P02 | RouteLLM: Learning to Route LLMs with Preference Data | LMSYS | 2024 | arXiv | 用偏好数据训练路由器，选择 strong/weak 模型 | 在保持质量的同时显著降低成本 | 高：request-level 路由的代表工作 | arXiv |
| P03 | UCCI: Calibrated Uncertainty for Cost-Optimal LLM Cascade Routing | Kotte | 2026 | arXiv | 校准不确定性 → 每查询错误概率 → 成本最优阈值 | 降低 31% 推理成本，F1=0.91 | 高：最新的 cascade 路由，有理论保证 | arXiv |
| P04 | SCOPE: Scalable and Controllable Routing via Pre-hoc Reasoning | Cao et al. | 2026 | arXiv | RL 训练路由器，预测模型成本和性能，支持零样本泛化 | 准确率提升 25.7% 或成本降低 95.1% | 高：可扩展路由，支持新模型零样本 | arXiv |
| P05 | GraphPlanner: Graph Memory-Augmented Agentic Routing | Feng et al. | 2026 | arXiv | 异构图 memory + MDP 决策 → 为每个查询生成 agent 工作流 | 准确率提升 9.3%，GPU 成本从 186 GiB 降到 1 GiB | 高：最接近"multi-agent 路由 + memory"的工作 | arXiv |
| P06 | ACAR: Adaptive Complexity Routing for Multi-Model Ensembles | Kumaresan | 2026 | arXiv | 自一致性方差 σ 路由 → 单/双/三模型执行模式 | 55.6% 准确率，54.2% 任务避免了全集成 | 中：多模型编排，但不做任务拆分 | arXiv |
| P07 | MetaGPT: Meta Programming for Multi-Agent Collaborative Framework | Hong et al. | 2023 | NeurIPS | 多角色 agent（PM/Architect/QA）+ 共享 message pool + 结构化文档 | 显著降低代码生成中的幻觉 | 高：多 agent 共享 memory 的经典架构 | arXiv |
| P08 | ChatDev: Communicative Agents for Software Development | Qian et al. | 2023 | ACL | chat chain + 角色 agent（CEO/CTO/Programmer）+ 对话式 memory | 通过统一语言通信实现多 agent 协作 | 高：多 agent 软件开发的代表 | arXiv |
| P09 | MemGPT: Towards LLMs as Operating Systems | Packer et al. | 2023 | ICLR | 虚拟上下文管理：层次化 memory（主存/外存）+ 中断控制流 | 超越上下文窗口限制，支持大文档分析和长期对话 | 高：层次化 memory 的开创性工作 | arXiv |
| P10 | MACLA: Learning Hierarchical Procedural Memory for LLM Agents | Forouzandeh et al. | 2025 | arXiv | 外部层次化过程 memory + 贝叶斯选择 + 对比精炼 | 78.1% 平均性能，构建 memory 仅需 56 秒 | 中：外部 memory + 经验复用 | arXiv |
| P11 | Agent Memory Below the Prompt: Persistent Q4 KV Cache | Shkolnikov | 2026 | arXiv | Q4 量化 KV cache 持久化 + 多 agent 共享 | 4x 更多 agent 上下文，TTTF 降低 136x | 中：底层 memory 共享优化 | arXiv |
| P12 | PolyKV: Shared Asymmetrically-Compressed KV Cache Pool | Patel, Joshi | 2026 | arXiv | 多 agent 共享压缩 KV cache 池 | 97.7% memory 减少，+0.57% PPL | 中：推理层 memory 共享 | arXiv |
| P13 | Small LLMs Are Weak Tool Learners: A Multi-LLM Agent | Shen et al. | 2024 | arXiv | 分解为 planner/caller/summarizer，每个用不同 LLM | 超越单 LLM 方法 | 中：多 LLM 分工的早期工作 | arXiv |
| P14 | Context Engineering for Multi-Agent LLM Code Assistants | Haseeb | 2025 | arXiv | 多组件协作：Intent Translator + 文献检索 + Claude Code sub-agents | 单次成功率和上下文一致性显著提升 | 中：多 harness 协作的实际案例 | arXiv |
| P15 | Towards Effective GenAI Multi-Agent Collaboration | Shu et al. | 2024 | arXiv | 协调模式（并行通信 + payload 引用）+ 路由模式 | 目标成功率 90%，比单 agent 提升 70% | 中：企业级多 agent 协作评估 | arXiv |
| P16 | Modality-Native Routing in Agent-to-Agent Networks (MMA2A) | Srinivasan | 2026 | arXiv | 检查 Agent Card 能力声明 → 原生模态路由 | 任务准确率提升 20pp | 中：agent 间路由的协议层设计 | arXiv |
| P17 | XAMT: Bilevel Optimization for Covert Memory Tampering in MAS | Sharma et al. | 2025 | arXiv | 攻击异构 MAS 的共享 memory（MARL ER buffer + RAG KB） | 亚百分比投毒率即可有效攻击 | 低：安全视角看 shared memory 漏洞 | arXiv |
| P18 | MRMMIA: Membership Inference Attacks on Memory in Chat Agents | Chen et al. | 2026 | arXiv | 多重调用探针 → 推断 agent memory 成员资格 | 在黑盒/灰盒/白盒设置下均有效 | 低：agent memory 隐私风险 | arXiv |

## Thematic Analysis

### Theme 1: LLM 模型级路由与级联（Model-Level Routing & Cascade）
**Status**: active
**Dominant approach**: 训练一个轻量路由器，根据查询难度选择 strong/cheap 模型
**Papers**: P01, P02, P03, P04, P06

这个方向已经相当成熟。FrugalGPT (P01) 开创了"级联"思路：先用便宜模型，不够自信再升级。RouteLLM (P02) 用偏好数据训练路由器。UCCI (P03) 加入了校准不确定性，有理论最优保证。SCOPE (P04) 做到了可扩展和零样本泛化。

**关键共识**：按查询难度路由可以降本 30-98%，且质量损失可控。
**未解决问题**：这些都是 request-level 路由，不涉及任务拆分、agent 选择或结果验收。

### Theme 2: 多 Agent 软件开发框架（Multi-Agent SE Frameworks）
**Status**: mature
**Dominant approach**: 定义角色 agent + 共享 message pool + 链式对话
**Papers**: P07, P08

MetaGPT (P07) 和 ChatDev (P08) 是这个方向的两个标杆。它们的核心是"角色分工 + 共享信息池"。MetaGPT 用结构化文档（PRD、设计文档）作为 agent 间通信介质，ChatDev 用 chat chain 驱动。

**关键共识**：多 agent 协作比单 agent 好，结构化通信比自由对话好。
**未解决问题**：memory 是 message pool 形式，不是分层图设计；没有成本路由；没有跨 harness 协作。

### Theme 3: Agent Memory 架构（Agent Memory Architecture）
**Status**: active
**Dominant approach**: 层次化 memory + 按需检索
**Papers**: P09, P10, P11, P12

MemGPT (P09) 是这个方向的开创者——把 OS 的虚拟内存思想搬到 LLM，用主存/外存分层管理上下文。MACLA (P10) 把 memory 做成了外部层次化过程 memory，用贝叶斯选择和对比精炼来管理。P11 和 P12 在底层做了 KV cache 共享优化。

**关键共识**：层次化 memory 有效，外部 memory 比纯 context window 更可扩展。
**未解决问题**：这些 memory 都是单 agent 或同构多 agent 的，没有面向异构 harness 的 directed memory access。

### Theme 4: Multi-Agent 编排与路由（Multi-Agent Orchestration & Routing）
**Status**: emerging
**Dominant approach**: 图结构 + 强化学习 + agent 工作流生成
**Papers**: P05, P13, P15, P16

GraphPlanner (P05) 是最接近你项目的工作：它用异构图 memory 做 multi-agent LLM 路由，为每个查询生成 agent 工作流（选择 LLM backbone + agent role）。P13 把任务分解为 planner/caller/summarizer，每个用不同 LLM。P15 评估了企业级多 agent 协作的效果。

**关键共识**：agent 级路由比模型级路由更灵活，但工程复杂度也更高。
**未解决问题**：没有跨 harness（Codex/Claude/OpenCode）的路由；没有 cost-aware 的任务拆分；没有 verifier 验收机制。

## Gap Identification Matrix

| Gap ID | Gap Description | Evidence (papers) | Gap Type | Confidence |
|--------|----------------|-------------------|----------|------------|
| G1 | **跨 harness 的 cost-aware task routing**：现有路由都在单一框架内（同一 LLM API 或同一 agent harness），没有"主 Codex + 子 Claude/OpenCode"这种跨 harness 路由 | P01-P06 做模型路由，P07-P08 做同框架多 agent | cross-domain transfer | HIGH |
| G2 | **面向 coding task 的多层图 memory**：现有 memory 要么是 message pool（P07/P08），要么是层次化 context（P09），要么是 KV cache 共享（P11/P12）。没有"Worker Task Node + Context Pack + Artifact Node"的分层图设计 | P09, P10, P11, P12 | overlooked formulation | HIGH |
| G3 | **Directed memory access for subagents**：现有多 agent memory 都允许 agent 自由检索（相似度搜索）。没有"主 agent 指定上下文，subagent 只拿 context bundle"的受控访问模式 | P07, P08, P09 | untested assumption | HIGH |
| G4 | **Worker-proposed / verifier-committed memory**：现有系统让 agent 直接写入共享 memory。没有"worker 提出事实 → verifier 验证 → orchestrator 提交"的两步确认机制 | P07, P08, P10 | overlooked formulation | MEDIUM |
| G5 | **Cost ledger + routing policy 联动**：FrugalGPT/RouteLLM 做了成本路由，但不记录"哪些任务值得委托、哪些需要升级"的历史。没有 cost ledger 反过来优化 routing policy 的闭环 | P01, P02, P03, P04 | missing diagnostic | MEDIUM |
| G6 | **跨 harness 的 task decomposition**：MetaGPT/ChatDev 在单一框架内拆任务。没有"这个子任务适合 Codex subagent，那个适合 Claude CLI"的跨 harness 拆分策略 | P07, P08, P13 | cross-domain transfer | HIGH |
| G7 | **Agent memory 隐私与安全**：P17/P18 指出共享 memory 是攻击面。但在 cost-aware routing 场景下，"把私有代码发给便宜 provider"的安全模型还没有被系统研究 | P17, P18 | untested assumption | MEDIUM |

## References

- P01: Chen, L., Zaharia, M., & Zou, J. (2023). FrugalGPT: How to Use Large Language Models While Reducing Cost and Improving Performance. arXiv:2305.05176.
- P02: LMSYS. (2024). RouteLLM: Learning to Route LLMs with Preference Data. arXiv.
- P03: Kotte, V. (2026). UCCI: Calibrated Uncertainty for Cost-Optimal LLM Cascade Routing. arXiv:2605.18796.
- P04: Cao, Q. et al. (2026). SCOPE: Scalable and Controllable Routing via Pre-hoc Reasoning. arXiv:2601.22323.
- P05: Feng, T. et al. (2026). GraphPlanner: Graph Memory-Augmented Agentic Routing for Multi-Agent LLMs. arXiv:2604.23626.
- P06: Kumaresan, R. (2026). ACAR: Adaptive Complexity Routing for Multi-Model Ensembles. arXiv:2602.21231.
- P07: Hong, S. et al. (2023). MetaGPT: Meta Programming for A Multi-Agent Collaborative Framework. arXiv:2308.00352.
- P08: Qian, C. et al. (2023). ChatDev: Communicative Agents for Software Development. arXiv:2307.07924.
- P09: Packer, C. et al. (2023). MemGPT: Towards LLMs as Operating Systems. arXiv:2310.08560.
- P10: Forouzandeh, S. et al. (2025). MACLA: Learning Hierarchical Procedural Memory for LLM Agents. arXiv:2512.18950.
- P11: Shkolnikov, Y. (2026). Agent Memory Below the Prompt: Persistent Q4 KV Cache for Multi-Agent LLM Inference. arXiv:2603.04428.
- P12: Patel, I. & Joshi, I. (2026). PolyKV: A Shared Asymmetrically-Compressed KV Cache Pool. arXiv:2604.24971.
- P13: Shen, W. et al. (2024). Small LLMs Are Weak Tool Learners: A Multi-LLM Agent. arXiv:2401.07324.
- P14: Haseeb, M. (2025). Context Engineering for Multi-Agent LLM Code Assistants. arXiv:2508.08322.
- P15: Shu, R. et al. (2024). Towards Effective GenAI Multi-Agent Collaboration. arXiv:2412.05449.
- P16: Srinivasan, V. (2026). Modality-Native Routing in Agent-to-Agent Networks. arXiv:2604.12213.
- P17: Sharma, A. et al. (2025). XAMT: Bilevel Optimization for Covert Memory Tampering. arXiv:2512.15790.
- P18: Chen, K. et al. (2026). MRMMIA: Membership Inference Attacks on Memory in Chat Agents. arXiv:2605.27825.
