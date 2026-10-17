"""页面置换算法轨迹生成器：FIFO / LRU / OPT / CLOCK。

设计文档第 5 章与第 4.1 节：后端一次性算完整步序列，前端在内存里 O(1) 回放。
每个参考串元素对应一个步骤（外加第 0 步的初始化快照）。
"""

from __future__ import annotations

from typing import Any

from .trace import TraceBuilder, log_entry

SUPPORTED_ALGORITHMS = ("FIFO", "LRU", "OPT", "CLOCK")

# 页框数取值范围（设计文档 5.3：NumberStepper Min 2 Max 7）
MIN_FRAMES = 2
MAX_FRAMES = 7
MAX_REFERENCE_LENGTH = 200


class PageReplacementInputError(ValueError):
    """输入参数越界或非法。"""


def parse_reference_string(raw: str | list[int] | None) -> list[int]:
    """接受 "7,0,1,2" / "7 0 1 2" / 已解析列表 三种形式。"""
    if raw is None:
        return []
    if isinstance(raw, list):
        values = raw
    else:
        normalized = raw.replace("，", ",").replace("[", "").replace("]", "")
        for sep in ("\n", "\t", ";"):
            normalized = normalized.replace(sep, ",")
        normalized = normalized.replace(" ", ",")
        parts = [p for p in normalized.split(",") if p.strip() != ""]
        values = []
        for part in parts:
            try:
                values.append(int(part.strip()))
            except ValueError as exc:
                raise PageReplacementInputError(f"参考串中存在非法数字: {part!r}") from exc
    result: list[int] = []
    for value in values:
        if not isinstance(value, int) or isinstance(value, bool):
            raise PageReplacementInputError("参考串元素必须为整数")
        if value < 0 or value > 99:
            raise PageReplacementInputError("页面号必须在 0~99 之间")
        result.append(value)
    return result


def _snapshot(
    *,
    algorithm: str,
    frames: list[int | None],
    frame_status: list[str],
    resident_time: list[int],
    page: int | None,
    status: str,
    evicted_page: int | None,
    evicted_frame_index: int | None,
    hits: int,
    misses: int,
    accessed_count: int,
    step_index: int,
    extras: dict[str, Any] | None = None,
) -> dict[str, Any]:
    total = hits + misses
    snapshot: dict[str, Any] = {
        "algorithm": algorithm,
        "frameCount": len(frames),
        "frames": list(frames),
        "frameStatus": list(frame_status),
        "residentTime": list(resident_time),
        "page": page,
        "status": status,
        "evictedPage": evicted_page,
        "evictedFrameIndex": evicted_frame_index,
        "hits": hits,
        "misses": misses,
        "accessedCount": accessed_count,
        "totalAccess": total,
        "hitRate": round(hits / total, 4) if total else 0.0,
        "missRate": round(misses / total, 4) if total else 0.0,
        "stepIndex": step_index,
    }
    if extras:
        snapshot.update(extras)
    return snapshot


def _frame_status_for_load(frames: list[int | None], loaded_index: int, status: str) -> list[str]:
    result: list[str] = []
    for index, value in enumerate(frames):
        if value is None:
            result.append("EMPTY")
        elif index == loaded_index:
            result.append(status)
        else:
            result.append("IDLE")
    return result


