# C4 Verifier Method

**Status**: first deterministic implementation available
**Date**: 2026-07-07

## 1. 定位

Verifier 执行 Decompose 预先生成的 `VerifierPlan`，根据真实 artifact、文件和运行环境证据判断节点结果。它不选择 worker，也不启动承担原任务的 worker。

```text
TaskNodeContract + VerifierPlan + WorkerResult + artifacts
                         ↓
                      Verifier
                         ↓
VerificationOutcome + evidence + failure attribution
```

## 2. 验证层级

按成本从低到高执行：

1. **Structural**：输出存在、格式完整、必需字段和 artifact 可读取。
2. **Policy**：读取/写入范围、secret、sandbox、consent scope 未越界。
3. **Grounding**：结论能对应到真实文件、日志或命令证据。
4. **Executable**：patch apply、syntax、lint、test、build。
5. **Semantic**：开放式质量、架构一致性或模型辅助评审。
6. **Integration**：跨节点结果、patch 冲突和组合一致性。
7. **Root**：所有 required requirement 与 Root Contract 是否满足。

确定性验证优先；模型评审不能覆盖失败的确定性检查。

## 3. 结果状态

```text
accepted
rejected
inconclusive
blocked
```

`inconclusive` 表示证据不足或验证器能力不足，不等同于 worker 错误。`blocked` 表示环境、权限或宿主策略阻止了验证。

## 4. Failure Attribution

Verifier 提供证据化信号，Application 汇总最终归因。需要区分 worker 输出错误、节点契约错误、上下文不足、环境失败、权限阻断和集成冲突，避免错误更新 worker 画像。

## 5. Root Verification

Root Verifier 检查：

- Requirement Ledger 是否完整覆盖；
- constraint 与禁止事项是否满足；
- 多节点 artifact 是否一致；
- 必须测试、构建和人工检查是否完成；
- 是否仍有关键结论只有 worker 自报；
- 外部调用是否未超出批准范围。

Root Verifier 输出验收证据；最终向用户报告和是否继续执行由 Application 决定。

## 6. 第一版本与 Future Work

第一版本已经实现 contract-aware 节点验证、受限确定性模板执行、`accepted/rejected/inconclusive/blocked` 语义、失败归因以及 Root Contract coverage/traceability。无法由本地确定性证据证明的 semantic criterion 必须由 Codex/人工 reviewer 显式决定，不能自动通过。

Future Work 包括 semantic reviewer、verifier ensemble、差异测试、复杂 patch integration、更精确的 artifact ownership/冲突模型和更可靠的 failure attribution。
