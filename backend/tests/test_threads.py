"""多线程生产者-消费者模拟器测试：逐步重放不变量、FIFO 语义、互斥锁争抢与输入校验。

测试策略：不信任模拟器自报的 invariants 字段，而是从步骤快照独立重放整条时间线，
重新推导缓冲区、信号量、互斥锁持有者、等待队列与生产/消费计数器，
再与快照声明值比对（与后端实现解耦的差分校验）。
"""

from __future__ import annotations

import json
from collections import deque

import pytest

from app.engine.threads_simulator import (
    MAX_BUFFER_CAPACITY,
    MAX_TOTAL_OPERATIONS,
    ThreadsInputError,
    simulate_threads,
)

CAPACITIES = (1, 2, 5)
ROLE_PAIRS = ((1, 1), (2, 2), (3, 3), (4, 4), (1, 3), (3, 1), (2, 4), (4, 2))
OPERATIONS = (1, 2, 7, 60)
SEEDS = (0, 42, 20261017)

DEFAULT_CASE = dict(buffer_capacity=5, producer_count=2, consumer_count=2, total_operations=20, seed=20261017)


# ---------------- 独立重放器 ----------------


def replay_trace(trace: dict) -> list[str]:
    """独立重放步骤并返回违规列表（空列表表示完全自洽）。"""
    errors: list[str] = []
    steps = trace["steps"]
    if not steps:
        return ["trace 不含任何步骤"]
    cap = trace["initialState"]["bufferCapacity"]
    produced_order: deque[int] = deque()

    first = steps[0]["snapshot"]
    if first["action"] != "INIT":
        errors.append(f"首步 action={first['action']}，应为 INIT")
    if first["semaphores"] != {"mutex": 1, "empty": cap, "full": 0}:
        errors.append(f"初始信号量异常: {first['semaphores']}")
    if first["bufferCount"] != 0:
        errors.append("初始缓冲区非空")

    prev = first
    for index, step in enumerate(steps):
        snapshot = step["snapshot"]
        where = f"step#{index}({snapshot['action']})"
        semaphores = snapshot["semaphores"]
        buffer = snapshot["bufferState"]
        count = sum(1 for value in buffer if value is not None)

        # 结构完整性
        if not step["title"] or not step["description"]:
            errors.append(f"{where}: 缺少标题或描述")
        if not isinstance(step["highlights"], list) or not step["logs"]:
            errors.append(f"{where}: highlights/logs 结构不完整")
        if snapshot["action"] != "INIT" and snapshot["activeThreadId"] is not None and not any(
            mark.startswith("thread:") for mark in step["highlights"]
        ):
            errors.append(f"{where}: 缺少 thread:<id> 高亮标记")

        # 快照自洽
        if count != snapshot["bufferCount"]:
            errors.append(f"{where}: bufferCount={snapshot['bufferCount']} 与实际 {count} 不符")
        if not 0 <= semaphores["mutex"] <= 1:
            errors.append(f"{where}: mutex={semaphores['mutex']} 越界")
        if semaphores["empty"] < 0 or semaphores["full"] < 0:
            errors.append(f"{where}: 信号量出现负值 {semaphores}")
        if semaphores["empty"] + semaphores["full"] > cap:
            errors.append(f"{where}: empty+full={semaphores['empty'] + semaphores['full']} 超过容量 {cap}")
        if count > cap:
            errors.append(f"{where}: 缓冲区溢出 {count}/{cap}")
        if (semaphores["mutex"] == 0) != (snapshot["mutexOwner"] is not None):
            errors.append(f"{where}: mutex={semaphores['mutex']} 与持有者 {snapshot['mutexOwner']} 矛盾")
        if not 0 <= snapshot["inPointer"] < cap or not 0 <= snapshot["outPointer"] < cap:
            errors.append(f"{where}: 环形指针越界")

        # 单步增量约束（离散事件每步只允许一个单位变化）
        prev_count = sum(1 for value in prev["bufferState"] if value is not None)
        if abs(count - prev_count) > 1:
            errors.append(f"{where}: 缓冲区一步内从 {prev_count} 跳到 {count}")
        for key in ("mutex", "empty", "full"):
            if abs(semaphores[key] - prev["semaphores"][key]) > 1:
                errors.append(f"{where}: {key} 一步内从 {prev['semaphores'][key]} 跳到 {semaphores[key]}")

        action = snapshot["action"]
        active = snapshot["activeThreadId"]

        if action == "INSERT":
            slot = (snapshot["inPointer"] - 1) % cap
            if prev["bufferState"][slot] is not None:
                errors.append(f"{where}: 覆写了非空槽位 {slot}")
            if buffer[slot] is None:
                errors.append(f"{where}: 写入后槽位 {slot} 仍为空")
            else:
                produced_order.append(buffer[slot])
            if snapshot["mutexOwner"] != active:
                errors.append(f"{where}: 未持锁写入（owner={snapshot['mutexOwner']}）")
            if snapshot["activeThreadType"] != "PRODUCER":
                errors.append(f"{where}: 消费者执行了写入")
            if snapshot["activeLine"] != 4:
                errors.append(f"{where}: 生产者写库行号 {snapshot['activeLine']} != 4")

        if action == "REMOVE":
            slot = (snapshot["outPointer"] - 1) % cap
            removed = prev["bufferState"][slot]
            if removed is None:
                errors.append(f"{where}: 从空槽位 {slot} 取出")
            if buffer[slot] is not None:
                errors.append(f"{where}: 取出后槽位 {slot} 仍有产品")
            if snapshot["mutexOwner"] != active:
                errors.append(f"{where}: 未持锁取出（owner={snapshot['mutexOwner']}）")
            if snapshot["activeThreadType"] != "CONSUMER":
                errors.append(f"{where}: 生产者执行了取出")
            if snapshot["activeLine"] != 3:
                errors.append(f"{where}: 消费者取库行号 {snapshot['activeLine']} != 3")
            if not produced_order:
                errors.append(f"{where}: 消费了不存在的产品")
            elif produced_order.popleft() != removed:
                errors.append(f"{where}: 取出顺序违反 FIFO（取出 {removed}，期望 {removed}）")

        if action == "P_MUTEX" and snapshot["mutexOwner"] != active:
            errors.append(f"{where}: P(mutex) 成功但持有者为 {snapshot['mutexOwner']}")
        if action == "V_MUTEX" and snapshot["mutexOwner"] == active:
            errors.append(f"{where}: V(mutex) 后仍持有锁")
        if action == "BLOCK_EMPTY" and semaphores["empty"] != 0:
            errors.append(f"{where}: BLOCK_EMPTY 时 empty={semaphores['empty']}")
        if action == "BLOCK_FULL" and semaphores["full"] != 0:
            errors.append(f"{where}: BLOCK_FULL 时 full={semaphores['full']}")
        if action == "BLOCK_MUTEX" and semaphores["mutex"] != 0:
            errors.append(f"{where}: BLOCK_MUTEX 时 mutex={semaphores['mutex']}")
        # V 操作在存在等待者时直接移交令牌（信号量值不变），此时必然伴随唤醒事件
        if action == "V_FULL" and semaphores["full"] < 1 and snapshot["counters"]["wakeEvents"] <= prev["counters"]["wakeEvents"]:
            errors.append(f"{where}: V(full) 既未加一也未移交")
        if action == "V_EMPTY" and semaphores["empty"] < 1 and snapshot["counters"]["wakeEvents"] <= prev["counters"]["wakeEvents"]:
            errors.append(f"{where}: V(empty) 既未加一也未移交")

        # 等待队列自洽：无重复；队列中的线程必须是 BLOCKED 且阻塞原因匹配
        blocked = {t["id"]: t for t in snapshot["threads"] if t["state"] == "BLOCKED"}
        for queue_name, queue in snapshot["waitQueues"].items():
            if len(set(queue)) != len(queue):
                errors.append(f"{where}: {queue_name} 等待队列出现重复 {queue}")
            for waiter in queue:
                if waiter not in blocked:
                    errors.append(f"{where}: {waiter} 在 {queue_name} 队列中但状态不是 BLOCKED")
                elif blocked[waiter]["blockedOn"] != queue_name:
                    errors.append(f"{where}: {waiter} 阻塞于 {blocked[waiter]['blockedOn']} 却排在 {queue_name} 队列")

        # 线程计数与全局计数一致
        if sum(t["produced"] for t in snapshot["threads"]) != snapshot["counters"]["produced"]:
            errors.append(f"{where}: 线程生产数之和与全局计数不一致")
        if sum(t["consumed"] for t in snapshot["threads"]) != snapshot["counters"]["consumed"]:
            errors.append(f"{where}: 线程消费数之和与全局计数不一致")
        for thread in snapshot["threads"]:
            if thread["opsDone"] > thread["opsQuota"]:
                errors.append(f"{where}: {thread['id']} 完成数超过配额")
            if thread["state"] == "DONE" and thread["opsDone"] != thread["opsQuota"]:
                errors.append(f"{where}: {thread['id']} 标记 DONE 但未完成配额")

        prev = snapshot

    metrics = trace["metrics"]
    if metrics["produced"] - metrics["consumed"] != metrics["bufferRemaining"]:
        errors.append("最终 生产-消费 != 缓冲区残留")
    if len(produced_order) != metrics["bufferRemaining"]:
        errors.append(f"FIFO 队列剩余 {len(produced_order)} != 残留 {metrics['bufferRemaining']}")
    if any(not value for value in trace["invariants"].values()):
        errors.append(f"模拟器自报不变量为假: {trace['invariants']}")
    return errors


