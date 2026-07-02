# AutoVibeIdea

**用 AI Agent 自动化科研选题：从文献调研到 idea 精炼，全流程自动化**

科研中最耗时的不是写论文，而是找到一个值得写的 idea。AutoVibeIdea 把「文献调研 → 想点子 → 多维筛选 → 深度精炼」这条完整链路交给 AI Agent 执行。你给一个研究方向，它输出一份 venue-ready 的 proposal。基于 Claude Code Skills 构建，外接 GPT-5.4 做交叉评审，打破单模型自评的盲区。

## Quick Start

```bash
/idea-pipeline "graph foundation models for relational databases" -- venue: ICML
```

一条命令触发四阶段流水线。每个阶段之间有 checkpoint，你可以介入调整方向，也可以全程自动跑完。

## 前置依赖

### 必须

- **Claude Code** — Anthropic 的 CLI 工具（Agent 执行层）
- **Codex MCP Server** — 调用外部 LLM（GPT-5.4）进行头脑风暴和交叉评审：
  ```bash
  claude mcp add codex -s user -- codex mcp-server
  ```

### 可选

- **Zotero MCP** — 让 `/lit-survey` 搜索你的 Zotero 论文库
- **Obsidian MCP** — 让 `/lit-survey` 搜索你的 Obsidian Vault

## Skills 一览

| Skill | 用途 | 调用示例 |
|-------|------|----------|
| `/lit-survey` | 文献调研，构建研究景观图 + Gap 识别 | `/lit-survey "LLM for code generation"` |
| `/idea-gen` | 生成 8-12 个 idea，初筛至 4-6 个 | `/idea-gen "efficient inference"` |
| `/idea-screen` | 新颖性 + 审稿人模拟 + 战略评估 | `/idea-screen "ideas" -- venue: NeurIPS` |
| `/idea-refine` | 迭代精炼至 venue-ready proposal | `/idea-refine "top idea description"` |
| `/idea-pipeline` | 一键全流程编排 | `/idea-pipeline "topic" -- venue: ICML` |

## 核心工作流

```
研究方向 → Phase 1 → Phase 2 → Phase 3 → Phase 4 → 最终报告
```

1. **文献调研** — 搜索 arXiv、Scholar、本地 PDF、Zotero、Obsidian，输出 `LANDSCAPE.md`（景观图 + Gap 矩阵）
2. **想点子** — 外部 LLM 头脑风暴 8-12 个 idea，经可行性 / 新颖性 / He 四维评分（≥12/20）过滤至 4-6 个，输出 `IDEAS_FILTERED.md`
3. **多维筛选** — 三模块并行评估：新颖性查重 + 目标会议审稿人模拟（3 审 + meta review）+ 战略契合度，输出 `SCREENING_RANKED.md`
4. **深度精炼** — 冻结 Problem Anchor，提取逻辑骨架，外部 LLM 迭代评审（最多 5 轮，目标 ≥9/10），输出 `FINAL_PROPOSAL.md`

## 会议 Profile

`venue-profiles/` 目录包含目标会议的审稿人画像，用于 Phase 3 审稿人模拟：

- `ICML.md` — ML 理论与方法
- `NeurIPS.md` — 广泛 ML + 交叉学科
- `VLDB.md` — 数据库与数据系统

**添加新会议**：复制 `venue-profiles/_template.md`，按模板填写审稿人偏好和评审标准即可。

## 多模型架构

| 角色 | 模型 | 职责 |
|------|------|------|
| 执行层 | Claude | 文献搜索、文件管理、规则化筛选、骨架提取、提案撰写 |
| 评审层 | GPT-5.4（via Codex MCP） | 头脑风暴、新颖性交叉验证、审稿人模拟、迭代评审 |

为什么要两个模型？同一个模型生成又评审，容易陷入自我确认偏差。外部模型做 adversarial review，能发现执行模型的盲区。

## 输出文件

| 文件 | 位置 | 内容 |
|------|------|------|
| `LANDSCAPE.md` / `.json` | `outputs/` | 文献景观图 + 结构化数据 |
| `IDEAS_RAW.md` | `outputs/` | 全部生成的 idea |
| `IDEAS_FILTERED.md` | `outputs/` | 过滤后的 idea（含评分） |
| `SCREENING_REPORT.md` | `outputs/` | 完整筛选报告 |
| `SCREENING_RANKED.md` | `outputs/` | 排序后的 idea + 综合评分 |
| `FINAL_PROPOSAL.md` | `refine-logs/` | 最终精炼提案 |
| `REFINEMENT_REPORT.md` | `refine-logs/` | 精炼过程记录 |
| `IDEA_DISCOVERY_REPORT.md` | `outputs/` | 全流程汇总报告 |

## 单独使用

不需要跑全流程。每个 skill 都可以独立调用：

```bash
# 只做文献调研
/lit-survey "federated learning on heterogeneous data"

# 只想点子（会自动读取 outputs/LANDSCAPE.json，如果有的话）
/idea-gen "privacy-preserving machine learning"

/idea-gen "skills + memory, with some graph-based idea. it is used to improve the success rate of the agent that skills."

# 只做筛选（传入 idea 描述或文件路径）
/idea-screen "outputs/IDEAS_FILTERED.md" -- venue: VLDB

# 只精炼一个 idea
/idea-refine "outputs/SCREENING_RANKED.md 中排名第一的 idea"
```

## 致谢

- 基于 [ARIS](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep) 框架发展而来
- 整合了 [何丙胜教授的科研选题框架](https://github.com/HeBingsheng/openbs)（四维评估体系）
- 评审方法论受 first-principles paper review 启发

## License

MIT
