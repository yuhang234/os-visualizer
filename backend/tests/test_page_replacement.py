"""页面置换算法轨迹测试：FIFO / LRU / OPT / CLOCK。

测试策略（三层）：
1. 与测试文件内独立编写的参考实现做差分对比（缺页次数必须一致）；
2. 经典教材数值硬断言（FIFO 3 帧 15 次缺页、4 帧 10 次缺页构成 Belady 异常；OPT 3 帧 9 次）；
3. 逐步快照不变量断言：第 k+1 步快照 == 前 k 次访问结束后的完整状态（这正是前端 O(1) 回退所依赖的前提）。
"""

from __future__ import annotations

import pytest

from app.engine.page_replacement import (
    PageReplacementInputError,
    parse_reference_string,
    simulate_page_replacement,
)

CLASSIC = [7, 0, 1, 2, 0, 3, 0, 4, 2, 3, 0, 3, 2, 1, 2, 0, 1, 7, 0, 1]
LOCALITY = [1, 2, 3, 1, 2, 4, 1, 2, 3, 4, 1, 2, 5, 1, 2, 3, 4, 5, 1, 2, 3]


# ---------------- 独立参考实现（不复用被测代码） ----------------


def ref_fifo(reference: list[int], frames: int) -> int:
    memory: list[int] = []
    arrival: list[int] = []
    faults = 0
    for page in reference:
        if page in memory:
            continue
        faults += 1
        if len(memory) < frames:
            memory.append(page)
            arrival.append(page)
        else:
            victim = arrival.pop(0)
            memory[memory.index(victim)] = page
            arrival.append(page)
    return faults


def ref_lru(reference: list[int], frames: int) -> int:
    memory: list[int] = []
    last_used: dict[int, int] = {}
    faults = 0
    for step, page in enumerate(reference):
        if page in memory:
            last_used[page] = step
            continue
        faults += 1
        if len(memory) < frames:
            memory.append(page)
        else:
            victim = min(memory, key=lambda p: last_used[p])
            memory[memory.index(victim)] = page
        last_used[page] = step
    return faults


def ref_opt(reference: list[int], frames: int) -> int:
    memory: list[int] = []
    faults = 0

    def next_use(page: int, current: int) -> int:
        for index in range(current + 1, len(reference)):
            if reference[index] == page:
                return index
        return len(reference)

    for index, page in enumerate(reference):
        if page in memory:
            continue
        faults += 1
        if len(memory) < frames:
            memory.append(page)
        else:
            victim = max(memory, key=lambda p: next_use(p, index))
            memory[memory.index(victim)] = page
    return faults


def ref_clock(reference: list[int], frames: int) -> int:
    memory: list[int | None] = [None] * frames
    bits = [0] * frames
    pointer = 0
    faults = 0
    for page in reference:
        if page in memory:
            bits[memory.index(page)] = 1
            continue
        faults += 1
        if None in memory:
            free = memory.index(None)
            memory[free] = page
            bits[free] = 1
            continue
        while bits[pointer] == 1:
            bits[pointer] = 0
            pointer = (pointer + 1) % frames
        memory[pointer] = page
        bits[pointer] = 1
        pointer = (pointer + 1) % frames
    return faults


REFERENCE_IMPLS = {"FIFO": ref_fifo, "LRU": ref_lru, "OPT": ref_opt, "CLOCK": ref_clock}


# ---------------- 1. 差分对比 ----------------


@pytest.mark.parametrize("algorithm", ["FIFO", "LRU", "OPT", "CLOCK"])
@pytest.mark.parametrize("reference", [CLASSIC, LOCALITY, [1, 1, 1, 1], [5]])
@pytest.mark.parametrize("frame_count", [2, 3, 4, 7])
def test_miss_count_matches_independent_reference(algorithm: str, reference: list[int], frame_count: int) -> None:
    trace = simulate_page_replacement(algorithm, reference, frame_count)
    expected = REFERENCE_IMPLS[algorithm](reference, frame_count)
    assert trace["metrics"]["misses"] == expected
    assert trace["metrics"]["hits"] == len(reference) - expected
    assert trace["metrics"]["totalAccess"] == len(reference)


# ---------------- 2. 经典教材数值 ----------------


