"""多线程同步互斥离散事件模拟器：有界缓冲区生产者-消费者。

设计文档第 7 章：互斥锁 mutex=1、空位信号量 empty=N、产品信号量 full=0。
伪代码（生产者 / 消费者）：
    1: item = produce_item();        1: P(full);
    2: P(empty);                     2: P(mutex);
    3: P(mutex);                     3: item = remove_item();
    4: insert_item(item);            4: V(mutex);
    5: V(mutex);                     5: V(empty);
    6: V(full);                      6: consume_item(item);

实现要点：
- 虚拟时间离散事件推进，事件按 (时间, 序号) 排序，给定 seed 后完全可复现。
- 信号量采用 FIFO 等待队列；V 操作在存在等待者时把令牌直接移交给队首线程。
- 每个动作产生一个步骤快照，供前端 O(1) 步进/回退。
"""

from __future__ import annotations

import heapq
import random
from collections import deque
from dataclasses import dataclass, field
from typing import Any

from .trace import TraceBuilder, log_entry

MAX_BUFFER_CAPACITY = 10
MAX_THREADS_PER_ROLE = 4
MAX_TOTAL_OPERATIONS = 60
MAX_STEPS = 5000

PRODUCER_CODE = [
    "item = produce_item();",
    "P(empty); // 等待空槽位",
    "P(mutex); // 抢占互斥锁",
    "insert_item(item); // 写入缓冲区",
    "V(mutex); // 释放互斥锁",
    "V(full); // 唤醒消费者",
]
CONSUMER_CODE = [
    "P(full); // 检查是否有产品",
    "P(mutex); // 抢占互斥锁",
    "item = remove_item(); // 取出产品",
    "V(mutex); // 释放互斥锁",
    "V(empty); // 增加空槽位信号",
    "consume_item(item);",
]


class ThreadsInputError(ValueError):
    """输入参数越界或非法。"""


@dataclass
class ThreadState:
    index: int
    thread_id: str
    kind: str  # PRODUCER / CONSUMER
    quota: int
    ops_done: int = 0
    pc: int = 0
    state: str = "NEW"  # NEW / RUNNING / BLOCKED / SLEEP / DONE
    blocked_on: str | None = None
    ready_time: float = 0.0
    current_line: int = 0
    last_action: str = "等待调度"
    produced: int = 0
    consumed: int = 0
    item_in_hand: int | None = None
    wait_events: int = 0
    wake_events: int = 0

    @property
    def progress(self) -> float:
        return round(min(1.0, self.ops_done / self.quota), 4) if self.quota else 1.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.thread_id,
            "name": self.thread_id,
            "type": self.kind,
            "state": self.state,
            "progress": self.progress,
            "opsDone": self.ops_done,
            "opsQuota": self.quota,
            "currentLine": self.current_line,
            "blockedOn": self.blocked_on,
            "lastAction": self.last_action,
            "produced": self.produced,
            "consumed": self.consumed,
            "waitEvents": self.wait_events,
            "wakeEvents": self.wake_events,
            "code": PRODUCER_CODE if self.kind == "PRODUCER" else CONSUMER_CODE,
        }


@dataclass
class CountingSemaphore:
    name: str
    value: int
    capacity: int | None = None
    waiters: deque[ThreadState] = field(default_factory=deque)

    def snapshot(self) -> int:
        return self.value