def simulate_fifo(reference: list[int], frame_count: int) -> dict[str, Any]:
    frames: list[int | None] = [None] * frame_count
    loaded_at: list[int] = [0] * frame_count
    fifo_queue: list[int] = []  # 页框索引，队首为最早载入
    hits = misses = 0

    builder = TraceBuilder(
        "fifo",
        "FIFO 先进先出页面置换算法",
        {
            "algorithm": "FIFO",
            "frameCount": frame_count,
            "referenceString": list(reference),
            "description": "FIFO：淘汰最早进入内存的页面，不考虑访问历史，可能出现 Belady 异常。",
        },
    )

    builder.add_step(
        "初始化",
        f"初始化 {frame_count} 个物理页框，全部为空。FIFO 就绪，开始扫描参考串。",
        _snapshot(
            algorithm="FIFO",
            frames=frames,
            frame_status=["EMPTY"] * frame_count,
            resident_time=[0] * frame_count,
            page=None,
            status="NONE",
            evicted_page=None,
            evicted_frame_index=None,
            hits=0,
            misses=0,
            accessed_count=0,
            step_index=0,
            extras={"fifoQueue": [], "lruOrder": [], "clockPointer": None, "clockRefBits": None},
        ),
        highlights=["frame:all"],
        logs=[log_entry("INFO", f"初始化完成: 页框数={frame_count}, 算法=FIFO, 参考串长度={len(reference)}")],
        event_tone="NONE",
    )

    for offset, page in enumerate(reference):
        step_index = offset + 1
        accessed = step_index
        evicted_page: int | None = None
        evicted_frame_index: int | None = None
        logs: list[dict[str, str]] = []
        highlights: list[str] = []
        tone = "STEP"

        if page in frames:
            frame_index = frames.index(page)
            hits += 1
            tone = "HIT"
            highlights = [f"frame:{frame_index}", f"page:{page}"]
            logs.append(log_entry("SUCCESS", f"访问页面 {page}: 命中页框 {frame_index}，无需置换"))
            description = (
                f"页面 {page} 已在页框 {frame_index} 中，命中。FIFO 队列顺序不受命中影响，"
                "队首仍是最早载入的页框。"
            )
            frame_status = ["HIT" if i == frame_index else ("EMPTY" if v is None else "IDLE") for i, v in enumerate(frames)]
        else:
            misses += 1
            tone = "MISS"
            free_index = next((i for i, v in enumerate(frames) if v is None), None)
            if free_index is not None:
                frame_index = free_index
                frames[frame_index] = page
                loaded_at[frame_index] = step_index
                fifo_queue.append(frame_index)
                logs.append(log_entry("DANGER", f"访问页面 {page}: 缺页，内存存在空闲页框，直接分配页框 {frame_index}"))
                description = f"页面 {page} 不在内存中，触发缺页；页框 {frame_index} 空闲，直接调入，未发生置换。"
            else:
                frame_index = fifo_queue.pop(0)
                evicted_page = frames[frame_index]
                evicted_frame_index = frame_index
                resident = step_index - loaded_at[frame_index]
                frames[frame_index] = page
                loaded_at[frame_index] = step_index
                fifo_queue.append(frame_index)
                logs.append(
                    log_entry(
                        "DANGER",
                        f"访问页面 {page}: 缺页，内存已满，根据 FIFO 淘汰页框 {frame_index} 中的旧页面 {evicted_page}"
                        f"（已驻留 {resident} 步）",
                    )
                )
                description = (
                    f"页面 {page} 触发缺页且内存已满：页框 {frame_index} 中的页面 {evicted_page} 已驻留 "
                    f"{resident} 步、最早进入内存，被 FIFO 规则淘汰，页面 {page} 调入该页框并排到队尾。"
                )
            highlights = [f"frame:{frame_index}", f"page:{page}"]
            frame_status = _frame_status_for_load(frames, frame_index, "MISS")

        resident_time = [max(0, step_index - loaded_at[i]) if frames[i] is not None else 0 for i in range(frame_count)]
        builder.add_step(
            f"访问页面 {page}",
            description,
            _snapshot(
                algorithm="FIFO",
                frames=frames,
                frame_status=frame_status,
                resident_time=resident_time,
                page=page,
                status="HIT" if tone == "HIT" else "MISS",
                evicted_page=evicted_page,
                evicted_frame_index=evicted_frame_index,
                hits=hits,
                misses=misses,
                accessed_count=accessed,
                step_index=step_index,
                extras={"fifoQueue": list(fifo_queue), "lruOrder": [], "clockPointer": None, "clockRefBits": None},
            ),
            highlights=highlights,
            logs=logs,
            event_tone=tone,
        )

    total = len(reference)
    return builder.build(
        metrics={
            "totalAccess": total,
            "hits": hits,
            "misses": misses,
            "hitRate": round(hits / total, 4) if total else 0.0,
            "missRate": round(misses / total, 4) if total else 0.0,
        },
        finalFrames=list(frames),
    )


