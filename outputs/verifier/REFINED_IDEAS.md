# Verifier 模块：精炼后的研究想法

**精炼日期**: 2026-06-24
**精炼对象**: Top 2 ideas (CAVE, 2SC)
**精炼内容**: Problem anchor, Core contribution, Experimental design, Expected results, Positioning

---

## Idea 1: Confidence-Adaptive Verification Escalation (CAVE)

### Problem Anchor

**核心问题**: 在 cost-aware coding-agent router 中，Verifier 需要在验证质量和验证成本之间取得最优平衡。现有方法使用固定的验证强度（如总是使用强模型），导致两种低效：(1) 对高置信度的正确输出过度验证，浪费计算资源；(2) 对低置信度的错误输出验证不足，导致低质量事实写入 shared memory。

**问题重要性**:
- **理论意义**: Li [P11] 的发现（弱模型自纠正率更高）挑战了"强模型更好验证"的直觉，需要新的理论框架来解释验证强度与验证效果的关系
- **实践意义**: 在 cost-aware router 中，验证成本直接影响系统总成本。如果 verifier 消耗的成本超过 worker 本身，整个路由策略就失去了意义
- **文献空白**: G6 — 没有 verifier 能在置信度不足时自动升级到更强模型

**问题形式化**:

设 worker 输出为 $x$，验证器集合为 $\{V_1, V_2, ..., V_k\}$，其中 $V_i$ 的验证强度和成本递增。目标是学习一个策略 $\pi: x \rightarrow \{V_1, V_2, ..., V_k, \text{accept}, \text{reject}\}$，使得：

$$\min_{\pi} \mathbb{E}[c(\pi(x))] \quad \text{s.t.} \quad \text{Quality}(\pi) \geq \tau$$

其中 $c(\cdot)$ 是验证成本，$\text{Quality}$ 是验证准确率，$\tau$ 是质量阈值。

### Core Contribution

**贡献 1: 置信度感知的验证升级策略**

设计一个基于置信度的动态验证升级策略：
- 轻量验证器（规则 + 小模型）对每个 worker 输出计算置信度分数 $s \in [0, 1]$
- 高置信度 ($s > \theta_h$): 直接接受，跳过进一步验证
- 中置信度 ($\theta_l < s \leq \theta_h$): 升级到中等模型验证
- 低置信度 ($s \leq \theta_l$): 升级到强模型验证或直接拒绝
- 阈值 $\theta_h, \theta_l$ 通过验证集上的成本-质量权衡优化

**贡献 2: 置信度校准方法**

设计专门针对编码任务验证的置信度校准方法：
- 特征工程：提取 worker 输出的结构特征（字段完整性、证据数量）、接地特征（路径存在率、行号有效率）、语义特征（结论-证据一致性）
- 校准模型：使用 temperature scaling 或 Platt scaling 校准置信度分数
- 校准目标：最小化 Expected Calibration Error (ECE)

**贡献 3: 成本-质量权衡的理论分析**

分析置信度自适应策略的最优性：
- 证明在一定假设下，CAVE 是成本-质量权衡的 Pareto 最优策略
- 分析置信度校准误差对策略性能的影响
- 给出 CAVE 相对于固定验证策略的成本节约上界

**贡献 4: 实验验证**

在真实编码任务上验证 CAVE 的有效性（详见实验设计）。

### Experimental Design

**实验 1: 置信度校准质量**

- **数据集**: 从 SWE-bench 或 HumanEval 中收集 worker 输出，标注验证结果（通过/拒绝）
- **方法**: 训练置信度模型，评估校准质量（ECE、reliability diagram）
- **基线**: 无校准（raw score）、temperature scaling、Platt scaling
- **指标**: ECE、Brier score、AUROC
- **预期**: CAVE 的置信度校准方法在 ECE 上优于基线

**实验 2: 成本-质量权衡**

- **数据集**: 同上
- **方法**: 在不同质量阈值 $\tau$ 下，比较 CAVE 与固定验证策略的成本和质量
- **基线**: 固定轻量验证、固定中等验证、固定强验证、随机升级
- **指标**: 验证成本（tokens/API calls）、验证质量（准确率、召回率）、总成本（worker + verifier）
- **预期**: CAVE 在相同质量阈值下，验证成本比固定强验证低 40-60%

**实验 3: 置信度操纵鲁棒性**

- **数据集**: 构造对抗样本——高置信度的错误输出、低置信度的正确输出
- **方法**: 分析 CAVE 在对抗场景下的表现
- **基线**: 固定验证策略
- **指标**: 对抗准确率、成本增加
- **预期**: CAVE 在对抗场景下仍优于固定策略，但成本增加