class BoundedBufferSimulator:
    def __init__(
        self,
        buffer_capacity: int,
        producer_count: int,
        consumer_count: int,
        total_operations: int,
        production_time: float = 1.5,
        consumption_time: float = 2.0,
        seed: int = 20261017,
        critical_time: float = 0.35,
    ) -> None:
        if not (1 <= buffer_capacity <= MAX_BUFFER_CAPACITY):
            raise ThreadsInputError(f"缓冲区容量必须在 1~{MAX_BUFFER_CAPACITY} 之间")
        if not (1 <= producer_count <= MAX_THREADS_PER_ROLE):
            raise ThreadsInputError(f"生产者线程数必须在 1~{MAX_THREADS_PER_ROLE} 之间")
        if not (1 <= consumer_count <= MAX_THREADS_PER_ROLE):
            raise ThreadsInputError(f"消费者线程数必须在 1~{MAX_THREADS_PER_ROLE} 之间")
        if not (1 <= total_operations <= MAX_TOTAL_OPERATIONS):
            raise ThreadsInputError(f"总操作数必须在 1~{MAX_TOTAL_OPERATIONS} 之间")
        if production_time <= 0 or consumption_time <= 0:
            raise ThreadsInputError("生产/消费耗时必须为正数")
        if critical_time < 0:
            raise ThreadsInputError("临界区持有时间不能为负数")

        self.capacity = buffer_capacity
        self.production_time = float(production_time)
        self.consumption_time = float(consumption_time)
        self.critical_time = float(critical_time)
        self.rng = random.Random(seed)
        self.seed = seed

        self.buffer: list[int | None] = [None] * buffer_capacity
        self.in_ptr = 0
        self.out_ptr = 0
        self.item_counter = 100

        self.mutex = CountingSemaphore("mutex", 1, 1)
        self.empty = CountingSemaphore("empty", buffer_capacity, buffer_capacity)
        self.full = CountingSemaphore("full", 0, buffer_capacity)
        self.mutex_owner: str | None = None

        self.threads: list[ThreadState] = []
        producer_quota, producer_extra = divmod(total_operations, producer_count)
        consumer_quota, consumer_extra = divmod(total_operations, consumer_count)
        for i in range(producer_count):
            quota = producer_quota + (1 if i < producer_extra else 0)
            self.threads.append(
                ThreadState(
                    index=len(self.threads),
                    thread_id=f"P{i + 1}",
                    kind="PRODUCER",
                    quota=max(quota, 1),
                    ready_time=round(self.rng.uniform(0, 0.35), 3),
                )
            )
        for i in range(consumer_count):
            quota = consumer_quota + (1 if i < consumer_extra else 0)
            self.threads.append(
                ThreadState(
                    index=len(self.threads),
                    thread_id=f"C{i + 1}",
                    kind="CONSUMER",
                    quota=max(quota, 1),
                    ready_time=round(self.rng.uniform(0.4, 0.9), 3),
                )
            )

        self.time = 0.0
        self.seq = 0
        self.heap: list[tuple[float, int, int]] = []
        for thread in self.threads:
            self._push(thread, thread.ready_time)
        self.counters = {"produced": 0, "consumed": 0, "blockEvents": 0, "wakeEvents": 0, "contextSwitches": 0, "mutexBlockEvents": 0}
        self.truncated = False

        self.builder = TraceBuilder(
            "threads-pc",
            "多线程同步互斥 —— 有界缓冲区生产者/消费者模型",
            {
                "bufferCapacity": buffer_capacity,
                "producerCount": producer_count,
                "consumerCount": consumer_count,
                "totalOperations": total_operations,
                "productionTime": self.production_time,
                "consumptionTime": self.consumption_time,
                "criticalTime": self.critical_time,
                "seed": seed,
                "producerCode": PRODUCER_CODE,
                "consumerCode": CONSUMER_CODE,
                "threads": [t.to_dict() for t in self.threads],
                "semaphores": {"mutex": 1, "empty": buffer_capacity, "full": 0},
                "description": "生产者先 P(empty) 再 P(mutex) 后写入缓冲区，消费者先 P(full) 再 P(mutex) 后取出；"
                "两个 P 操作的顺序不可颠倒，否则会发生死锁。",
            },
        )

    # ---------- 内部工具 ----------

    def _push(self, thread: ThreadState, when: float) -> None:
        self.seq += 1
        heapq.heappush(self.heap, (round(when, 3), self.seq, thread.index))

    def _snapshot(self, active: ThreadState | None, action: str) -> dict[str, Any]:
        return {
            "time": round(self.time, 3),
            "bufferState": list(self.buffer),
            "bufferCount": sum(1 for v in self.buffer if v is not None),
            "inPointer": self.in_ptr,
            "outPointer": self.out_ptr,
            "semaphores": {
                "mutex": self.mutex.value,
                "empty": self.empty.value,
                "full": self.full.value,
            },
            "mutexOwner": self.mutex_owner,
            "waitQueues": {
                "mutex": [t.thread_id for t in self.mutex.waiters],
                "empty": [t.thread_id for t in self.empty.waiters],
                "full": [t.thread_id for t in self.full.waiters],
            },
            "activeThreadId": active.thread_id if active else None,
            "activeThreadType": active.kind if active else None,
            "activeLine": active.current_line if active else None,
            "action": action,
            "threads": [t.to_dict() for t in self.threads],
            "counters": dict(self.counters),
        }

    def _emit(self, thread: ThreadState | None, title: str, description: str, action: str, *, tone: str = "STEP", logs: list[dict[str, str]] | None = None, highlights: list[str] | None = None) -> None:
        marks = list(highlights or [])
        if thread is not None:
            marks.append(f"thread:{thread.thread_id}")
            marks.append(f"line:{thread.thread_id}:{thread.current_line}")
        self.builder.add_step(title, description, self._snapshot(thread, action), highlights=marks, logs=logs or [], event_tone=tone)

    def _wake(self, sem: CountingSemaphore, thread: ThreadState, wake_reason: str) -> None:
        """把令牌移交给等待者：等待者直接获得资源，无需再次 P 操作。

        因此这里同步推进 pc —— 被阻塞的线程恰好停在某个 P 操作上，唤醒即代表该 P 已完成。
        """
        sem.waiters.remove(thread)
        thread.state = "RUNNING"
        thread.blocked_on = None
        thread.wake_events += 1
        thread.last_action = wake_reason
        thread.pc += 1
        if sem is self.mutex:
            self.mutex_owner = thread.thread_id
        self.counters["wakeEvents"] += 1
        self._push(thread, self.time)

    def _acquire(self, sem: CountingSemaphore, thread: ThreadState, line: int, label: str) -> bool:
        """返回 True 表示获取成功（可继续执行），False 表示阻塞（已挂起）。"""
        thread.current_line = line
        if sem.value > 0:
            sem.value -= 1
            if sem is self.mutex:
                self.mutex_owner = thread.thread_id
            return True
        thread.state = "BLOCKED"
        thread.blocked_on = sem.name
        thread.wait_events += 1
        thread.last_action = f"阻塞等待 {label}"
        sem.waiters.append(thread)
        self.counters["blockEvents"] += 1
        if sem is self.mutex:
            self.counters["mutexBlockEvents"] += 1
        return False

    def _release(self, sem: CountingSemaphore, thread: ThreadState, line: int) -> ThreadState | None:
        thread.current_line = line
        if sem is self.mutex:
            self.mutex_owner = None
        if sem.waiters:
            woken = sem.waiters[0]
            self._wake(sem, woken, f"被 {thread.thread_id} 的 V({sem.name}) 唤醒")
            return woken
        sem.value = min(sem.capacity, sem.value + 1) if sem.capacity is not None else sem.value + 1
        return None

    # ---------- 线程执行 ----------

    def _run_producer(self, thread: ThreadState) -> None:
        while True:
            if thread.ops_done >= thread.quota:
                thread.state = "DONE"
                thread.blocked_on = None
                thread.last_action = "已完成全部生产任务"
                self._emit(
                    thread,
                    f"{thread.thread_id} 完成生产任务",
                    f"{thread.thread_id} 已累计生产 {thread.produced} 个产品，达到配额 {thread.quota}，线程退出。",
                    "DONE",
                    tone="SUCCESS",
                    logs=[log_entry("SUCCESS", f"{thread.thread_id}: 生产任务完成（{thread.produced}/{thread.quota}）")],
                )
                return

            line = thread.pc % 6
            if line == 0:
                thread.current_line = 1
                thread.state = "SLEEP"
                thread.item_in_hand = self.item_counter
                self.item_counter += 1
                thread.last_action = f"正在生产产品 #{thread.item_in_hand}"
                thread.ready_time = round(self.time + self.production_time, 3)
                self._emit(
                    thread,
                    f"{thread.thread_id} 生产产品 #{thread.item_in_hand}",
                    f"{thread.thread_id} 执行 produce_item()，耗时 {self.production_time}s 生成产品 #{thread.item_in_hand}，"
                    f"预计 {thread.ready_time}s 后进入临界区申请。",
                    "PRODUCE",
                    tone="STEP",
                    logs=[log_entry("INFO", f"{thread.thread_id}: produce_item() → #{thread.item_in_hand}（耗时 {self.production_time}s）")],
                )
                thread.pc += 1
                self._push(thread, thread.ready_time)
                return

            if line == 1:
                thread.current_line = 2
                if self._acquire(self.empty, thread, 2, "空槽位 empty"):
                    thread.last_action = "P(empty) 成功，获得空槽位"
                    self._emit(
                        thread,
                        f"{thread.thread_id} P(empty) 成功",
                        f"{thread.thread_id} 申请空槽位成功，empty 由 {self.empty.value + 1} 减为 {self.empty.value}。",
                        "P_EMPTY",
                        logs=[log_entry("INFO", f"{thread.thread_id}: P(empty) 成功，empty={self.empty.value}")],
                    )
                    thread.pc += 1
                    continue
                self._emit(
                    thread,
                    f"{thread.thread_id} 阻塞在 P(empty)",
                    f"缓冲区已满（empty=0），{thread.thread_id} 无法获得空槽位，被挂入 empty 等待队列，"
                    "等待消费者 V(empty) 唤醒。",
                    "BLOCK_EMPTY",
                    tone="BLOCK",
                    logs=[log_entry("WARN", f"{thread.thread_id}: P(empty) 阻塞 —— 缓冲区已满（empty=0）")],
                )
                return

            if line == 2:
                thread.current_line = 3
                if self._acquire(self.mutex, thread, 3, "互斥锁 mutex"):
                    thread.last_action = "P(mutex) 成功，进入临界区"
                    self._emit(
                        thread,
                        f"{thread.thread_id} 进入临界区",
                        f"{thread.thread_id} 抢占互斥锁成功（mutex=0），获得临界区访问权，开始写入缓冲区。",
                        "P_MUTEX",
                        logs=[log_entry("INFO", f"{thread.thread_id}: P(mutex) 成功，进入临界区")],
                    )
                    thread.pc += 1
                    continue
                self._emit(
                    thread,
                    f"{thread.thread_id} 阻塞在 P(mutex)",
                    f"互斥锁已被 {self.mutex_owner} 持有，{thread.thread_id} 进入 mutex 等待队列，"
                    "体现互斥语义：任一时刻只允许一个线程操作缓冲区。",
                    "BLOCK_MUTEX",
                    tone="BLOCK",
                    logs=[log_entry("WARN", f"{thread.thread_id}: P(mutex) 阻塞 —— 锁被 {self.mutex_owner} 持有")],
                )
                return

            if line == 3:
                thread.current_line = 4
                slot = self.in_ptr
                item = thread.item_in_hand
                self.buffer[slot] = item
                self.in_ptr = (self.in_ptr + 1) % self.capacity
                thread.item_in_hand = None
                self.counters["produced"] += 1
                thread.produced += 1
                thread.last_action = f"写入产品 #{item} 到槽位 {slot}，持有互斥锁中"
                self._emit(
                    thread,
                    f"{thread.thread_id} 写入槽位 {slot}",
                    f"持有互斥锁期间，{thread.thread_id} 把产品 #{item} 写入槽位 {slot}，"
                    f"写指针推进到 {self.in_ptr}，缓冲区现有 {sum(1 for v in self.buffer if v is not None)}/{self.capacity} 个产品。"
                    + (
                        f"临界区尚未退出（继续持锁 {self.critical_time}s），其他线程此时申请 mutex 会被阻塞。"
                        if self.critical_time > 0
                        else ""
                    ),
                    "INSERT",
                    tone="STEP",
                    logs=[log_entry("SUCCESS", f"{thread.thread_id}: insert_item(#{item}) → 槽位 {slot}")],
                )
                thread.pc += 1
                # 写入完成后仍持锁，被调度器在临界区内抢占一段时间：
                # 这段时间里其他线程的 P(mutex) 会落到 BLOCK_MUTEX 上，互斥锁争抢因此可观察。
                if self.critical_time > 0:
                    thread.ready_time = round(self.time + self.critical_time, 3)
                    self._push(thread, thread.ready_time)
                    return
                continue

            if line == 4:
                thread.current_line = 5
                woken = self._release(self.mutex, thread, 5)
                thread.last_action = "V(mutex) 释放互斥锁"
                self._emit(
                    thread,
                    f"{thread.thread_id} 退出临界区",
                    f"{thread.thread_id} 执行 V(mutex) 释放互斥锁"
                    + (f"，唤醒等待者 {woken.thread_id} 并将锁直接移交。" if woken else "，mutex 恢复为 1。"),
                    "V_MUTEX",
                    logs=[log_entry("INFO", f"{thread.thread_id}: V(mutex) 释放临界区" + (f"，唤醒 {woken.thread_id}" if woken else ""))],
                )
                thread.pc += 1
                continue

            if line == 5:
                thread.current_line = 6
                woken = self._release(self.full, thread, 6)
                thread.ops_done += 1
                thread.last_action = "V(full) 增加产品信号量"
                self._emit(
                    thread,
                    f"{thread.thread_id} V(full) 通知消费者",
                    f"{thread.thread_id} 完成第 {thread.ops_done}/{thread.quota} 次生产：V(full) 使产品信号量变为 {self.full.value}"
                    + (f"，唤醒等待中的消费者 {woken.thread_id}。" if woken else "，当前无消费者等待。"),
                    "V_FULL",
                    tone="SUCCESS",
                    logs=[
                        log_entry(
                            "SUCCESS",
                            f"{thread.thread_id}: V(full)，full={self.full.value}"
                            + (f"，唤醒 {woken.thread_id}" if woken else ""),
                        )
                    ],
                )
                thread.pc += 1
                if thread.ops_done >= thread.quota:
                    continue
                # 生产下一件产品前让出 CPU，制造并发交错
                thread.ready_time = round(self.time + 0.05, 3)
                self._push(thread, thread.ready_time)
                return

    def _run_consumer(self, thread: ThreadState) -> None:
        while True:
            if thread.ops_done >= thread.quota:
                thread.state = "DONE"
                thread.blocked_on = None
                thread.last_action = "已完成全部消费任务"
                self._emit(
                    thread,
                    f"{thread.thread_id} 完成消费任务",
                    f"{thread.thread_id} 已累计消费 {thread.consumed} 个产品，达到配额 {thread.quota}，线程退出。",
                    "DONE",
                    tone="SUCCESS",
                    logs=[log_entry("SUCCESS", f"{thread.thread_id}: 消费任务完成（{thread.consumed}/{thread.quota}）")],
                )
                return

            line = thread.pc % 6
            if line == 0:
                thread.current_line = 1
                if self._acquire(self.full, thread, 1, "产品信号量 full"):
                    thread.last_action = "P(full) 成功，缓冲区有产品"
                    self._emit(
                        thread,
                        f"{thread.thread_id} P(full) 成功",
                        f"{thread.thread_id} 确认缓冲区有产品，full 由 {self.full.value + 1} 减为 {self.full.value}。",
                        "P_FULL",
                        logs=[log_entry("INFO", f"{thread.thread_id}: P(full) 成功，full={self.full.value}")],
                    )
                    thread.pc += 1
                    continue
                self._emit(
                    thread,
                    f"{thread.thread_id} 阻塞在 P(full)",
                    f"缓冲区当前为空（full=0），{thread.thread_id} 没有产品可取，被挂入 full 等待队列，"
                    "等待生产者 V(full) 唤醒。",
                    "BLOCK_FULL",
                    tone="BLOCK",
                    logs=[log_entry("WARN", f"{thread.thread_id}: P(full) 阻塞 —— 缓冲区为空（full=0）")],
                )
                return

            if line == 1:
                thread.current_line = 2
                if self._acquire(self.mutex, thread, 2, "互斥锁 mutex"):
                    thread.last_action = "P(mutex) 成功，进入临界区"
                    self._emit(
                        thread,
                        f"{thread.thread_id} 进入临界区",
                        f"{thread.thread_id} 抢占互斥锁成功（mutex=0），获得临界区访问权，准备取出产品。",
                        "P_MUTEX",
                        logs=[log_entry("INFO", f"{thread.thread_id}: P(mutex) 成功，进入临界区")],
                    )
                    thread.pc += 1
                    continue
                self._emit(
                    thread,
                    f"{thread.thread_id} 阻塞在 P(mutex)",
                    f"互斥锁已被 {self.mutex_owner} 持有，{thread.thread_id} 进入 mutex 等待队列，等待锁释放。",
                    "BLOCK_MUTEX",
                    tone="BLOCK",
                    logs=[log_entry("WARN", f"{thread.thread_id}: P(mutex) 阻塞 —— 锁被 {self.mutex_owner} 持有")],
                )
                return

            if line == 2:
                thread.current_line = 3
                slot = self.out_ptr
                item = self.buffer[slot]
                self.buffer[slot] = None
                self.out_ptr = (self.out_ptr + 1) % self.capacity
                thread.item_in_hand = item
                self.counters["consumed"] += 1
                thread.consumed += 1
                thread.last_action = f"取出槽位 {slot} 的产品 #{item}，持有互斥锁中"
                self._emit(
                    thread,
                    f"{thread.thread_id} 取出槽位 {slot}",
                    f"持有互斥锁期间，{thread.thread_id} 从槽位 {slot} 取出产品 #{item}，"
                    f"读指针推进到 {self.out_ptr}，缓冲区剩余 {sum(1 for v in self.buffer if v is not None)}/{self.capacity} 个产品。"
                    + (
                        f"临界区尚未退出（继续持锁 {self.critical_time}s），其他线程此时申请 mutex 会被阻塞。"
                        if self.critical_time > 0
                        else ""
                    ),
                    "REMOVE",
                    tone="STEP",
                    logs=[log_entry("SUCCESS", f"{thread.thread_id}: remove_item() ← 槽位 {slot} 的产品 #{item}")],
                )
                thread.pc += 1
                if self.critical_time > 0:
                    thread.ready_time = round(self.time + self.critical_time, 3)
                    self._push(thread, thread.ready_time)
                    return
                continue

            if line == 3:
                thread.current_line = 4
                woken = self._release(self.mutex, thread, 4)
                thread.last_action = "V(mutex) 释放互斥锁"
                self._emit(
                    thread,
                    f"{thread.thread_id} 退出临界区",
                    f"{thread.thread_id} 执行 V(mutex) 释放互斥锁"
                    + (f"，唤醒等待者 {woken.thread_id} 并将锁直接移交。" if woken else "，mutex 恢复为 1。"),
                    "V_MUTEX",
                    logs=[log_entry("INFO", f"{thread.thread_id}: V(mutex) 释放临界区" + (f"，唤醒 {woken.thread_id}" if woken else ""))],
                )
                thread.pc += 1
                continue

            if line == 4:
                thread.current_line = 5
                woken = self._release(self.empty, thread, 5)
                thread.last_action = "V(empty) 归还空槽位"
                self._emit(
                    thread,
                    f"{thread.thread_id} V(empty) 归还空槽位",
                    f"{thread.thread_id} 归还一个空槽位：V(empty) 使空位信号量变为 {self.empty.value}"
                    + (f"，唤醒被阻塞的生产者 {woken.thread_id}。" if woken else "，当前无生产者等待。"),
                    "V_EMPTY",
                    logs=[
                        log_entry(
                            "SUCCESS",
                            f"{thread.thread_id}: V(empty)，empty={self.empty.value}"
                            + (f"，唤醒 {woken.thread_id}" if woken else ""),
                        )
                    ],
                )
                thread.pc += 1
                continue

            if line == 5:
                thread.current_line = 6
                item = thread.item_in_hand
                thread.item_in_hand = None
                thread.state = "SLEEP"
                thread.ops_done += 1
                thread.last_action = f"正在消费产品 #{item}"
                thread.ready_time = round(self.time + self.consumption_time, 3)
                self._emit(
                    thread,
                    f"{thread.thread_id} 消费产品 #{item}",
                    f"{thread.thread_id} 执行 consume_item(#{item})，耗时 {self.consumption_time}s，"
                    f"完成第 {thread.ops_done}/{thread.quota} 次消费。",
                    "CONSUME",
                    tone="SUCCESS",
                    logs=[log_entry("INFO", f"{thread.thread_id}: consume_item(#{item}) 耗时 {self.consumption_time}s")],
                )
                thread.pc += 1
                if thread.ops_done >= thread.quota:
                    continue
                self._push(thread, thread.ready_time)
                return

    # ---------- 主循环 ----------

    def run(self) -> dict[str, Any]:
        self._emit(
            None,
            "初始化同步原语",
            f"缓冲区容量 {self.capacity}，互斥锁 mutex=1，空位信号量 empty={self.capacity}，产品信号量 full=0；"
            f"{len([t for t in self.threads if t.kind == 'PRODUCER'])} 个生产者与 "
            f"{len([t for t in self.threads if t.kind == 'CONSUMER'])} 个消费者线程已创建。",
            "INIT",
            tone="NONE",
            logs=[
                log_entry(
                    "INFO",
                    f"初始化完成: 缓冲区={self.capacity}, 生产者={len([t for t in self.threads if t.kind == 'PRODUCER'])}, "
                    f"消费者={len([t for t in self.threads if t.kind == 'CONSUMER'])}, seed={self.seed}",
                )
            ],
        )

        while self.heap:
            if len(self.builder.steps) >= MAX_STEPS:
                self.truncated = True
                break
            when, _, index = heapq.heappop(self.heap)
            thread = self.threads[index]
            if thread.state == "DONE":
                continue
            self.time = max(self.time, when)
            if thread.state != "BLOCKED":
                thread.state = "RUNNING"
            self.counters["contextSwitches"] += 1
            if thread.kind == "PRODUCER":
                self._run_producer(thread)
            else:
                self._run_consumer(thread)

        # 收尾：把仍在阻塞的线程标记出来，便于观察死锁/饥饿
        still_blocked = [t.thread_id for t in self.threads if t.state == "BLOCKED"]
        completed = [t.thread_id for t in self.threads if t.state == "DONE"]
        all_done = len(completed) == len(self.threads)
        buffer_count = sum(1 for v in self.buffer if v is not None)
        invariants_ok = (
            self.empty.value + self.full.value == self.capacity
            and buffer_count == self.full.value
            and 0 <= self.mutex.value <= 1
        )
        summary = (
            f"模拟结束：{len(completed)}/{len(self.threads)} 个线程完成全部配额，累计生产 {self.counters['produced']} 个、"
            f"消费 {self.counters['consumed']} 个产品，缓冲区残留 {buffer_count} 个。"
            + (f"仍被阻塞的线程：{'、'.join(still_blocked)}。" if still_blocked else "无线程处于阻塞状态。")
            + ("" if invariants_ok else "⚠ 不变量校验异常，请检查模拟器实现。")
        )
        self._emit(
            None,
            "模拟结束",
            summary,
            "FINISH",
            tone="SUCCESS" if all_done and invariants_ok else "DANGER",
            logs=[
                log_entry(
                    "SUCCESS" if all_done and invariants_ok else "WARN",
                    f"结束统计: 生产={self.counters['produced']}, 消费={self.counters['consumed']}, "
                    f"阻塞事件={self.counters['blockEvents']}, 唤醒事件={self.counters['wakeEvents']}, "
                    f"上下文切换={self.counters['contextSwitches']}, 缓冲区残留={buffer_count}",
                )
            ],
        )

        return self.builder.build(
            metrics={
                "bufferCapacity": self.capacity,
                "produced": self.counters["produced"],
                "consumed": self.counters["consumed"],
                "bufferRemaining": buffer_count,
                "blockEvents": self.counters["blockEvents"],
                "mutexBlockEvents": self.counters["mutexBlockEvents"],
                "wakeEvents": self.counters["wakeEvents"],
                "contextSwitches": self.counters["contextSwitches"],
                "virtualDuration": round(self.time, 3),
                "criticalTime": self.critical_time,
                "completedThreads": completed,
                "blockedThreads": still_blocked,
                "truncated": self.truncated,
            },
            invariants={
                "emptyPlusFullEqualsCapacity": self.empty.value + self.full.value == self.capacity,
                "bufferCountEqualsFull": buffer_count == self.full.value,
                "mutexInRange": 0 <= self.mutex.value <= 1,
                "noNegativeSemaphore": self.empty.value >= 0 and self.full.value >= 0 and self.mutex.value >= 0,
                "producedMinusConsumedEqualsBuffer": self.counters["produced"] - self.counters["consumed"] == buffer_count,
            },
        )


def simulate_threads(
    buffer_capacity: int,
    producer_count: int,
    consumer_count: int,
    total_operations: int,
    production_time: float = 1.5,
    consumption_time: float = 2.0,
    seed: int = 20261017,
    critical_time: float = 0.35,
) -> dict[str, Any]:
    simulator = BoundedBufferSimulator(
        buffer_capacity=buffer_capacity,
        producer_count=producer_count,
        consumer_count=consumer_count,
        total_operations=total_operations,
        production_time=production_time,
        consumption_time=consumption_time,
        seed=seed,
        critical_time=critical_time,
    )
    return simulator.run()
