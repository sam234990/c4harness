# Multi-Harness Shared Task Memory Graph

**日期**: 2026-06-25  
**目标**: 为 Codex + Claude CLI / OpenCode / Codex subagent 等多 harness 在**一次任务内部**协作，设计一套尽量简单、可扩展、可落地的 shared memory 与文件协作结构。

## 范围边界

本文只设计单次任务运行期间的 Shared Task Memory：worker 当前需要知道什么、能看到什么、产生了哪些 artifact，以及多个 worker 如何围绕文件协作。

它不负责：

- 保存跨任务的 Task Contract Graph 历史版本；
- 统计历史任务的成功、失败、返工和升级；
- 形成 worker 长期能力画像；
- 为 Dashboard 保存长期 Token/延迟统计；
- 把过去全部任务内容开放给当前 worker 检索。

这些内容属于独立的 [Execution History](history.md)。两者可以暂时共用一个 SQLite 文件，但必须使用不同 repository、表语义和生命周期。

```text
Shared Task Memory                 Execution History
当前任务的协作上下文               跨任务的已发生事实
Context Pack / Artifact            Plan snapshot / Outcome
Visibility / File coordination     Failure attribution / Token
任务结束后可压缩或清理              Append-only、可审计、可聚合
```

另外，Decompose 产生的 `TaskContractGraph` 是规划结构；本文的图是执行期间的 `Context-Artifact Graph`。二者可以通过 node id 关联，但不是同一张图。

## 核心结论

我们不做复杂的通用 memory 框架，而是做一个面向 coding task 的 **轻量分层图**。

最简单的结构是：

```text
Private Orchestrator State
  -> Worker Task Node
      -> Context Pack
          -> File / Artifact Node
```

它不是严格四层都必须存在。默认情况下：

- `Private Orchestrator State` 可以只存在于主 harness 内部，不一定落库。
- `Worker Task Node` 是每次委托任务的核心节点。
- `Context Pack` 是可选的，只有 worker 背景信息不足时才创建。
- `File / Artifact Node` 表示真实文件、日志、patch、worker 输出等。

一句话：

**主 harness 保留私有控制权，worker 只拿到被投喂的任务节点和必要上下文；文件作为共享资源节点，通过锁、patch proposal 和 verifier 管理。**

## 为什么这样设计

我们需要同时满足两个方向：

### 复杂任务

当任务很长、worker 很多、背景信息复杂时，worker 可能只看一个 subtask node 不够。

因此需要 `Context Pack`：

```text
Context Pack
  - 简短总结
  - 背景事实
  - 项目约定
  - 相关文件地图
  - deeper references
```

它的形态类似 Codex skills：

```text
summary first
  -> references
  -> concrete files
```

worker 先读 summary，必要时再打开具体引用。

### 简单任务

当只有一个主 harness 和一个 worker 时，系统必须足够快。

因此顶层私有节点不需要真实创建：

```text
主 harness 内部计划
  -> dispatch packet
  -> worker result
  -> ledger
```

这时只需要记录 worker 任务、结果、token、验证状态即可。

## 节点类型

### 1. Private Orchestrator State

这是主 harness 的私有状态。

包含：

- 用户原始目标
- 总体计划
- 任务拆解
- 路由策略
- verifier / hook 策略
- 当前任务的用量摘要
- 不希望 worker 看到的控制信息

重要原则：

**worker 不直接读取这一层。**

第一版甚至可以不把它落库，只让它存在于主 harness 或 orchestrator 进程内部。

如果需要在 graph 中追踪委托关系，可以创建一个轻量 `control` node。这个节点只保存任务标题、repo、公开元数据，不保存主 harness 的私有推理、hook 细节或隐藏 verifier policy。

### 2. Worker Task Node

这是 worker 真正接收的任务节点。

包含：

- worker-visible goal
- assigned harness，例如 `claude_cli` / `qwen_subagent`
- allowed files
- allowed context packs
- constraints，例如 read-only / patch / no network
- status
- worker output
- proposed facts
- proposed patches
- 本次节点的 token usage
- verifier result

这是系统里最重要的实体。

### 3. Context Pack

这是可选背景包。

当 worker 缺背景时，主 harness 不应该把全部 memory 塞过去，而是创建或选择一个 context pack。

包含：

- 简短说明
- 已验证事实
- 相关模块说明
- 项目约定
- 当前任务中已经验证、并由主 harness 选择的前置结论
- 指向具体 artifact/file 的引用

原则：

**Context Pack 是 worker 可读的背景材料，不包含主 harness 的私有控制信息。**

### 4. File / Artifact Node

