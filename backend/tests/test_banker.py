"""银行家算法测试：安全性判定、安全序列、资源请求三步判定、快照不变量。

教材标准用例（Silberschatz《操作系统概念》）：
    Available = (3,3,2)
    Max        = P0(7,5,3) P1(3,2,2) P2(9,0,2) P3(2,2,2) P4(4,3,3)
    Allocation = P0(0,1,0) P1(2,0,0) P2(3,0,2) P3(2,1,1) P4(0,0,2)
    Need       = Max - Allocation
    安全序列   = P1 → P3 → P4 → P0 → P2
    P1 请求 (1,0,2) → 批准；P4 请求 (3,3,0) → 拒绝（不安全，需回滚等待）
"""

from __future__ import annotations

import pytest

from app.engine.banker import (
    BankerInputError,
    check_safety_trace,
    compute_need,
    prepare_state,
    request_resource_trace,
)

AVAILABLE = [3, 3, 2]
MAX_MATRIX = [[7, 5, 3], [3, 2, 2], [9, 0, 2], [2, 2, 2], [4, 3, 3]]
ALLOCATION = [[0, 1, 0], [2, 0, 0], [3, 0, 2], [2, 1, 1], [0, 0, 2]]
TEXTBOOK_NEED = [[7, 4, 3], [1, 2, 2], [6, 0, 0], [0, 1, 1], [4, 3, 1]]
UNSAFE_AVAILABLE = [0, 0]
UNSAFE_MAX = [[1, 1], [1, 1]]
UNSAFE_ALLOCATION = [[1, 0], [0, 1]]


# ---------------- 输入校验 ----------------


def test_compute_need_is_max_minus_allocation() -> None:
    assert compute_need(MAX_MATRIX, ALLOCATION) == TEXTBOOK_NEED


def test_prepare_state_normalizes_and_names_resources() -> None:
    state = prepare_state(AVAILABLE, MAX_MATRIX, ALLOCATION)
    assert state["processCount"] == 5
    assert state["resourceCount"] == 3
    assert state["processNames"] == ["P0", "P1", "P2", "P3", "P4"]
    assert state["resourceNames"] == ["A", "B", "C"]
    assert state["needMatrix"] == TEXTBOOK_NEED


def test_prepare_state_rejects_inconsistent_need_matrix() -> None:
    wrong = [[0, 0, 0]] * 5
    with pytest.raises(BankerInputError, match="Need"):
        prepare_state(AVAILABLE, MAX_MATRIX, ALLOCATION, need_matrix=wrong)


def test_prepare_state_rejects_allocation_larger_than_max() -> None:
    bad_allocation = [[9, 1, 0], *ALLOCATION[1:]]
    with pytest.raises(BankerInputError):
        prepare_state(AVAILABLE, MAX_MATRIX, bad_allocation)


@pytest.mark.parametrize(
    "available,max_matrix,allocation",
    [
        ([3, 3], MAX_MATRIX, ALLOCATION),  # Available 维度不符
        ([3, 3, 2], [[1, 2, 3], [1, 2]], ALLOCATION),  # Max 行宽不一致
        ([3, 3, 2], [[1, 2, 3]] * 11, [[1, 2, 3]] * 11),  # 超过 10 进程
        ([3, 3, 2], [[1, 2, 3, 4, 5, 6, 7]] * 2, [[0] * 7] * 2),  # 超过 6 类资源
        ([3, 3, 2], [[100, 0, 0]] * 2, [[0, 0, 0]] * 2),  # 数值超过 99
    ],
)
def test_prepare_state_rejects_out_of_contract_shapes(available, max_matrix, allocation) -> None:
    with pytest.raises(BankerInputError):
        prepare_state(available, max_matrix, allocation)


# ---------------- 安全性判定 ----------------


def test_textbook_case_is_safe_with_expected_sequence() -> None:
    result = check_safety_trace(AVAILABLE, MAX_MATRIX, ALLOCATION)
    assert result["isSafe"] is True
    assert result["safeSequence"] == ["P1", "P3", "P4", "P0", "P2"]
    assert result["unfinishedProcesses"] == []
    assert result["state"]["needMatrix"] == TEXTBOOK_NEED