def simulate_lru(reference: list[int], frame_count: int) -> dict[str, Any]:
    frames: list[int | None] = [None] * frame_count
    loaded_at: list[int] = [0] * frame_count
    last_used: list[int] = [0] * frame_count  # 最近一次被访问的步号
    hits = misses = 0

    def lru_order() -> list[int]:
        """返回页框索引，最久未使用者在前（仅统计已占用页框）。"""
        occupied = [i for i, v in enumerate(frames) if v is not None]
        return sorted(occupied, key=lambda i: last_used[i])

    builder = TraceBuilder(
        "lru",
        "LRU 最近最久未使用页面置换算法",
        {
            "algorithm": "LRU",
            "frameCount": frame_count,
            "referenceString": list(reference),
            "description": "LRU：淘汰最近一段时间最久未被访问的页面，利用程序局部性原理，无 Belady 异常。",
        },
    )

    builder.add_step(
        "初始化",
        f"初始化 {frame_count} 个物理页框，全部为空。LRU 就绪，开始扫描参考串。",
        _snapshot(
            algorithm="LRU",
            frames=frames,
            frame_status=["EMPTY"] * frame_count,
            resident_time=[0] * frame_count,
            page=None,
            status="NONE",
            evicted_page=None,
            evicted_frame_index=None,
            hits=0,
            misses=0,
            accessed_count=0,
            step_index=0,
            extras={"fifoQueue": [], "lruOrder": [], "clockPointer": None, "clockRefBits": None},
        ),
        highlights=["frame:all"],
        logs=[log_entry("INFO", f"初始化完成: 页框数={frame_count}, 算法=LRU, 参考串长度={len(reference)}")],
        event_tone="NONE",
    )

    for offset, page in enumerate(reference):
        step_index = offset + 1
        accessed = step_index
        evicted_page: int | None = None
        evicted_frame_index: int | None = None
        logs: list[dict[str, str]] = []
        highlights: list[str] = []
        tone = "STEP"

        if page in frames:
            frame_index = frames.index(page)
            hits += 1
            tone = "HIT"
            last_used[frame_index] = step_index
            highlights = [f"frame:{frame_index}", f"page:{page}"]
            logs.append(log_entry("SUCCESS", f"访问页面 {page}: 命中页框 {frame_index}，刷新其最近使用时间"))
            description = (
                f"页面 {page} 命中页框 {frame_index}，该页框成为最近最常使用者，"
                "在 LRU 淘汰序列中被推到最后。"
            )
            frame_status = ["HIT" if i == frame_index else ("EMPTY" if v is None else "IDLE") for i, v in enumerate(frames)]
        else:
            misses += 1
            tone = "MISS"
            free_index = next((i for i, v in enumerate(frames) if v is None), None)
            if free_index is not None:
                frame_index = free_index
                frames[frame_index] = page
                loaded_at[frame_index] = step_index
                last_used[frame_index] = step_index
                logs.append(log_entry("DANGER", f"访问页面 {page}: 缺页，分配空闲页框 {frame_index}"))
                description = f"页面 {page} 不在内存中，触发缺页；页框 {frame_index} 空闲，直接调入。"
            else:
                frame_index = min(range(frame_count), key=lambda i: last_used[i])
                evicted_page = frames[frame_index]
                evicted_frame_index = frame_index
                idle_steps = step_index - last_used[frame_index]
                frames[frame_index] = page
                loaded_at[frame_index] = step_index
                last_used[frame_index] = step_index
                logs.append(
                    log_entry(
                        "DANGER",
                        f"访问页面 {page}: 缺页，内存已满，淘汰页框 {frame_index} 中的页面 {evicted_page}"
                        f"（已 {idle_steps} 步未被访问）",
                    )
                )
                description = (
                    f"页面 {page} 触发缺页且内存已满：页框 {frame_index} 中的页面 {evicted_page} 已连续 "
                    f"{idle_steps} 步未被访问，是最近最久未使用者，被淘汰。"
                )
            highlights = [f"frame:{frame_index}", f"page:{page}"]
            frame_status = _frame_status_for_load(frames, frame_index, "MISS")

        resident_time = [max(0, step_index - loaded_at[i]) if frames[i] is not None else 0 for i in range(frame_count)]
        builder.add_step(
            f"访问页面 {page}",
            description,
            _snapshot(
                algorithm="LRU",
                frames=frames,
                frame_status=frame_status,
                resident_time=resident_time,
                page=page,
                status="HIT" if tone == "HIT" else "MISS",
                evicted_page=evicted_page,
                evicted_frame_index=evicted_frame_index,
                hits=hits,
                misses=misses,
                accessed_count=accessed,
                step_index=step_index,
                extras={"fifoQueue": [], "lruOrder": lru_order(), "clockPointer": None, "clockRefBits": None},
            ),
            highlights=highlights,
            logs=logs,
            event_tone=tone,
        )

    total = len(reference)
    return builder.build(
        metrics={
            "totalAccess": total,
            "hits": hits,
            "misses": misses,
            "hitRate": round(hits / total, 4) if total else 0.0,
            "missRate": round(misses / total, 4) if total else 0.0,
        },
        finalFrames=list(frames),
    )