def strip_wallclock(trace: dict) -> str:
    """剔除创建时间与日志时间戳后序列化，用于比较调度是否可复现。"""
    clone = json.loads(json.dumps(trace))
    clone.pop("createdAt", None)
    for step in clone["steps"]:
        for entry in step["logs"]:
            entry.pop("timestamp", None)
    return json.dumps(clone, sort_keys=True, ensure_ascii=False)


# ---------------- 差分重放：全部参数组合都不变量成立 ----------------


@pytest.mark.parametrize("capacity", CAPACITIES)
@pytest.mark.parametrize("producers,consumers", ROLE_PAIRS)
@pytest.mark.parametrize("operations", OPERATIONS)
def test_replayed_invariants_hold_across_parameter_matrix(
    capacity: int, producers: int, consumers: int, operations: int
) -> None:
    for seed in SEEDS:
        trace = simulate_threads(capacity, producers, consumers, operations, seed=seed)
        errors = replay_trace(trace)
        assert not errors, f"cap={capacity} P={producers} C={consumers} ops={operations} seed={seed}: {errors}"


# ---------------- 终止性与配额守恒 ----------------


@pytest.mark.parametrize("capacity", (1, 3, 7))
@pytest.mark.parametrize("roles", (1, 2, 3, 4))
@pytest.mark.parametrize("operations", (1, 3, 12, 60))
def test_balanced_roles_drain_the_buffer_without_deadlock(capacity: int, roles: int, operations: int) -> None:
    trace = simulate_threads(capacity, roles, roles, operations, seed=7)
    metrics = trace["metrics"]
    threads = trace["initialState"]["threads"]
    producer_demand = sum(t["opsQuota"] for t in threads if t["type"] == "PRODUCER")
    consumer_demand = sum(t["opsQuota"] for t in threads if t["type"] == "CONSUMER")
    # 每个线程至少 1 次操作，因此两侧需求相同且不小于请求的操作数
    assert producer_demand == consumer_demand >= operations
    assert metrics["produced"] == producer_demand
    assert metrics["consumed"] == consumer_demand
    assert metrics["bufferRemaining"] == 0
    assert metrics["blockedThreads"] == []
    assert len(metrics["completedThreads"]) == roles * 2
    assert metrics["truncated"] is False
    assert trace["steps"][-1]["snapshot"]["action"] == "FINISH"
    # 所有产品悉数消费，FIFO 队列必须清空
    assert not replay_trace(trace)