**实验 4: 端到端系统评估**

- **系统**: 将 CAVE 集成到 cost-aware coding-agent router 中
- **任务**: SWE-bench 上的编码任务
- **基线**: 无 verifier、固定 verifier、CAVE
- **指标**: 任务成功率、总成本、延迟
- **预期**: CAVE 在相同成本下任务成功率提升 10-20%

### Expected Results

**主要结果**:
1. CAVE 的置信度校准 ECE < 0.05（优于所有基线）
2. CAVE 在质量阈值 $\tau = 0.95$ 时，验证成本比固定强验证低 50%
3. CAVE 在端到端评估中，相同成本下任务成功率提升 15%

**消融实验**:
1. 置信度校准的贡献：去除校准后，成本增加 30%（因为升级策略更保守）
2. 动态升级的贡献：固定阈值后，质量下降 5%（因为无法适应不同难度的输出）
3. 成本-质量权衡：不同阈值下的 Pareto 曲线

**失败模式分析**:
1. 如果置信度校准误差 > 0.1，CAVE 的优势消失——需要更好的校准方法
2. 如果 worker 输出的置信度分布过于集中（都在高或低），CAVE 退化为固定策略——需要更多样化的 worker

### Positioning

**与现有工作的关系**:

| 工作 | 关系 | Delta |
|------|------|-------|
| SAFE [P01] | SAFE 使用固定验证强度 | CAVE 动态调整验证强度 |
| DiVA [P08] | DiVA 使用 agent+判别器混合 | CAVE 根据置信度选择验证器 |
| SuperCorrect [P10] | 固定教师-学生结构 | CAVE 动态选择验证强度 |
| Li [P11] | 揭示自纠正悖论 | CAVE 利用这一发现设计升级策略 |
| LCSV (I1) | LCSV 是四层验证流水线 | CAVE 在 LCSV 基础上增加置信度自适应 |

**论文定位**:

- **标题**: "Confidence-Adaptive Verification Escalation for Cost-Aware Multi-Agent Coding Systems"
- **核心主张**: 验证强度应该与置信度匹配，而非固定不变
- **贡献类型**: 方法 + 实证
- **目标会议**: ICSE 2027 (SE4AI track) 或 NeurIPS 2027 (Datasets & Benchmarks)
- **备选会议**: ASE 2027, EMNLP 2027

**故事线**:
1. 现有 verifier 使用固定验证强度，导致成本浪费或质量不足
2. Li [P11] 的发现表明"更强的验证器不一定更好"
3. CAVE 提出置信度自适应的验证升级策略
4. 实验证明 CAVE 在成本-质量权衡上优于所有基线
5. CAVE 可以集成到 cost-aware router 中，提升端到端性能

---

## Idea 2: Two-Step Commit Protocol for Multi-Agent Shared Memory (2SC)

### Problem Anchor

**核心问题**: 多 agent 编码系统中，shared memory 是核心协调媒介——worker 之间通过 shared memory 共享事实、协调行动。但现有系统允许 worker 直接写入 memory，没有验证门控。这导致两个严重问题：(1) 质量问题——低质量或错误的事实污染 memory，误导后续 worker；(2) 安全问题——恶意 worker 可以篡改 memory（XAMT [P07]），或泄露敏感数据（MRMMIA [P06]）。

**问题重要性**:
- **理论意义**: 将数据库事务保证（ACID）引入 LLM agent memory，是一个跨领域的理论贡献
- **实践意义**: shared memory 安全是多 agent 系统可靠运行的基础——没有安全的 memory，就没有可靠的 agent 协作
- **文献空白**: G3 (shared memory 安全未被研究) + G4 (两步提交不存在)

**问题形式化**:

设多 agent 系统有 $n$ 个 worker $\{W_1, W_2, ..., W_n\}$ 和一个 shared memory $M$。每个 worker 完成子任务后产生输出 $o_i$。目标是设计一个协议 $\Pi$，使得：

1. **安全性**: $M$ 中只包含经过验证的事实（无错误、无敏感数据、无篡改）
2. **活性**: 正确的 worker 输出最终会被写入 $M$（无死锁、无饥饿）
3. **效率**: 验证延迟可接受（不影响 worker 的执行效率）

### Core Contribution

**贡献 1: 两步内存提交协议**

设计 "worker 提议 / verifier 确认" 的两步提交协议：