def test_textbook_case_trace_work_and_finish_invariants() -> None:
    trace = check_safety_trace(AVAILABLE, MAX_MATRIX, ALLOCATION)["trace"]
    assert trace["algorithmId"] == "banker-safety"
    assert trace["totalSteps"] >= 2

    allocations = {f"P{i}": ALLOCATION[i] for i in range(5)}
    for step in trace["steps"]:
        snapshot = step["snapshot"]
        rows, cols = len(MAX_MATRIX), 3
        assert len(snapshot["finish"]) == rows
        # 安全序列长度必须等于已完成进程数
        assert len(snapshot["safeSequence"]) == sum(1 for flag in snapshot["finish"] if flag)
        assert len(snapshot["work"]) == cols
        # Work == Available + Σ(已完成进程的 Allocation)
        expected_work = [
            AVAILABLE[j] + sum(allocations[name][j] for name in snapshot["safeSequence"]) for j in range(cols)
        ]
        assert snapshot["work"] == expected_work
        if snapshot["phase"] == "COMPLETE":
            assert snapshot["satisfied"] is True
            assert snapshot["workAfter"] == snapshot["work"]
            assert all(snapshot["need"][j] <= snapshot["workBefore"][j] for j in range(cols))
        if snapshot["phase"] == "SKIP":
            assert snapshot["satisfied"] is False
            assert any(snapshot["need"][j] > snapshot["workBefore"][j] for j in range(cols))

    final = trace["steps"][-1]["snapshot"]
    assert final["phase"] == "FINAL"
    assert final["isSafe"] is True
    assert final["safeSequence"] == ["P1", "P3", "P4", "P0", "P2"]
    assert all(final["finish"])
    assert trace["steps"][-1]["eventTone"] == "SUCCESS"


def test_unsafe_state_is_detected_and_no_sequence_returned() -> None:
    result = check_safety_trace(UNSAFE_AVAILABLE, UNSAFE_MAX, UNSAFE_ALLOCATION)
    assert result["isSafe"] is False
    assert result["safeSequence"] == []
    assert sorted(result["unfinishedProcesses"]) == ["P0", "P1"]
    assert result["trace"]["steps"][-1]["eventTone"] == "DANGER"
    logs = result["trace"]["steps"][-1]["logs"]
    assert any("不安全" in entry["message"] for entry in logs)


def test_partially_satisfiable_state_reports_unfinished_processes() -> None:
    available = [1, 0]
    maximum = [[1, 1], [2, 0]]
    allocation = [[0, 0], [1, 0]]
    result = check_safety_trace(available, maximum, allocation)
    # P0 的 Need=(1,1) 不可满足（B 资源为 0），P1 的 Need=(1,0) 可满足
    assert result["isSafe"] is False
    assert result["safeSequence"] == []
    assert result["unfinishedProcesses"] == ["P0"]


def test_empty_available_but_zero_need_is_safe() -> None:
    result = check_safety_trace([0, 0], [[1, 1], [2, 2]], [[1, 1], [2, 2]])
    assert result["isSafe"] is True
    assert result["safeSequence"] == ["P0", "P1"]


# ---------------- 资源请求判定 ----------------


def test_textbook_request_p1_is_granted() -> None:
    result = request_resource_trace(1, [1, 0, 2], AVAILABLE, MAX_MATRIX, ALLOCATION)
    assert result["granted"] is True
    assert result["checkNeed"] is True
    assert result["checkAvailable"] is True
    assert result["isSafeAfterTentative"] is True
    assert result["safeSequence"]
    assert result["resultingAvailable"] == [2, 3, 0]
    assert result["resultingAllocation"] == [3, 0, 2]
    assert result["resultingNeed"] == [0, 2, 0]

    trace = result["trace"]
    assert trace["algorithmId"] == "banker-request"
    phases = [step["snapshot"]["phase"] for step in trace["steps"]]
    assert phases[0] == "REQUEST"
    assert "CHECK_NEED" in phases and "CHECK_AVAILABLE" in phases and "TENTATIVE" in phases
    assert phases[-1] == "GRANT"
    assert trace["steps"][-1]["eventTone"] == "SUCCESS"
    # 试探状态的步骤必须带 [试探状态] 前缀，保证前端日志能区分"假想分配"与"真实提交"
    assert any(step["title"].startswith("[试探状态]") for step in trace["steps"])