def simulate_opt(reference: list[int], frame_count: int) -> dict[str, Any]:
    frames: list[int | None] = [None] * frame_count
    loaded_at: list[int] = [0] * frame_count
    hits = misses = 0

    def next_use(page: int, after_index: int) -> int:
        for index in range(after_index, len(reference)):
            if reference[index] == page:
                return index
        return len(reference)  # 之后再也不会被访问：最大距离

    builder = TraceBuilder(
        "opt",
        "OPT 最佳置换算法（Belady 最优）",
        {
            "algorithm": "OPT",
            "frameCount": frame_count,
            "referenceString": list(reference),
            "description": "OPT：淘汰未来最长时间不再被访问的页面。理论缺页率最低，但需要预知未来访问串，仅用于教学与性能下界对比。",
        },
    )

    builder.add_step(
        "初始化",
        f"初始化 {frame_count} 个物理页框，全部为空。OPT 就绪（需要完整参考串以预知未来）。",
        _snapshot(
            algorithm="OPT",
            frames=frames,
            frame_status=["EMPTY"] * frame_count,
            resident_time=[0] * frame_count,
            page=None,
            status="NONE",
            evicted_page=None,
            evicted_frame_index=None,
            hits=0,
            misses=0,
            accessed_count=0,
            step_index=0,
            extras={"fifoQueue": [], "lruOrder": [], "clockPointer": None, "clockRefBits": None},
        ),
        highlights=["frame:all"],
        logs=[log_entry("INFO", f"初始化完成: 页框数={frame_count}, 算法=OPT, 参考串长度={len(reference)}")],
        event_tone="NONE",
    )

    for offset, page in enumerate(reference):
        step_index = offset + 1
        accessed = step_index
        evicted_page: int | None = None
        evicted_frame_index: int | None = None
        logs: list[dict[str, str]] = []
        highlights: list[str] = []
        tone = "STEP"

        if page in frames:
            frame_index = frames.index(page)
            hits += 1
            tone = "HIT"
            highlights = [f"frame:{frame_index}", f"page:{page}"]
            logs.append(log_entry("SUCCESS", f"访问页面 {page}: 命中页框 {frame_index}，无需置换"))
            description = f"页面 {page} 已在页框 {frame_index} 中，命中。OPT 只在实际缺页时才做未来扫描。"
            frame_status = ["HIT" if i == frame_index else ("EMPTY" if v is None else "IDLE") for i, v in enumerate(frames)]
        else:
            misses += 1
            tone = "MISS"
            free_index = next((i for i, v in enumerate(frames) if v is None), None)
            if free_index is not None:
                frame_index = free_index
                frames[frame_index] = page
                loaded_at[frame_index] = step_index
                logs.append(log_entry("DANGER", f"访问页面 {page}: 缺页，分配空闲页框 {frame_index}"))
                description = f"页面 {page} 不在内存中，触发缺页；页框 {frame_index} 空闲，直接调入。"
            else:
                future = {frames[i]: next_use(int(frames[i]), offset + 1) for i in range(frame_count) if frames[i] is not None}
                frame_index = max(range(frame_count), key=lambda i: future.get(frames[i], len(reference)))
                evicted_page = frames[frame_index]
                evicted_frame_index = frame_index
                distance = future[evicted_page]
                distance_text = "此后不再被访问" if distance >= len(reference) else f"下次访问在第 {distance + 1} 步"
                frames[frame_index] = page
                loaded_at[frame_index] = step_index
                logs.append(
                    log_entry(
                        "DANGER",
                        f"访问页面 {page}: 缺页，内存已满，淘汰页框 {frame_index} 中的页面 {evicted_page}（{distance_text}）",
                    )
                )
                description = (
                    f"页面 {page} 触发缺页且内存已满：页框 {frame_index} 中的页面 {evicted_page} 距离下次访问最远"
                    f"（{distance_text}），按 OPT 规则被淘汰。"
                )
            highlights = [f"frame:{frame_index}", f"page:{page}"]
            frame_status = _frame_status_for_load(frames, frame_index, "MISS")

        resident_time = [max(0, step_index - loaded_at[i]) if frames[i] is not None else 0 for i in range(frame_count)]
        builder.add_step(
            f"访问页面 {page}",
            description,
            _snapshot(
                algorithm="OPT",
                frames=frames,
                frame_status=frame_status,
                resident_time=resident_time,
                page=page,
                status="HIT" if tone == "HIT" else "MISS",
                evicted_page=evicted_page,
                evicted_frame_index=evicted_frame_index,
                hits=hits,
                misses=misses,
                accessed_count=accessed,
                step_index=step_index,
                extras={"fifoQueue": [], "lruOrder": [], "clockPointer": None, "clockRefBits": None},
            ),
            highlights=highlights,
            logs=logs,
            event_tone=tone,
        )

    total = len(reference)
    return builder.build(
        metrics={
            "totalAccess": total,
            "hits": hits,
            "misses": misses,
            "hitRate": round(hits / total, 4) if total else 0.0,
            "missRate": round(misses / total, 4) if total else 0.0,
        },
        finalFrames=list(frames),
    )


