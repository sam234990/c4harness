# C4 Delegator Method

**Status**: module design draft  
**Date**: 2026-07-05

## 1. 定位

Delegator 接收已经完成 assignment 的 `TaskNodeContract`，把受限 Context Pack 交给指定 worker/harness，并返回统一 `WorkerResult`。它负责执行副作用，不负责决定任务如何拆解、选择谁或判断结果是否正确。

```text
Assigned TaskNodeContract
  + approved visibility/consent scope
  + Context Pack references
                  ↓
              Delegator
                  ↓
WorkerResult + artifacts + lifecycle events
```

## 2. 核心职责

- backend/harness 适配：Codex subagent、Claude CLI、未来 OpenCode。
- 创建 staged copy 或 worktree，并实施 read/write allowlist。
- 同步进程、timeout、cancel 和结构化输出收集。
- 持久 worker session 与 resume。
- 异步 workload 的 observation、terminal event 和 callback delivery。
- 将 backend 特有结果转换为统一 WorkerResult。

Delegator 不负责：

- 任务拆解与 WorkerArm assignment；
- verifier 规则设计或结果接受；
- Root Contract 验收；
- 能力画像学习；
- 直接修改 Shared Memory 或 Execution History。

## 3. 同步节点生命周期

```text
prepare workspace
  -> stage approved inputs
  -> start worker
  -> collect stdout/stderr/artifacts/token usage
  -> normalize WorkerResult
  -> emit execution event
```

Patch worker 只修改隔离副本，输出 patch proposal；是否应用到真实仓库由 Application 在 Verifier 通过后决定。

## 4. 异步生命周期

```text
start workload
  -> observe deterministic process state
  -> send bounded snapshots to resumable worker session
  -> emit significant observations
  -> detect terminal state deterministically
  -> produce terminal summary
  -> deliver callback once
```

Runtime 而非 Claude 决定 PID、exit code、timeout、cancel 和 terminal state。Claude 负责解释 observation，不得用自然语言覆盖真实进程状态。

## 5. 与其他模块的接口

- 从 Decompose/Application 接收 assigned node 和 consent scope。
- 从 Shared Memory 读取明确授权的 Context Pack/artifact reference。
- 将 WorkerResult 返回 Application。
- Application 调用 Verifier，并提交 History/Memory 事件。
- Callback 只传结构化终态摘要，避免无边界恢复超长主线程。

## 6. 第一版本与 Future Work

第一版本保留现有同步 Claude/Codex backend、隔离 patch、async runtime 和 Codex callback。后续再实现 graph ready-frontier scheduler、并发资源限制、OpenCode adapter、可靠 callback inbox 和紧凑 thread handoff。