@pytest.mark.parametrize(
    "producers,consumers",
    ((1, 3), (1, 4), (3, 1), (4, 2), (2, 4)),
)
def test_under_supplied_roles_only_leave_the_scarce_side_blocked(producers: int, consumers: int) -> None:
    """生产者/消费者数量不等时，需求多的一方可能永久阻塞 —— 属于建模预期而非死锁。"""
    operations = 3
    trace = simulate_threads(3, producers, consumers, operations, seed=11)
    metrics = trace["metrics"]
    threads = trace["initialState"]["threads"]
    producer_demand = sum(t["opsQuota"] for t in threads if t["type"] == "PRODUCER")
    consumer_demand = sum(t["opsQuota"] for t in threads if t["type"] == "CONSUMER")
    assert producer_demand >= operations and consumer_demand >= operations  # 每个线程至少 1 次操作
    assert metrics["produced"] == producer_demand
    assert metrics["consumed"] == min(producer_demand, consumer_demand)
    assert metrics["produced"] - metrics["consumed"] == metrics["bufferRemaining"]
    blocked = set(metrics["blockedThreads"])
    if consumer_demand > producer_demand:
        assert blocked and all(tid.startswith("C") for tid in blocked), "缺货时只应留下消费者"
    else:
        assert not blocked, "货源充足时不应有线程永久阻塞"
    assert not replay_trace(trace)


