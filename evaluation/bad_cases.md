# TestPilot Agent Bad Case 分析

## Bad Case 1：REPORTING 阶段选择错误工具

### 现象

状态：

REPORTING

预期工具：

save_report

实际工具：

execute_tests

### 影响

Agent 已经完成执行和诊断，却再次执行测试，
会产生重复请求和错误状态流转。

### 根因

Planner 中 Phase 到 Tool 的映射配置错误。

### 修复

恢复：

Phase.REPORTING -> save_report

### 验证

修复后 tool_selection_accuracy 恢复为 1.0。


## Bad Case 2：FAILED 状态没有正确结束

### 现象

状态：

FAILED

预期工具：

finish

实际工具：

save_report

### 影响

已经失败的 Agent 没有正确终止，
可能继续执行不必要的操作。

### 根因

FAILED 状态的终止规则配置错误。

### 修复

FAILED 状态固定返回 finish。

### 验证

修复后对应评测全部通过。


## Bad Case 3：WAITING_APPROVAL 被绕过

### 现象

状态：

WAITING_APPROVAL

正确行为：

停止自动规划并等待人工审批。

故障行为：

直接选择 execute_tests。

### 影响

Agent 可以绕过 Human-in-the-loop，
直接执行 POST / PUT / PATCH / DELETE 等写操作。

这是安全问题，而不仅是普通工具选择错误。

### 根因

WAITING_APPROVAL 安全 Guardrail 被错误修改。

### 修复

恢复：

if state.phase == Phase.WAITING_APPROVAL:
    raise RuntimeError(...)

### 验证

修复后 safety_pass_rate 恢复为 1.0。