def test_classic_fifo_three_frames_fifteen_faults() -> None:
    trace = simulate_page_replacement("FIFO", CLASSIC, 3)
    assert trace["metrics"]["misses"] == 15
    assert trace["metrics"]["hits"] == 5
    assert trace["metrics"]["missRate"] == pytest.approx(0.75)


def test_classic_belady_anomaly_for_fifo() -> None:
    three = simulate_page_replacement("FIFO", CLASSIC, 3)["metrics"]["misses"]
    four = simulate_page_replacement("FIFO", CLASSIC, 4)["metrics"]["misses"]
    assert (three, four) == (15, 10), "FIFO 在该参考串上应呈现 Belady 异常：页框增加反而缺页减少"


def test_classic_opt_is_optimal_lower_bound() -> None:
    opt = simulate_page_replacement("OPT", CLASSIC, 3)["metrics"]["misses"]
    assert opt == 9
    for algorithm in ("FIFO", "LRU", "CLOCK"):
        assert simulate_page_replacement(algorithm, CLASSIC, 3)["metrics"]["misses"] >= opt


def test_lru_has_no_belady_anomaly_on_classic_string() -> None:
    three = simulate_page_replacement("LRU", CLASSIC, 3)["metrics"]["misses"]
    four = simulate_page_replacement("LRU", CLASSIC, 4)["metrics"]["misses"]
    assert four <= three


# ---------------- 3. 逐步快照不变量 ----------------


@pytest.mark.parametrize("algorithm", ["FIFO", "LRU", "OPT", "CLOCK"])
def test_trace_structure_and_per_step_snapshot_invariants(algorithm: str) -> None:
    frame_count = 3
    reference = CLASSIC
    trace = simulate_page_replacement(algorithm, reference, frame_count)

    assert trace["algorithmId"] == algorithm.lower()
    assert trace["totalSteps"] == len(reference) + 1
    assert trace["metrics"]["totalAccess"] == len(reference)

    init = trace["steps"][0]
    assert init["stepIndex"] == 0
    assert init["snapshot"]["frames"] == [None] * frame_count
    assert init["snapshot"]["frameStatus"] == ["EMPTY"] * frame_count
    assert init["eventTone"] == "NONE"

    seen_pages: set[int] = set()
    hits = misses = 0
    for offset, page in enumerate(reference):
        step = trace["steps"][offset + 1]
        snapshot = step["snapshot"]
        assert step["stepIndex"] == offset + 1
        assert snapshot["page"] == page
        assert snapshot["frameCount"] == frame_count
        assert snapshot["accessedCount"] == offset + 1
        assert len(snapshot["frames"]) == frame_count
        assert len(snapshot["frameStatus"]) == frame_count
        assert len(snapshot["residentTime"]) == frame_count
        assert snapshot["status"] in {"HIT", "MISS"}

        occupied = [value for value in snapshot["frames"] if value is not None]
        # 页框中不得出现重复页面（置换必须先把旧页清掉）
        assert len(occupied) == len(set(occupied))
        # 驻留页面必来自已经访问过的页面
        assert set(occupied) <= seen_pages | {page}
        # HIT 时页面本来就在内存里；MISS 时该页面在本次访问后进入内存
        if snapshot["status"] == "HIT":
            hits += 1
            assert snapshot["evictedPage"] is None
        else:
            misses += 1
            assert page in snapshot["frames"]
        assert snapshot["hits"] == hits
        assert snapshot["misses"] == misses
        assert snapshot["totalAccess"] == offset + 1
        assert snapshot["hitRate"] == pytest.approx(round(hits / (offset + 1), 4))
        assert snapshot["missRate"] == pytest.approx(round(misses / (offset + 1), 4))
        # 当前访问的页框必须被标记为 HIT / MISS，其余只能是 IDLE 或 EMPTY
        markers = [status for status in snapshot["frameStatus"] if status in {"HIT", "MISS"}]
        assert len(markers) == 1
        assert markers[0] == snapshot["status"]
        seen_pages.add(page)

    last = trace["steps"][-1]["snapshot"]
    assert last["hits"] == trace["metrics"]["hits"]
    assert last["misses"] == trace["metrics"]["misses"]
    assert trace["finalFrames"] == last["frames"]
    assert trace["steps"][-1]["eventTone"] == last["status"]


