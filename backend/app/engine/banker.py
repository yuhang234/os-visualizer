"""银行家算法：安全性检查 + 资源请求试探分配。

设计文档第 6 章：
1. 安全性检查（Safety Algorithm）输出安全序列与 Work/Need/Allocation/Finish 演进轨迹。
2. 资源请求算法按 Request <= Need、Request <= Available、试探分配 + 安全性检查 三步判定。
"""

from __future__ import annotations

from typing import Any, Sequence

from .trace import TraceBuilder, log_entry

MAX_PROCESSES = 10
MAX_RESOURCES = 6
MAX_VALUE = 99

RESOURCE_NAMES = ["A", "B", "C", "D", "E", "F"]


class BankerInputError(ValueError):
    """矩阵维度不一致、数值越界或 Max < Allocation。"""


def _validate_matrix(matrix: Sequence[Sequence[int]], name: str, rows: int, cols: int) -> list[list[int]]:
    if len(matrix) != rows:
        raise BankerInputError(f"{name} 矩阵行数应为 {rows}，实际为 {len(matrix)}")
    result: list[list[int]] = []
    for row_index, row in enumerate(matrix):
        if len(row) != cols:
            raise BankerInputError(f"{name} 矩阵第 {row_index} 行列数应为 {cols}，实际为 {len(row)}")
        cleaned: list[int] = []
        for value in row:
            if not isinstance(value, int) or isinstance(value, bool):
                raise BankerInputError(f"{name} 矩阵只能包含整数")
            if value < 0 or value > MAX_VALUE:
                raise BankerInputError(f"{name} 矩阵数值必须在 0~{MAX_VALUE} 之间")
            cleaned.append(value)
        result.append(cleaned)
    return result


def _validate_vector(vector: Sequence[int], name: str, cols: int) -> list[int]:
    if len(vector) != cols:
        raise BankerInputError(f"{name} 向量长度应为 {cols}，实际为 {len(vector)}")
    cleaned: list[int] = []
    for value in vector:
        if not isinstance(value, int) or isinstance(value, bool):
            raise BankerInputError(f"{name} 只能包含整数")
        if value < 0 or value > MAX_VALUE:
            raise BankerInputError(f"{name} 数值必须在 0~{MAX_VALUE} 之间")
        cleaned.append(value)
    return cleaned


def compute_need(max_matrix: Sequence[Sequence[int]], allocation_matrix: Sequence[Sequence[int]]) -> list[list[int]]:
    return [
        [max_matrix[i][j] - allocation_matrix[i][j] for j in range(len(max_matrix[i]))]
        for i in range(len(max_matrix))
    ]


def prepare_state(
    available: Sequence[int],
    max_matrix: Sequence[Sequence[int]],
    allocation_matrix: Sequence[Sequence[int]],
    need_matrix: Sequence[Sequence[int]] | None = None,
) -> dict[str, Any]:
    """校验并规范化银行家算法输入状态，返回带 need 的完整状态字典。"""
    if not max_matrix:
        raise BankerInputError("Max 矩阵不能为空")
    rows = len(max_matrix)
    if rows > MAX_PROCESSES:
        raise BankerInputError(f"进程数不能超过 {MAX_PROCESSES}")
    cols = len(max_matrix[0])
    if cols < 1 or cols > MAX_RESOURCES:
        raise BankerInputError(f"资源种类数必须在 1~{MAX_RESOURCES} 之间")

    max_clean = _validate_matrix(max_matrix, "Max", rows, cols)
    alloc_clean = _validate_matrix(allocation_matrix, "Allocation", rows, cols)
    available_clean = _validate_vector(available, "Available 向量", cols)

    for i in range(rows):
        for j in range(cols):
            if alloc_clean[i][j] > max_clean[i][j]:
                raise BankerInputError(
                    f"Allocation[{i}][{j}]={alloc_clean[i][j]} 大于 Max[{i}][{j}]={max_clean[i][j]}，输入自相矛盾"
                )

    computed_need = compute_need(max_clean, alloc_clean)
    if need_matrix is not None:
        need_clean = _validate_matrix(need_matrix, "Need", rows, cols)
        if need_clean != computed_need:
            raise BankerInputError("传入的 Need 矩阵与 Max - Allocation 不一致")
    need_clean = computed_need

    return {
        "available": available_clean,
        "maxMatrix": max_clean,
        "allocationMatrix": alloc_clean,
        "needMatrix": need_clean,
        "processCount": rows,
        "resourceCount": cols,
        "processNames": [f"P{i}" for i in range(rows)],
        "resourceNames": RESOURCE_NAMES[:cols],
    }