**Step 1: Worker Propose**
- Worker 完成子任务后，输出进入 "proposed" 状态
- Proposed 输出存储在临时缓冲区，不直接写入 shared memory
- 提议包含：worker ID、任务 ID、输出内容、时间戳

**Step 2: Verifier Confirm**
- Verifier 对 proposed 输出执行四层验证（结构/接地/策略/质量）
- 验证通过 → 输出变为 "verified"，写入 shared memory
- 验证失败 → 输出变为 "rejected"，记录拒绝原因
- 所有状态变更记录在 append-only audit log

**Step 3: Conflict Resolution (可选)**
- 如果多个 worker 对同一事实产生冲突输出，使用对比选择（参考 I7 CMFS）
- 选择得分最高的版本写入 shared memory

**贡献 2: 状态机与一致性保证**

形式化协议的状态机：

```
[Proposed] --(验证通过)--> [Verified] --(写入)--> [In Memory]
[Proposed] --(验证失败)--> [Rejected]
[Proposed] --(超时)--> [Expired]
```

一致性保证：
- **原子性**: 每个 propose 要么完全写入，要么完全不写入
- **一致性**: 写入后 memory 满足所有验证约束
- **隔离性**: 多个 propose 并发执行不互相干扰
- **持久性**: verified 的事实不会丢失

**贡献 3: 安全分析**

威胁建模与防御分析：

| 威胁 | 攻击方式 | 防御措施 |
|------|---------|---------|
| Memory 篡改 (XAMT) | 恶意 worker 直接写入 memory | 两步提交门控，只有 verifier 能写入 |
| 隐私泄露 (MRMMIA) | Worker 输出包含敏感数据 | 策略验证层检测敏感数据 |
| 过度帮助 (P15) | Worker 绕过 read-only 约束 | 执行约束验证 |
| Verifier 攻击 | 攻击 verifier 使其放行恶意输出 | 多样性防御、audit log |
| 拒绝服务 | 大量 propose 拒绝 verifier | 速率限制、优先级队列 |

**贡献 4: 实验验证**

在真实多 agent 编码系统上验证 2SC 的有效性（详见实验设计）。

### Experimental Design

**实验 1: 协议正确性验证**

- **方法**: 使用 TLA+ 或类似的 formal specification 语言建模协议
- **验证**: 模型检查安全性（无非法写入）和活性（无死锁）
- **场景**: 正常执行、并发 propose、verifier 崩溃、worker 崩溃
- **预期**: 协议满足所有安全性、活性、一致性保证

**实验 2: 性能开销分析**

- **系统**: 在多 agent 编码系统中实现 2SC
- **方法**: 比较有 2SC 和无 2SC 的系统性能
- **指标**: 端到端延迟、throughput、verifier 负载
- **变量**: worker 数量 (1, 5, 10, 20)、propose 频率
- **预期**: 2SC 增加的延迟 < 10%（验证是轻量的）

**实验 3: 安全性评估**

- **攻击场景**: 模拟 XAMT 风格的 memory 篡改攻击
- **方法**: 比较有 2SC 和无 2SC 的系统在攻击下的表现
- **指标**: 攻击成功率、memory 中的错误事实数量
- **预期**: 2SC 将攻击成功率从 ~80% 降低到 < 5%

**实验 4: 端到端系统评估**

- **系统**: 将 2SC 集成到 cost-aware coding-agent router 中
- **任务**: SWE-bench 上的编码任务
- **基线**: 无门控直接写入、后验检查（MemCoder 风格）、2SC
- **指标**: 任务成功率、memory 质量（错误事实比例）、总成本
- **预期**: 2SC 在相同成本下任务成功率提升 10-15%

### Expected Results

**主要结果**:
1. TLA+ 模型检查通过——协议满足所有安全性和活性保证
2. 2SC 增加的端到端延迟 < 10%——性能开销可接受
3. 2SC 将 memory 篡改攻击成功率从 80% 降低到 < 5%——安全保证有效
4. 2SC 在端到端评估中任务成功率提升 12%——质量保证有效

**消融实验**:
1. 两步提交的贡献：去除门控后，memory 中错误事实增加 5 倍
2. Audit log 的贡献：去除 log 后，攻击检测率下降 30%
3. 超时机制的贡献：去除超时后，系统活性下降（死锁风险增加）

**失败模式分析**:
1. 如果 verifier 本身被攻击，2SC 的安全保证失效——需要多样性防御
2. 如果 propose 频率过高，verifier 可能成为瓶颈——需要负载均衡
3. 如果 verifier 的验证延迟过高，worker 可能超时——需要异步验证

### Positioning