def simulate_clock(reference: list[int], frame_count: int) -> dict[str, Any]:
    """CLOCK（二次机会）算法。

    实现约定：一次页面访问产生一个步骤；指针扫过并清除访问位的过程记录在该步骤的
    日志与 `clockSweep` 字段中，不在时间轴上额外插入子步骤（保证"第 k 步 == 第 k 次访问"，
    与参考串高亮一一对应）。这是对设计文档未明确之处的实现决定，已在交付报告说明。
    """
    frames: list[int | None] = [None] * frame_count
    loaded_at: list[int] = [0] * frame_count
    ref_bits: list[int] = [0] * frame_count
    pointer = 0
    hits = misses = 0

    builder = TraceBuilder(
        "clock",
        "CLOCK 时钟（二次机会）页面置换算法",
        {
            "algorithm": "CLOCK",
            "frameCount": frame_count,
            "referenceString": list(reference),
            "description": "CLOCK：把页框组织成环形队列，命中时置访问位为 1；缺页时指针顺时针扫描，遇到访问位为 1 的页面给予第二次机会并清零，直到找到访问位为 0 的页面淘汰。",
        },
    )

    builder.add_step(
        "初始化",
        f"初始化 {frame_count} 个物理页框，访问位全部为 0，时钟指针指向页框 0。",
        _snapshot(
            algorithm="CLOCK",
            frames=frames,
            frame_status=["EMPTY"] * frame_count,
            resident_time=[0] * frame_count,
            page=None,
            status="NONE",
            evicted_page=None,
            evicted_frame_index=None,
            hits=0,
            misses=0,
            accessed_count=0,
            step_index=0,
            extras={"fifoQueue": [], "lruOrder": [], "clockPointer": pointer, "clockRefBits": list(ref_bits), "clockSweep": []},
        ),
        highlights=["frame:all", f"clock:{pointer}"],
        logs=[log_entry("INFO", f"初始化完成: 页框数={frame_count}, 算法=CLOCK, 指针=页框 {pointer}")],
        event_tone="NONE",
    )

    for offset, page in enumerate(reference):
        step_index = offset + 1
        accessed = step_index
        evicted_page: int | None = None
        evicted_frame_index: int | None = None
        sweep: list[int] = []
        logs: list[dict[str, str]] = []
        highlights: list[str] = []
        tone = "STEP"

        if page in frames:
            frame_index = frames.index(page)
            hits += 1
            tone = "HIT"
            ref_bits[frame_index] = 1
            highlights = [f"frame:{frame_index}", f"page:{page}", f"clock:{pointer}"]
            logs.append(log_entry("SUCCESS", f"访问页面 {page}: 命中页框 {frame_index}，访问位置 1（给予二次机会）"))
            description = f"页面 {page} 命中页框 {frame_index}，硬件把该页框的访问位置 1；时钟指针不动（仍指向页框 {pointer}）。"
            frame_status = ["HIT" if i == frame_index else ("EMPTY" if v is None else "IDLE") for i, v in enumerate(frames)]
        else:
            misses += 1
            tone = "MISS"
            free_index = next((i for i, v in enumerate(frames) if v is None), None)
            if free_index is not None:
                frame_index = free_index
                frames[frame_index] = page
                loaded_at[frame_index] = step_index
                ref_bits[frame_index] = 1
                logs.append(log_entry("DANGER", f"访问页面 {page}: 缺页，分配空闲页框 {frame_index}，访问位置 1"))
                description = (
                    f"页面 {page} 不在内存中，触发缺页；页框 {frame_index} 空闲，直接调入并置访问位为 1。"
                    f"时钟指针保持在页框 {pointer}。"
                )
            else:
                # 指针扫描：访问位为 1 的页框给予第二次机会
                guard = 0
                while ref_bits[pointer] == 1 and guard < frame_count * 2 + 2:
                    ref_bits[pointer] = 0
                    sweep.append(pointer)
                    logs.append(
                        log_entry(
                            "WARN",
                            f"指针指向页框 {pointer}（页面 {frames[pointer]}）：访问位为 1，给予第二次机会并清零，指针前移",
                        )
                    )
                    pointer = (pointer + 1) % frame_count
                    guard += 1
                frame_index = pointer
                evicted_page = frames[frame_index]
                evicted_frame_index = frame_index
                frames[frame_index] = page
                loaded_at[frame_index] = step_index
                ref_bits[frame_index] = 1
                pointer = (pointer + 1) % frame_count
                sweep_text = (
                    f"先给页框 {', '.join(str(s) for s in sweep)} 二次机会后，" if sweep else ""
                )
                logs.append(
                    log_entry(
                        "DANGER",
                        f"访问页面 {page}: 缺页，内存已满，{sweep_text}淘汰页框 {frame_index} 中的页面 {evicted_page}，"
                        f"新页面访问位置 1，指针前移到页框 {pointer}",
                    )
                )
                description = (
                    f"页面 {page} 触发缺页且内存已满：{sweep_text}指针停在页框 {frame_index}，"
                    f"淘汰其中的页面 {evicted_page}，调入页面 {page} 并置访问位为 1。"
                )
            highlights = [f"frame:{frame_index}", f"page:{page}", f"clock:{pointer}"]
            frame_status = _frame_status_for_load(frames, frame_index, "MISS")

        resident_time = [max(0, step_index - loaded_at[i]) if frames[i] is not None else 0 for i in range(frame_count)]
        builder.add_step(
            f"访问页面 {page}",
            description,
            _snapshot(
                algorithm="CLOCK",
                frames=frames,
                frame_status=frame_status,
                resident_time=resident_time,
                page=page,
                status="HIT" if tone == "HIT" else "MISS",
                evicted_page=evicted_page,
                evicted_frame_index=evicted_frame_index,
                hits=hits,
                misses=misses,
                accessed_count=accessed,
                step_index=step_index,
                extras={
                    "fifoQueue": [],
                    "lruOrder": [],
                    "clockPointer": pointer,
                    "clockRefBits": list(ref_bits),
                    "clockSweep": sweep,
                },
            ),
            highlights=highlights,
            logs=logs,
            event_tone=tone,
        )

    total = len(reference)
    return builder.build(
        metrics={
            "totalAccess": total,
            "hits": hits,
            "misses": misses,
            "hitRate": round(hits / total, 4) if total else 0.0,
            "missRate": round(misses / total, 4) if total else 0.0,
        },
        finalFrames=list(frames),
    )


_DISPATCH = {
    "FIFO": simulate_fifo,
    "LRU": simulate_lru,
    "OPT": simulate_opt,
    "CLOCK": simulate_clock,
}


def simulate_page_replacement(algorithm: str, reference: list[int], frame_count: int) -> dict[str, Any]:
    """统一入口：校验输入并分派到具体算法。"""
    normalized = (algorithm or "").strip().upper()
    if normalized not in _DISPATCH:
        raise PageReplacementInputError(f"不支持的页面置换算法: {algorithm!r}，可选 {list(SUPPORTED_ALGORITHMS)}")
    if not isinstance(frame_count, int) or isinstance(frame_count, bool):
        raise PageReplacementInputError("物理页框数必须为整数")
    if frame_count < MIN_FRAMES or frame_count > MAX_FRAMES:
        raise PageReplacementInputError(f"物理页框数必须在 {MIN_FRAMES}~{MAX_FRAMES} 之间")
    if not reference:
        raise PageReplacementInputError("参考串不能为空")
    if len(reference) > MAX_REFERENCE_LENGTH:
        raise PageReplacementInputError(f"参考串长度不能超过 {MAX_REFERENCE_LENGTH}")
    return _DISPATCH[normalized](reference, frame_count)