def test_textbook_request_p4_is_denied_and_rolled_back() -> None:
    result = request_resource_trace(4, [3, 3, 0], AVAILABLE, MAX_MATRIX, ALLOCATION)
    assert result["granted"] is False
    assert result["checkNeed"] is True
    assert result["checkAvailable"] is True
    assert result["isSafeAfterTentative"] is False
    assert "不安全" in result["reason"] or "回滚" in result["reason"]
    assert result["safeSequence"] == []

    trace = result["trace"]
    phases = [step["snapshot"]["phase"] for step in trace["steps"]]
    assert phases[-1] == "ROLLBACK"
    final = trace["steps"][-1]["snapshot"]
    assert final["rolledBack"] is True
    assert final["granted"] is False
    # 回滚后资源状态必须与请求前的 Available 完全一致
    assert final["available"] == AVAILABLE
    assert trace["steps"][-1]["eventTone"] == "DANGER"


def test_request_exceeding_need_is_rejected_as_illegal() -> None:
    result = request_resource_trace(1, [2, 2, 2], AVAILABLE, MAX_MATRIX, ALLOCATION)
    assert result["granted"] is False
    assert result["checkNeed"] is False
    assert result["checkAvailable"] is None
    assert result["isSafeAfterTentative"] is None
    phases = [step["snapshot"]["phase"] for step in result["trace"]["steps"]]
    assert phases[-1] == "REJECT"
    assert "非法" in result["reason"]


def test_request_exceeding_available_waits_without_state_change() -> None:
    result = request_resource_trace(0, [7, 4, 3], AVAILABLE, MAX_MATRIX, ALLOCATION)
    assert result["granted"] is False
    assert result["checkNeed"] is True
    assert result["checkAvailable"] is False
    assert result["isSafeAfterTentative"] is None
    phases = [step["snapshot"]["phase"] for step in result["trace"]["steps"]]
    assert phases[-1] == "WAIT"
    assert result["trace"]["steps"][-1]["snapshot"]["available"] == AVAILABLE


def test_request_with_zero_vector_is_granted_and_state_unchanged() -> None:
    result = request_resource_trace(2, [0, 0, 0], AVAILABLE, MAX_MATRIX, ALLOCATION)
    assert result["granted"] is True
    assert result["resultingAvailable"] == AVAILABLE
    assert result["resultingAllocation"] == ALLOCATION[2]
    assert result["resultingNeed"] == TEXTBOOK_NEED[2]


@pytest.mark.parametrize("process_index", [-1, 5, 99])
def test_request_rejects_out_of_range_process_index(process_index: int) -> None:
    with pytest.raises(BankerInputError):
        request_resource_trace(process_index, [0, 0, 0], AVAILABLE, MAX_MATRIX, ALLOCATION)


def test_request_rejects_wrong_dimension_vector() -> None:
    with pytest.raises(BankerInputError):
        request_resource_trace(1, [1, 0], AVAILABLE, MAX_MATRIX, ALLOCATION)


def test_every_request_step_is_replayable_with_consistent_available() -> None:
    """每个步骤快照都要能被前端直接回放：结构完整、可 JSON 序列化、资源向量自洽。

    请求阶段的步骤自带 available/request；并入的试探安全性子步骤改带 work，
    因此断言按快照自身的键分别约束，而不是假设所有步骤形状一致。
    """
    import json

    result = request_resource_trace(1, [1, 0, 2], AVAILABLE, MAX_MATRIX, ALLOCATION)
    grant_index = next(
        i
        for i, step in enumerate(result["trace"]["steps"])
        if step["snapshot"]["phase"] == "GRANT"
    )
    for step in result["trace"]["steps"]:
        snapshot = step["snapshot"]
        assert isinstance(snapshot, dict)
        assert "phase" in snapshot
        assert step["description"]
        assert isinstance(step["highlights"], list)
        json.dumps(snapshot)  # 前端回放要求快照可直接序列化
        if "available" in snapshot:
            assert len(snapshot["available"]) == 3
            assert snapshot["process"] == "P1"
            assert snapshot["request"] == [1, 0, 2]
        else:
            # 试探安全性检查子步骤：用 Work/Need 快照
            assert len(snapshot["work"]) == 3
    # GRANT 之前的真实状态不变；GRANT 之后才提交试探结果
    assert result["trace"]["steps"][0]["snapshot"]["available"] == [3, 3, 2]
    assert result["trace"]["steps"][grant_index]["snapshot"]["available"] == [2, 3, 0]
    assert result["trace"]["steps"][-1]["snapshot"]["available"] == [2, 3, 0]