def test_max_scale_case_stays_within_step_budget() -> None:
    trace = simulate_threads(
        MAX_BUFFER_CAPACITY, 4, 4, MAX_TOTAL_OPERATIONS, seed=20261017
    )
    metrics = trace["metrics"]
    assert metrics["truncated"] is False
    assert trace["totalSteps"] < 5000
    assert metrics["produced"] == metrics["consumed"] == MAX_TOTAL_OPERATIONS
    assert metrics["blockedThreads"] == []


# ---------------- 互斥锁争抢与信号量阻塞的可观察性 ----------------


def test_default_preset_shows_both_mutex_contention_and_semaphore_blocking() -> None:
    """设计文档 Phase 2 验收：多线程需直观展现互斥锁争抢与信号量阻塞。"""
    trace = simulate_threads(**DEFAULT_CASE)
    actions = {step["snapshot"]["action"] for step in trace["steps"]}
    assert "BLOCK_MUTEX" in actions, "未出现互斥锁争抢，无法演示 P(mutex) 阻塞"
    assert "BLOCK_EMPTY" in actions or "BLOCK_FULL" in actions, "未出现信号量阻塞"
    assert trace["metrics"]["mutexBlockEvents"] > 0
    assert trace["metrics"]["wakeEvents"] > 0


def test_mutex_is_held_by_at_most_one_thread_and_released_after_hold_window() -> None:
    """临界区持有窗口：写/取之后仍持锁一段时间，期间其他线程 P(mutex) 必然阻塞。"""
    trace = simulate_threads(5, 3, 3, 12, seed=3, critical_time=0.5)
    assert trace["metrics"]["mutexBlockEvents"] > 0
    mutex_holders: set[str] = set()
    steps = trace["steps"]
    for index, step in enumerate(steps):
        snapshot = step["snapshot"]
        if snapshot["action"] == "BLOCK_MUTEX":
            owner = snapshot["mutexOwner"]
            assert owner is not None and owner != snapshot["activeThreadId"]
            mutex_holders.add(owner)
            assert snapshot["semaphores"]["mutex"] == 0
    # 持锁者在下一次被调度时必须走出临界区（不会永久持锁）
    assert not replay_trace(trace)


def test_zero_critical_time_disables_contention_window() -> None:
    """critical_time=0 时临界区不跨调度量子，退化为原子临界区（无 BLOCK_MUTEX）。"""
    trace = simulate_threads(3, 3, 3, 9, seed=5, critical_time=0.0)
    actions = [step["snapshot"]["action"] for step in trace["steps"]]
    assert "BLOCK_MUTEX" not in actions
    assert trace["metrics"]["mutexBlockEvents"] == 0
    assert not replay_trace(trace)


def test_threads_experience_blocking_and_waking_with_matching_counters() -> None:
    trace = simulate_threads(**DEFAULT_CASE)
    final = trace["steps"][-1]["snapshot"]
    for thread in final["threads"]:
        assert thread["waitEvents"] == thread["wakeEvents"] or thread["state"] != "DONE"
        if thread["state"] == "DONE":
            assert thread["wakeEvents"] <= thread["waitEvents"]
    counters = final["counters"]
    assert counters["blockEvents"] >= counters["wakeEvents"]
    assert counters["contextSwitches"] > 0
    assert not replay_trace(trace)


# ---------------- 确定性 ----------------


def test_same_seed_reproduces_identical_schedule() -> None:
    first = strip_wallclock(simulate_threads(**DEFAULT_CASE))
    second = strip_wallclock(simulate_threads(**DEFAULT_CASE))
    assert first == second


