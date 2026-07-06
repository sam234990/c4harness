# C4 Execution History and Capability Evidence

**Status**: method boundary draft  
**Date**: 2026-07-05

## 1. 定位

Execution History 保存跨任务、append-only 的执行事实，用于审计、Dashboard、评估和后续 worker assignment。它不是 worker 在一次任务中共享上下文的 Memory。

必须区分：

```text
Shared Task Memory
  单次任务内的当前协作状态
  Worker Task / Context Pack / Artifact / visibility / file lock

Execution History
  跨任务的已发生事实
  plan snapshot / route / outcome / verification / failure / token / latency
```

两者可以暂时使用同一个 SQLite 文件，但必须由不同 repository 管理，使用不同表和生命周期。共享物理数据库不代表它们属于同一种方法。

## 2. 为什么不能塞进 Shared Memory

Shared Memory 面向正在执行的任务，强调最小可见性、按需读取和协作修改。Execution History 面向未来任务，强调不可变事实、版本、归因和统计。

把两者混在同一张节点图中会产生问题：

- worker 可能读到与当前任务无关的历史私有内容；
- 当前任务的节点更新可能覆盖历史事实；
- Decompose 难以区分“当前上下文”与“历史能力证据”；
- 清理一次任务的 staged artifact 可能误删长期统计；
- Dashboard 查询和 worker 可见性规则互相干扰。

因此，Task Contract Graph 的历史版本应保存为计划快照或专用 plan tables，而不是伪装成 Context Pack/Artifact 节点。

## 3. 记录对象

```text
ExecutionHistoryRecord
  task_id
  parent_task_id
  source_thread_id
  plan_version
  plan_snapshot
  node_id
  worker_arm_id
  route_reason
  started_at / finished_at
  outcome: success | failed | inconclusive | blocked | cancelled
  verification_outcome
  failure_attribution
  input/output/total_tokens
  latency
  artifact_references[]
  user_feedback
```

原始结果不可被能力画像覆盖。画像是从历史事实派生的 read model，可以重建。

## 4. Failure Attribution

至少区分：

- `worker_error`
- `decomposition_error`
- `assignment_error`
- `missing_context`
- `verification_inconclusive`
- `environment_failure`
- `permission_blocked`
- `consent_scope_changed`
- `integration_conflict`

只有经过验证、且归因允许的 outcome 才能更新 worker capability evidence。环境错误和宿主策略阻断不能惩罚 worker。

## 5. Capability Evidence

Decompose 不直接读取所有历史原文，而读取按 WorkerArm、任务维度和项目范围聚合的证据：

```text
CapabilityProfile
  worker_arm_id
  capability_dimension
  verified_successes
  verified_failures
  inconclusive_count
  sample_count
  rework_rate
  escalation_rate
  token_distribution
  latency_distribution
  model_version
  last_updated_at
```

第一版只展示计数和经验比例；Future Work 再引入 Bayesian posterior、时间衰减或 contextual bandit。

## 6. 写入与读取边界

- Application 在计划产生、节点结束、验证结束和主任务结束时提交历史事件。
- Delegator、Verifier 和 Decompose 不直接写 History 数据库。
- Usage recorder 从同一结构化事件提取 Token 和延迟。
- Dashboard 只读查询，不修改原始 outcome。
- Decompose 只读取受控的 capability profile 摘要。
- Shared Memory 中的 raw artifact 只以稳定引用进入 History，不自动复制完整正文。

## 7. 当前实现状态

当前 `MemoryStore` 的 `runs`、`subtasks` 和 usage 字段已经承担部分 Execution History 功能；`record_decomposition()` 还把 Task Contract Graph 写入 Shared Memory 的 `nodes/edges` 表。这是过渡实现，不是最终方法边界。

后续兼容迁移应当：

1. 保留旧表读取，避免 Dashboard 和已有账本失效。
2. 新增独立 `HistoryRepository` 与 plan/outcome schema。
3. 由 Application 双写或迁移旧记录。
4. 验证查询一致后，停止将 contract graph 写入 Shared Memory nodes。
5. Shared Memory 只保留当前任务的 context/artifact graph。