def _safety_rows_to_snapshot(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return rows


def run_safety_check(
    available: Sequence[int],
    max_matrix: Sequence[Sequence[int]],
    allocation_matrix: Sequence[Sequence[int]],
    *,
    builder: TraceBuilder | None = None,
    title_prefix: str = "",
    step_offset: int = 0,
) -> dict[str, Any]:
    """执行安全性检查。

    - 未传入 builder 时，内部自建 TraceBuilder 并返回完整 ExecutionTrace。
    - 传入 builder 时（资源请求场景），把步骤追加进外部轨迹并返回判定结果。
    """
    state = prepare_state(available, max_matrix, allocation_matrix)
    work: list[int] = list(state["available"])
    need: list[list[int]] = state["needMatrix"]
    allocation: list[list[int]] = state["allocationMatrix"]
    processes: list[str] = state["processNames"]
    rows_count = state["processCount"]
    cols = state["resourceCount"]
    finish = [False] * rows_count
    safe_sequence: list[str] = []
    completed_rows: list[dict[str, Any]] = []

    own_builder = builder is None
    if builder is None:
        builder = TraceBuilder(
            "banker-safety",
            "银行家算法安全性检查",
            {
                **state,
                "description": "Work 初始等于 Available；反复寻找满足 Need[i] <= Work 且未完成的进程，"
                "找到后令 Work += Allocation[i] 并标记 Finish[i]=True，直到所有进程完成（安全）或无法推进（死锁）。",
            },
        )
        builder.add_step(
            "初始化",
            f"Work 初始化为 Available = ({', '.join(map(str, work))})，所有进程 Finish = False，安全序列为空。",
            {
                "phase": "INIT",
                "work": list(work),
                "finish": list(finish),
                "safeSequence": [],
                "rows": [],
                "processIndex": None,
                "process": None,
                "satisfied": None,
                "need": None,
                "allocation": None,
                "workBefore": list(work),
                "workAfter": list(work),
                "remainingProcesses": list(processes),
                "isSafe": None,
            },
            highlights=["work"],
            logs=[log_entry("INFO", f"安全性检查开始: {rows_count} 个进程, {cols} 类资源, Available={work}")],
            event_tone="NONE",
        )

    attempts = 0
    while True:
        progressed = False
        for index in range(rows_count):
            if finish[index]:
                continue
            attempts += 1
            work_before = list(work)
            ok = all(need[index][j] <= work[j] for j in range(cols))
            shortfalls = [f"{state['resourceNames'][j]}: 需 {need[index][j]} > 有 {work[j]}" for j in range(cols) if need[index][j] > work[j]]
            if ok:
                work_after = [work[j] + allocation[index][j] for j in range(cols)]
                work = work_after
                finish[index] = True
                safe_sequence.append(processes[index])
                completed_rows.append(
                    {
                        "process": processes[index],
                        "workBefore": work_before,
                        "need": list(need[index]),
                        "allocation": list(allocation[index]),
                        "workAfter": list(work_after),
                        "finish": True,
                    }
                )
                builder.add_step(
                    f"{title_prefix}进程 {processes[index]} 可满足",
                    f"Need[{processes[index]}] = ({', '.join(map(str, need[index]))}) ≤ Work = ({', '.join(map(str, work_before))})，"
                    f"满足条件。进程执行完毕释放资源：Work = ({', '.join(map(str, work_before))}) + "
                    f"Allocation = ({', '.join(map(str, allocation[index]))}) = ({', '.join(map(str, work_after))})，"
                    f"Finish[{processes[index]}] = True，安全序列追加 {processes[index]}。",
                    {
                        "phase": "COMPLETE",
                        "work": list(work_after),
                        "workBefore": work_before,
                        "workAfter": work_after,
                        "finish": list(finish),
                        "safeSequence": list(safe_sequence),
                        "rows": _safety_rows_to_snapshot(completed_rows),
                        "processIndex": index,
                        "process": processes[index],
                        "satisfied": True,
                        "need": list(need[index]),
                        "allocation": list(allocation[index]),
                        "remainingProcesses": [p for i, p in enumerate(processes) if not finish[i]],
                        "isSafe": None,
                    },
                    highlights=[f"process:{processes[index]}", "work"],
                    logs=[
                        log_entry(
                            "SUCCESS",
                            f"进程 {processes[index]}: Need ({', '.join(map(str, need[index]))}) ≤ Work "
                            f"({', '.join(map(str, work_before))}) 成立，标记完成并回收资源",
                        )
                    ],
                    event_tone="SUCCESS",
                )
                progressed = True
            else:
                builder.add_step(
                    f"{title_prefix}进程 {processes[index]} 暂不可满足",
                    f"Need[{processes[index]}] = ({', '.join(map(str, need[index]))}) 与 Work = "
                    f"({', '.join(map(str, work_before))}) 比较不成立（{'；'.join(shortfalls)}），"
                    f"进程 {processes[index]} 本轮跳过，继续检查下一个进程。",
                    {
                        "phase": "SKIP",
                        "work": list(work),
                        "workBefore": work_before,
                        "workAfter": list(work),
                        "finish": list(finish),
                        "safeSequence": list(safe_sequence),
                        "rows": _safety_rows_to_snapshot(completed_rows),
                        "processIndex": index,
                        "process": processes[index],
                        "satisfied": False,
                        "need": list(need[index]),
                        "allocation": list(allocation[index]),
                        "remainingProcesses": [p for i, p in enumerate(processes) if not finish[i]],
                        "isSafe": None,
                    },
                    highlights=[f"process:{processes[index]}"],
                    logs=[
                        log_entry(
                            "WARN",
                            f"进程 {processes[index]}: Need ({', '.join(map(str, need[index]))}) ≤ Work "
                            f"({', '.join(map(str, work_before))}) 不成立，本轮跳过",
                        )
                    ],
                    event_tone="BLOCK",
                )
        if not progressed:
            break

    is_safe = all(finish)
    unfinished = [processes[i] for i in range(rows_count) if not finish[i]]
    final_description = (
        f"所有进程均能完成，系统处于安全状态。安全序列为 ⟨{' → '.join(safe_sequence)}⟩，"
        "按此顺序分配资源不会发生死锁。"
        if is_safe
        else f"存在无法完成的进程 {'、'.join(unfinished)}，系统处于不安全状态："
        "当前剩余资源无法满足任何未完成进程的 Need，继续分配可能进入死锁。"
    )
    builder.add_step(
        "安全性判定完成",
        final_description,
        {
            "phase": "FINAL",
            "work": list(work),
            "workBefore": list(work),
            "workAfter": list(work),
            "finish": list(finish),
            "safeSequence": list(safe_sequence),
            "rows": _safety_rows_to_snapshot(completed_rows),
            "processIndex": None,
            "process": None,
            "satisfied": is_safe,
            "need": None,
            "allocation": None,
            "remainingProcesses": unfinished,
            "isSafe": is_safe,
        },
        highlights=["work", "safe-sequence"],
        logs=[
            log_entry(
                "SUCCESS" if is_safe else "DANGER",
                f"安全性判定: {'安全 (SAFE)' if is_safe else '不安全 (UNSAFE)'}；"
                f"安全序列 = {safe_sequence if is_safe else '不存在'}",
            )
        ],
        event_tone="SUCCESS" if is_safe else "DANGER",
    )

    result = {
        "isSafe": is_safe,
        "safeSequence": safe_sequence if is_safe else [],
        "unfinishedProcesses": unfinished,
        "work": work,
        "finish": finish,
        "attemptCount": attempts,
    }
    if own_builder:
        result["trace"] = builder.build(
            metrics={
                "processCount": rows_count,
                "resourceCount": cols,
                "attemptCount": attempts,
                "safeSequenceLength": len(safe_sequence),
            },
            state=state,
        )
        result["state"] = state
    return result


def check_safety_trace(
    available: Sequence[int],
    max_matrix: Sequence[Sequence[int]],
    allocation_matrix: Sequence[Sequence[int]],
) -> dict[str, Any]:
    """REST 入口：返回 ExecutionTrace 形式的完整安全性检查过程。"""
    result = run_safety_check(available, max_matrix, allocation_matrix)
    return {
        "isSafe": result["isSafe"],
        "safeSequence": result["safeSequence"],
        "unfinishedProcesses": result["unfinishedProcesses"],
        "trace": result["trace"],
        "state": result["state"],
    }


def request_resource_trace(
    process_index: int,
    request_vector: Sequence[int],
    available: Sequence[int],
    max_matrix: Sequence[Sequence[int]],
    allocation_matrix: Sequence[Sequence[int]],
) -> dict[str, Any]:
    """资源请求算法：三步判定 + 试探分配 + 安全性检查，全过程可步进回放。"""
    state = prepare_state(available, max_matrix, allocation_matrix)
    rows_count = state["processCount"]
    cols = state["resourceCount"]
    processes = state["processNames"]
    names = state["resourceNames"]
    if not isinstance(process_index, int) or isinstance(process_index, bool) or not (0 <= process_index < rows_count):
        raise BankerInputError(f"进程下标必须在 0~{rows_count - 1} 之间")
    request = _validate_vector(request_vector, "Request 向量", cols)

    target = processes[process_index]
    need = state["needMatrix"][process_index]
    allocation = state["allocationMatrix"][process_index]
    available_now = list(state["available"])

    builder = TraceBuilder(
        "banker-request",
        f"银行家算法资源请求判定（{target} 申请 {dict(zip(names, request))}）",
        {
            **state,
            "processIndex": process_index,
            "process": target,
            "requestVector": request,
            "description": "Request-Request 算法：先检查 Request ≤ Need，再检查 Request ≤ Available，"
            "然后试探性分配并执行安全性检查；安全则正式分配，不安全则回滚并让进程等待。",
        },
    )

    builder.add_step(
        "提交资源请求",
        f"进程 {target} 提出请求 Request = ({', '.join(map(str, request))})，开始逐步判定。",
        {
            "phase": "REQUEST",
            "process": target,
            "processIndex": process_index,
            "request": request,
            "available": list(available_now),
            "need": list(need),
            "allocation": list(allocation),
            "checkNeed": None,
            "checkAvailable": None,
            "granted": None,
            "rolledBack": False,
        },
        highlights=[f"process:{target}", "request"],
        logs=[log_entry("INFO", f"进程 {target} 请求资源 {dict(zip(names, request))}")],
        event_tone="STEP",
    )

    # 步骤一：Request <= Need
    need_ok = all(request[j] <= need[j] for j in range(cols))
    builder.add_step(
        "检查条件一：Request ≤ Need",
        f"Request = ({', '.join(map(str, request))})，Need[{target}] = ({', '.join(map(str, need))})，"
        + ("条件成立，请求量未超过该进程声明的最大需求。" if need_ok else "条件不成立：请求量超过进程声明的最大需求，属于非法请求，直接拒绝。"),
        {
            "phase": "CHECK_NEED",
            "process": target,
            "processIndex": process_index,
            "request": request,
            "available": list(available_now),
            "need": list(need),
            "allocation": list(allocation),
            "checkNeed": need_ok,
            "checkAvailable": None,
            "granted": None,
            "rolledBack": False,
        },
        highlights=[f"process:{target}", "need", "request"],
        logs=[
            log_entry(
                "SUCCESS" if need_ok else "DANGER",
                f"条件一 Request ≤ Need: {'成立' if need_ok else '不成立（非法请求）'}",
            )
        ],
        event_tone="SUCCESS" if need_ok else "DANGER",
    )

    if not need_ok:
        builder.add_step(
            "请求被拒绝",
            f"Request 超过 Need[{target}]，请求非法，系统拒绝该请求且不改变任何资源状态。",
            {
                "phase": "REJECT",
                "process": target,
                "processIndex": process_index,
                "request": request,
                "available": list(available_now),
                "need": list(need),
                "allocation": list(allocation),
                "checkNeed": False,
                "checkAvailable": None,
                "granted": False,
                "rolledBack": True,
                "reason": "Request 超过 Need，非法请求",
            },
            highlights=[f"process:{target}"],
            logs=[log_entry("DANGER", f"进程 {target} 的请求超过 Need，判定为非法请求")],
            event_tone="DANGER",
        )
        return {
            "granted": False,
            "reason": f"Request 超过 Need[{target}]，请求非法，已拒绝。",
            "checkNeed": False,
            "checkAvailable": None,
            "isSafeAfterTentative": None,
            "safeSequence": [],
            "trace": builder.build(),
            "state": state,
        }

    # 步骤二：Request <= Available
    available_ok = all(request[j] <= available_now[j] for j in range(cols))
    builder.add_step(
        "检查条件二：Request ≤ Available",
        f"Request = ({', '.join(map(str, request))})，Available = ({', '.join(map(str, available_now))})，"
        + ("条件成立，当前系统确有足够空闲资源。" if available_ok else "条件不成立：系统当前空闲资源不足，进程需要等待。"),
        {
            "phase": "CHECK_AVAILABLE",
            "process": target,
            "processIndex": process_index,
            "request": request,
            "available": list(available_now),
            "need": list(need),
            "allocation": list(allocation),
            "checkNeed": True,
            "checkAvailable": available_ok,
            "granted": None,
            "rolledBack": False,
        },
        highlights=[f"process:{target}", "available", "request"],
        logs=[
            log_entry(
                "SUCCESS" if available_ok else "WARN",
                f"条件二 Request ≤ Available: {'成立' if available_ok else '不成立（资源不足，需等待）'}",
            )
        ],
        event_tone="SUCCESS" if available_ok else "BLOCK",
    )

    if not available_ok:
        builder.add_step(
            "进程进入等待",
            f"系统当前空闲资源不足，进程 {target} 本次请求无法立即满足，进入等待队列；"
            "资源状态保持不变，待其他进程释放资源后可重新申请。",
            {
                "phase": "WAIT",
                "process": target,
                "processIndex": process_index,
                "request": request,
                "available": list(available_now),
                "need": list(need),
                "allocation": list(allocation),
                "checkNeed": True,
                "checkAvailable": False,
                "granted": False,
                "rolledBack": True,
                "reason": "Available 不足",
            },
            highlights=[f"process:{target}"],
            logs=[log_entry("WARN", f"进程 {target} 请求的资源超过 Available，进入等待")],
            event_tone="BLOCK",
        )
        return {
            "granted": False,
            "reason": f"Request 超过 Available = ({', '.join(map(str, available_now))})，进程需等待。",
            "checkNeed": True,
            "checkAvailable": False,
            "isSafeAfterTentative": None,
            "safeSequence": [],
            "trace": builder.build(),
            "state": state,
        }

    # 步骤三：试探性分配
    tentative_available = [available_now[j] - request[j] for j in range(cols)]
    tentative_allocation = [row[:] for row in state["allocationMatrix"]]
    tentative_allocation[process_index] = [allocation[j] + request[j] for j in range(cols)]
    tentative_need = [row[:] for row in state["needMatrix"]]
    tentative_need[process_index] = [need[j] - request[j] for j in range(cols)]

    builder.add_step(
        "试探性分配（尚未提交）",
        f"临时令 Available' = ({', '.join(map(str, tentative_available))})，"
        f"Allocation'[{target}] = ({', '.join(map(str, tentative_allocation[process_index]))})，"
        f"Need'[{target}] = ({', '.join(map(str, tentative_need[process_index]))})，随后对该假想状态执行安全性检查。",
        {
            "phase": "TENTATIVE",
            "process": target,
            "processIndex": process_index,
            "request": request,
            "available": tentative_available,
            "availableBefore": list(available_now),
            "need": list(tentative_need[process_index]),
            "allocation": list(tentative_allocation[process_index]),
            "checkNeed": True,
            "checkAvailable": True,
            "granted": None,
            "rolledBack": False,
        },
        highlights=[f"process:{target}", "available", "tentative"],
        logs=[
            log_entry(
                "INFO",
                f"试探分配: Available ({', '.join(map(str, available_now))}) → "
                f"({', '.join(map(str, tentative_available))})",
            )
        ],
        event_tone="STEP",
    )

    # 步骤四：对试探状态执行安全性检查（步骤并入本轨迹）
    safety = run_safety_check(
        tentative_available,
        state["maxMatrix"],
        tentative_allocation,
        builder=builder,
        title_prefix="[试探状态] ",
    )

    if safety["isSafe"]:
        builder.add_step(
            "判定：批准分配",
            f"试探状态安全（安全序列 ⟨{' → '.join(safety['safeSequence'])}⟩），系统正式批准进程 {target} 的请求，"
            "资源状态按试探结果提交。",
            {
                "phase": "GRANT",
                "process": target,
                "processIndex": process_index,
                "request": request,
                "available": tentative_available,
                "availableBefore": list(available_now),
                "need": list(tentative_need[process_index]),
                "allocation": list(tentative_allocation[process_index]),
                "checkNeed": True,
                "checkAvailable": True,
                "granted": True,
                "rolledBack": False,
                "isSafeAfterTentative": True,
                "safeSequence": safety["safeSequence"],
            },
            highlights=[f"process:{target}", "granted", "safe-sequence"],
            logs=[
                log_entry(
                    "SUCCESS",
                    f"判定通过: 试探分配后系统仍安全，正式分配资源给进程 {target}",
                )
            ],
            event_tone="SUCCESS",
        )
        return {
            "granted": True,
            "reason": f"满足条件一与条件二，试探分配后系统仍安全（安全序列 ⟨{' → '.join(safety['safeSequence'])}⟩），批准分配。",
            "checkNeed": True,
            "checkAvailable": True,
            "isSafeAfterTentative": True,
            "safeSequence": safety["safeSequence"],
            "resultingAvailable": tentative_available,
            "resultingAllocation": tentative_allocation[process_index],
            "resultingNeed": tentative_need[process_index],
            "trace": builder.build(),
            "state": state,
        }

    builder.add_step(
        "判定：回滚并等待",
        f"试探分配后系统进入不安全状态（未完成进程 {'、'.join(safety['unfinishedProcesses'])}），"
        f"为避免死锁，系统撤销本次试探分配，资源状态回滚到 ({', '.join(map(str, available_now))})，"
        f"进程 {target} 本次请求失败，需等待。",
        {
            "phase": "ROLLBACK",
            "process": target,
            "processIndex": process_index,
            "request": request,
            "available": list(available_now),
            "availableBefore": list(available_now),
            "need": list(need),
            "allocation": list(allocation),
            "checkNeed": True,
            "checkAvailable": True,
            "granted": False,
            "rolledBack": True,
            "isSafeAfterTentative": False,
            "safeSequence": [],
        },
        highlights=[f"process:{target}", "rollback"],
        logs=[
            log_entry(
                "DANGER",
                f"判定不通过: 试探分配后系统不安全，撤销分配并回滚资源状态，进程 {target} 需等待",
            )
        ],
        event_tone="DANGER",
    )
    return {
        "granted": False,
        "reason": "试探分配后系统进入不安全状态，已回滚，请求被拒绝（进程等待）。",
        "checkNeed": True,
        "checkAvailable": True,
        "isSafeAfterTentative": False,
        "safeSequence": [],
        "trace": builder.build(),
        "state": state,
    }
