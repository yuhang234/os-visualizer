"""ExecutionTrace 共享构造工具。

设计文档第 4.1 节定义了步骤数据结构；本模块提供统一构造函数，保证三个算法
产出的轨迹结构完全一致（前端因此只需一个回放引擎）。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

# 轨迹内日志的虚拟时间戳步进（秒）。一次性算完的轨迹需要一个"看起来像控制台"的时间轴。
_LOG_TIME_STEP = timedelta(milliseconds=350)

VALID_TONES = {"NONE", "STEP", "HIT", "MISS", "SUCCESS", "DANGER", "BLOCK", "WAKEUP"}
VALID_LEVELS = {"INFO", "SUCCESS", "WARN", "DANGER"}


class TraceBuilder:
    """逐步累积步骤快照，最后一次性产出 ExecutionTrace。"""

    def __init__(self, algorithm_id: str, algorithm_name: str, initial_state: dict[str, Any]) -> None:
        self.algorithm_id = algorithm_id
        self.algorithm_name = algorithm_name
        self.initial_state = initial_state
        self.steps: list[dict[str, Any]] = []
        self._base_time = datetime.now(timezone.utc)

    def _timestamp(self, step_index: int) -> str:
        moment = self._base_time + _LOG_TIME_STEP * step_index
        # 本地教学场景展示 HH:MM:SS 即可，避免时区字符串挤占控制台宽度。
        return moment.strftime("%H:%M:%S")

    def add_step(
        self,
        title: str,
        description: str,
        snapshot: dict[str, Any],
        *,
        highlights: Iterable[str] | None = None,
        logs: Iterable[dict[str, str]] | None = None,
        event_tone: str = "STEP",
    ) -> int:
        index = len(self.steps)
        normalized_logs: list[dict[str, str]] = []
        for entry in logs or []:
            level = str(entry.get("level", "INFO")).upper()
            normalized_logs.append(
                {
                    "timestamp": entry.get("timestamp") or self._timestamp(index),
                    "level": level if level in VALID_LEVELS else "INFO",
                    "message": str(entry.get("message", "")),
                }
            )
        tone = event_tone if event_tone in VALID_TONES else "STEP"
        self.steps.append(
            {
                "stepIndex": index,
                "title": title,
                "description": description,
                "snapshot": snapshot,
                "highlights": list(highlights or []),
                "logs": normalized_logs,
                "eventTone": tone,
            }
        )
        return index

    def build(self, metrics: dict[str, Any] | None = None, **extra: Any) -> dict[str, Any]:
        trace: dict[str, Any] = {
            "algorithmId": self.algorithm_id,
            "algorithmName": self.algorithm_name,
            "createdAt": self._base_time.isoformat(),
            "totalSteps": len(self.steps),
            "initialState": self.initial_state,
            "steps": self.steps,
        }
        if metrics is not None:
            trace["metrics"] = metrics
        trace.update(extra)
        return trace


def log_entry(level: str, message: str) -> dict[str, str]:
    return {"level": level, "message": message}