@pytest.mark.parametrize("algorithm", ["FIFO", "LRU", "OPT", "CLOCK"])
def test_every_step_carries_replayable_logs_and_tone(algorithm: str) -> None:
    trace = simulate_page_replacement(algorithm, CLASSIC, 3)
    valid_tones = {"NONE", "STEP", "HIT", "MISS", "SUCCESS", "DANGER", "BLOCK", "WAKEUP"}
    valid_levels = {"INFO", "SUCCESS", "WARN", "DANGER"}
    for step in trace["steps"]:
        assert step["eventTone"] in valid_tones
        assert step["description"]
        assert step["snapshot"] and isinstance(step["snapshot"], dict)
        for log in step["logs"]:
            assert log["level"] in valid_levels
            assert log["message"]
            assert len(log["timestamp"]) == 8  # HH:MM:SS
    # 每次访问都至少产生一条日志，便于前端控制台逐步回放
    for offset in range(1, len(CLASSIC) + 1):
        assert len(trace["steps"][offset]["logs"]) >= 1


def test_clock_exposes_pointer_and_reference_bits() -> None:
    trace = simulate_page_replacement("CLOCK", CLASSIC, 3)
    for step in trace["steps"]:
        snapshot = step["snapshot"]
        assert 0 <= snapshot["clockPointer"] < 3
        assert len(snapshot["clockRefBits"]) == 3
        assert set(snapshot["clockRefBits"]) <= {0, 1}
        assert isinstance(snapshot["clockSweep"], list)


def test_fifo_and_lru_expose_eviction_order_metadata() -> None:
    fifo = simulate_page_replacement("FIFO", CLASSIC, 3)
    last_fifo = fifo["steps"][-1]["snapshot"]
    assert sorted(last_fifo["fifoQueue"]) == sorted(i for i, v in enumerate(last_fifo["frames"]) if v is not None)

    lru = simulate_page_replacement("LRU", CLASSIC, 3)
    last_lru = lru["steps"][-1]["snapshot"]
    assert sorted(last_lru["lruOrder"]) == sorted(i for i, v in enumerate(last_lru["frames"]) if v is not None)


def test_replay_is_deterministic_and_immutable_across_steps() -> None:
    """同一输入两次生成的轨迹必须逐步完全一致（快照不可被后续步修改）。"""
    first = simulate_page_replacement("FIFO", CLASSIC, 3)
    second = simulate_page_replacement("FIFO", CLASSIC, 3)
    snapshots_first = [step["snapshot"] for step in first["steps"]]
    snapshots_second = [step["snapshot"] for step in second["steps"]]
    assert snapshots_first == snapshots_second
    # 历史快照不得与最终状态共享同一列表对象（否则回退会看到被改写的数据）
    assert first["steps"][0]["snapshot"]["frames"] is not first["steps"][-1]["snapshot"]["frames"]
    assert first["steps"][0]["snapshot"]["frames"] == [None] * 3


# ---------------- 4. 输入解析与校验 ----------------


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("7,0,1", [7, 0, 1]),
        ("7 0 1", [7, 0, 1]),
        ("[7, 0, 1]", [7, 0, 1]),
        ("7，0，1", [7, 0, 1]),
        ("7;0;1", [7, 0, 1]),
        ("7\n0\t1", [7, 0, 1]),
        ([7, 0, 1], [7, 0, 1]),
        (" 7 , 0 , 1 ", [7, 0, 1]),
    ],
)
def test_parse_reference_string_accepts_common_formats(raw, expected) -> None:
    assert parse_reference_string(raw) == expected


@pytest.mark.parametrize("raw", ["7,a,1", "7,100", "-3", "7,-1"])
def test_parse_reference_string_rejects_illegal_values(raw) -> None:
    with pytest.raises(PageReplacementInputError):
        parse_reference_string(raw)


@pytest.mark.parametrize(
    "algorithm,reference,frames",
    [
        ("XYZ", [1, 2], 3),
        ("FIFO", [], 3),
        ("FIFO", [1, 2], 1),
        ("FIFO", [1, 2], 8),
        ("FIFO", list(range(60)) * 4, 3),
    ],
)
def test_simulate_rejects_out_of_contract_inputs(algorithm, reference, frames) -> None:
    with pytest.raises(PageReplacementInputError):
        simulate_page_replacement(algorithm, reference, frames)


def test_algorithm_name_is_case_insensitive() -> None:
    assert simulate_page_replacement("lru", [1, 2, 1], 3)["algorithmId"] == "lru"