def test_different_seeds_produce_different_schedules() -> None:
    baseline = strip_wallclock(simulate_threads(**DEFAULT_CASE))
    other = strip_wallclock(simulate_threads(**{**DEFAULT_CASE, "seed": 4242}))
    assert baseline != other


# ---------------- 输入校验 ----------------


@pytest.mark.parametrize(
    "kwargs",
    [
        {"buffer_capacity": 0},
        {"buffer_capacity": MAX_BUFFER_CAPACITY + 1},
        {"producer_count": 0},
        {"producer_count": 5},
        {"consumer_count": 0},
        {"consumer_count": 5},
        {"total_operations": 0},
        {"total_operations": MAX_TOTAL_OPERATIONS + 1},
        {"production_time": 0.0},
        {"consumption_time": -1.0},
        {"critical_time": -0.1},
    ],
)
def test_invalid_inputs_are_rejected(kwargs: dict) -> None:
    params = {**DEFAULT_CASE, **kwargs}
    with pytest.raises(ThreadsInputError):
        simulate_threads(**params)


# ---------------- 轨迹结构与教学内容 ----------------


def test_trace_structure_and_pseudocode_line_mapping() -> None:
    trace = simulate_threads(**DEFAULT_CASE)
    assert trace["algorithmId"] == "threads-pc"
    assert trace["totalSteps"] == len(trace["steps"])
    assert trace["initialState"]["producerCode"] == [
        "item = produce_item();",
        "P(empty); // 等待空槽位",
        "P(mutex); // 抢占互斥锁",
        "insert_item(item); // 写入缓冲区",
        "V(mutex); // 释放互斥锁",
        "V(full); // 唤醒消费者",
    ]
    assert trace["initialState"]["consumerCode"][0] == "P(full); // 检查是否有产品"
    line_expectations = {
        # 动作 → (生产者行号, 消费者行号)；None 表示该角色不会出现此动作
        "PRODUCE": (1, None),
        "P_EMPTY": (2, None),
        "P_FULL": (None, 1),
        "P_MUTEX": (3, 2),
        "INSERT": (4, None),
        "REMOVE": (None, 3),
        "V_MUTEX": (5, 4),
        "V_FULL": (6, None),
        "V_EMPTY": (None, 5),
        "CONSUME": (None, 6),
        "BLOCK_EMPTY": (2, None),
        "BLOCK_FULL": (None, 1),
        "BLOCK_MUTEX": (3, 2),
    }
    for step in trace["steps"]:
        snapshot = step["snapshot"]
        action = snapshot["action"]
        if action in line_expectations:
            producer_line, consumer_line = line_expectations[action]
            expected = producer_line if snapshot["activeThreadType"] == "PRODUCER" else consumer_line
            assert expected is not None, f"{action} 不应由 {snapshot['activeThreadType']} 执行"
            assert snapshot["activeLine"] == expected, f"{action}({snapshot['activeThreadType']}) 行号错位"
        assert step["eventTone"] in {"NONE", "STEP", "HIT", "MISS", "SUCCESS", "DANGER", "BLOCK", "WAKEUP"}
        json.dumps(snapshot)  # 前端回放要求快照可序列化
    assert trace["metrics"]["criticalTime"] == 0.35
    assert trace["initialState"]["criticalTime"] == 0.35


def test_blocked_thread_reports_reason_for_ui() -> None:
    trace = simulate_threads(1, 3, 1, 6, seed=2)
    blocked_steps = [
        step for step in trace["steps"] if step["snapshot"]["action"] in {"BLOCK_EMPTY", "BLOCK_FULL", "BLOCK_MUTEX"}
    ]
    assert blocked_steps
    for step in blocked_steps:
        snapshot = step["snapshot"]
        blocked = [t for t in snapshot["threads"] if t["id"] == snapshot["activeThreadId"]]
        assert blocked and blocked[0]["state"] == "BLOCKED"
        assert blocked[0]["blockedOn"] in {"mutex", "empty", "full"}
        assert "阻塞" in blocked[0]["lastAction"] or "等待" in blocked[0]["lastAction"]
        assert step["eventTone"] == "BLOCK"