**与现有工作的关系**:

| 工作 | 关系 | Delta |
|------|------|-------|
| MemCoder [P14] | 后验验证反馈 | 2SC 是前置验证门控 |
| MACLA [P13] | 记忆质量评估 | 2SC 是写入保护机制 |
| XAMT [P07] | 展示攻击 | 2SC 提供防御 |
| MRMMIA [P06] | 揭示隐私风险 | 2SC 的策略验证防护隐私泄露 |
| 数据库 WAL | 成熟技术 | 2SC 将其迁移到 LLM agent 领域 |

**论文定位**:

- **标题**: "Two-Step Commit: Securing Shared Memory in Multi-Agent Coding Systems"
- **核心主张**: Shared memory 需要事务保证——worker 提议 / verifier 确认的两步提交
- **贡献类型**: 协议设计 + 安全分析 + 实证
- **目标会议**: ICSE 2027 (SE4AI track) 或 CCS 2027 (AI Security)
- **备选会议**: NDSS 2027, USENIX Security 2027

**故事线**:
1. 多 agent 编码系统依赖 shared memory 协调，但 memory 安全未被研究
2. XAMT 和 MRMMIA 揭示了 memory 篡改和隐私泄露的风险
3. 2SC 提出两步提交协议——worker 提议 / verifier 确认
4. 形式化验证证明协议的安全性和活性
5. 实验证明 2SC 在性能开销可接受的前提下，显著提升安全性和任务成功率

---

## 两个想法的对比

| 维度 | CAVE | 2SC |
|------|------|-----|
| **核心问题** | 验证效率 | 验证安全 |
| **贡献类型** | 方法 + 实证 | 协议 + 安全分析 |
| **技术难度** | 中等（置信度校准） | 中低（协议设计） |
| **新颖性** | 高（挑战直觉） | 中高（跨领域迁移） |
| **实用性** | 高（直接降成本） | 高（直接提升安全） |
| **目标会议** | ICSE / NeurIPS | ICSE / CCS |
| **实验难度** | 中等（需要标注数据） | 中低（需要攻击模拟） |

---

## 推荐策略

### 策略 A: 两篇独立论文

**论文 1 (CAVE)**: 投 ICSE 2027 SE4AI track 或 NeurIPS 2027
- 故事线：验证效率问题 → 置信度自适应 → 成本-质量权衡
- 核心贡献：CAVE 方法 + 实验验证

**论文 2 (2SC)**: 投 ICSE 2027 SE4AI track 或 CCS 2027
- 故事线：memory 安全问题 → 两步提交协议 → 安全保证
- 核心贡献：2SC 协议 + 安全分析

**优点**: 两篇论文独立发表，最大化影响力
**缺点**: 工作量大，需要两个完整的实验

### 策略 B: 合并为一篇系统论文

**论文**: 投 ICSE 2027 (主会议)
- 故事线：Verifier 的完整架构 → 置信度自适应验证 + 两步内存提交
- 核心贡献：完整的 verifier 系统设计

**优点**: 工作量集中，论文更完整
**缺点**: 贡献点分散，审稿人可能认为"不够聚焦"

### 策略 C: 主攻 CAVE，2SC 作为扩展

**主论文 (CAVE)**: 投 NeurIPS 2027 或 ICML 2027
- 故事线：验证效率问题 → 置信度自适应 → 成本-质量权衡
- 核心贡献：CAVE 方法

**扩展 (2SC)**: 作为 CAVE 的系统实现，集成到 cost-aware router 中
- 在 CAVE 论文中增加一节讨论 memory 安全
- 2SC 作为 future work 或技术报告

**优点**: 聚焦 ML 方法，适合 ML 会议
**缺点**: 2SC 的贡献被弱化

### 最终推荐

**推荐策略 A: 两篇独立论文**

**理由**:
1. CAVE 和 2SC 解决不同维度的问题（效率 vs 安全），适合独立发表
2. 两篇论文可以投不同类型的会议（ML vs SE/Security），扩大影响力
3. 工作量虽然大，但两个想法的技术风险都可控
4. 两篇论文可以互相引用，形成"Verifier 系列"

**时间线**:
- **2026 Q3-Q4**: 实现 CAVE 和 2SC，进行实验
- **2027 Q1**: 投稿 CAVE 到 NeurIPS 2027 (deadline ~May 2027)
- **2027 Q2**: 投稿 2SC 到 CCS 2027 (deadline ~May 2027)
- **备选**: 如果需要更多时间，投稿到 ICSE 2027 (deadline ~Sep 2027)