表示真实材料：

- 源代码文件
- 配置文件
- 日志
- 测试输出
- patch proposal
- worker raw output
- transcript

一个 file node 可以连接多个 worker node。

因此文件层天然是图结构，不是树结构。

## 边类型

最少只需要这些边：

| Edge | 含义 |
|---|---|
| `delegates_to` | 主任务委托给 worker node |
| `uses_context` | worker node 使用某个 context pack |
| `may_read` | worker 可以读取某个 file/artifact |
| `proposes_patch` | worker 对某文件提出 patch |
| `evidence_for` | artifact 支持某个结论 |
| `conflicts_with` | 两个 worker/patch 产生冲突 |
| `verified_as` | verifier 接受或拒绝某个输出 |

## 读写规则

| 角色 | 能读什么 | 能写什么 |
|---|---|---|
| 主 harness | 全部 | 全部 |
| worker | 自己的 task node、允许的 context pack、允许的 file/artifact | 只能写自己的 output/proposal |
| verifier | worker 输出、证据文件、必要控制信息 | verifier result / accepted facts |
| router | 当前任务元数据，以及 History 提供的受控能力画像摘要 | worker node / routing decision |

关键规则：

**worker 不直接写 shared facts，也不直接提交真实文件修改。**

worker 只能 propose：

```text
proposed fact
proposed patch
progress event
final result
```

由 verifier / main harness 决定是否 commit。

## 文件锁

第一版不要做复杂锁。

最简单策略：

1. worker 默认 read-only。
2. 如果需要改文件，worker 生成 patch proposal。
3. orchestrator 检查该文件是否已有未处理 patch。
4. 如果没有冲突，再由主 harness 或 verifier 应用。

也就是说第一版只需要：

```text
read
patch_proposal
```

暂时不做 worker 直接 write lock。

## 运行模式

### Inline Mode

适合一个 worker 的简单任务。

```text
不创建真实 top node
创建 worker result
记录 token ledger
记录 verifier result
```

这是当前实现最接近的模式。

### Graph Mode

适合多个 worker 或长任务。

```text
worker nodes
context packs
artifact/file nodes
edges
patch proposals
verification events
```

以后复杂自动路由走这个模式。

## 和双轨 Memory 的关系

双轨 memory 仍然保留，但它变成这个图的两个视图：

```text
Shared Task Memory
  = worker task nodes
  + verified facts
  + routing / verifier status

Artifact Memory
  = context packs
  + file/artifact nodes
  + raw outputs
  + patch proposals
```

所以最终不是“双轨 vs 图”，而是：

**双轨是概念分类，图是实现结构。**

## 最小实现

第一版只需要四张表：

```text
nodes
edges
worker_events
file_locks
```

### nodes

保存 worker task、context pack、artifact/file。

字段：

```text
id
run_id
kind: control / worker_task / context_pack / artifact
title
summary
body_path
visibility
status
owner
created_at
updated_at
```

### edges

保存节点关系。

字段：

```text
src_node_id
dst_node_id
edge_type
metadata_json
```

### worker_events

保存 worker 的 append-only 输出。

字段：

```text
worker_node_id
event_type: progress / proposed_fact / proposed_patch / final / error
payload_json
verifier_status
committed
created_at
```

### file_locks

第一版只记录 read 和 patch proposal。

字段：

```text
artifact_node_id
worker_node_id
lock_type: read / patch_proposal
base_hash
status
expires_at
```

## 与 Execution History 的连接

Shared Memory 只向 History 提交稳定引用和结构化终态：

```text
task/node id
artifact reference and provenance
verified outcome
failure attribution
token and latency
```

历史原始内容不会自动成为新任务的 Context Pack。只有 Decompose/Application 明确选择某条已验证历史结论时，才将其摘要复制或引用为当前任务的 Context Pack；worker 不能自由遍历跨任务历史。

## 当前实现与下一步

当前 `c4harness run` 已经能把 worker、artifact、事件和 verifier 结果写入图结构。下一步不是继续把所有持久化都塞入这些表，而是收紧边界：

1. `nodes/edges/worker_events/file_locks` 只表达当前任务协作图。
2. Decompose 的 contract graph plan snapshot 迁到独立 History repository。
3. `runs/subtasks` 中的历史调用逐步由 History facade 接管。
4. Shared Memory 与 History 通过 task/node/artifact id 关联，不共享 worker 可见性。
5. 保持旧 SQLite 读取兼容，完成迁移前不破坏 Dashboard。

这就是 multi-harness task router 的最小 Shared Memory 协议；跨任务学习与统计不属于本文。
