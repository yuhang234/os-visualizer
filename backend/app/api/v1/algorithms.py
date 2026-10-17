"""算法计算接口：页面置换 / 银行家 / 多线程（设计文档第 13.2 节）。"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from ...core import db
from ...engine.banker import BankerInputError, check_safety_trace, request_resource_trace
from ...engine.page_replacement import PageReplacementInputError, simulate_page_replacement
from ...engine.threads_simulator import ThreadsInputError, simulate_threads
from ...schemas.algorithms import (
    BankerRequestRequest,
    BankerSafetyRequest,
    PageReplacementRequest,
    ScenarioSaveRequest,
    ThreadsRequest,
)
from ...schemas.common import created, ok
from ..deps import current_user_optional, current_user_required

router = APIRouter(prefix="/algorithms", tags=["algorithms"])


@router.post("/page-replacement/simulate")
def page_replacement_simulate(payload: PageReplacementRequest) -> dict[str, Any]:
    """返回完整 ExecutionTrace（totalSteps / metrics / steps），前端在内存里回放。"""
    try:
        return simulate_page_replacement(payload.algorithm, payload.referenceString, payload.frameCount)
    except PageReplacementInputError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/banker/check-safety")
def banker_check_safety(payload: BankerSafetyRequest) -> dict[str, Any]:
    try:
        result = check_safety_trace(payload.available, payload.maxMatrix, payload.allocationMatrix)
    except BankerInputError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    trace = result["trace"]
    return ok(
        {
            "isSafe": result["isSafe"],
            "safeSequence": result["safeSequence"],
            "unfinishedProcesses": result["unfinishedProcesses"],
            "steps": trace["steps"],
            "trace": trace,
            "state": result["state"],
        }
    )


@router.post("/banker/request-resource")
def banker_request_resource(payload: BankerRequestRequest) -> dict[str, Any]:
    try:
        result = request_resource_trace(
            payload.processIndex,
            payload.requestVector,
            payload.currentState.available,
            payload.currentState.maxMatrix,
            payload.currentState.allocationMatrix,
        )
    except BankerInputError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ok(
        {
            "granted": result["granted"],
            "reason": result["reason"],
            "checkNeed": result["checkNeed"],
            "checkAvailable": result["checkAvailable"],
            "isSafeAfterTentative": result["isSafeAfterTentative"],
            "safeSequence": result["safeSequence"],
            "resultingAvailable": result.get("resultingAvailable"),
            "resultingAllocation": result.get("resultingAllocation"),
            "resultingNeed": result.get("resultingNeed"),
            "steps": result["trace"]["steps"],
            "trace": result["trace"],
        }
    )


@router.post("/threads/simulate")
def threads_simulate(payload: ThreadsRequest) -> dict[str, Any]:
    """返回离散并发事件序列快照（含不变量校验结果）。"""
    try:
        return simulate_threads(
            buffer_capacity=payload.bufferCapacity,
            producer_count=payload.producerCount,
            consumer_count=payload.consumerCount,
            total_operations=payload.totalOperations,
            production_time=payload.productionTime,
            consumption_time=payload.consumptionTime,
            seed=payload.seed,
            critical_time=payload.criticalTime,
        )
    except ThreadsInputError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


# ---------------- 案例持久化（登录后跨设备同步） ----------------


@router.get("/scenarios")
def list_scenarios(
    kind: str | None = None,
    user: dict[str, Any] | None = Depends(current_user_optional),
) -> dict[str, Any]:
    if user is None:
        return ok([], message="游客模式：案例仅保存在本地，登录后可云端同步")
    rows = db.list_scenarios(user["id"], kind)
    return ok(
        [
            {
                "id": int(row["id"]),
                "kind": row["kind"],
                "name": row["name"],
                "payload": json.loads(row["payload"]),
                "updatedAt": row["updated_at"],
            }
            for row in rows
        ]
    )


@router.post("/scenarios", status_code=201)
def save_scenario(
    payload: ScenarioSaveRequest,
    user: dict[str, Any] = Depends(current_user_required),
) -> dict[str, Any]:
    result = db.save_scenario(user["id"], payload.kind, payload.name, json.dumps(payload.payload, ensure_ascii=False))
    return created(result, message="案例已保存")


@router.delete("/scenarios/{scenario_id}")
def delete_scenario(scenario_id: int, user: dict[str, Any] = Depends(current_user_required)) -> dict[str, Any]:
    if not db.delete_scenario(user["id"], scenario_id):
        raise HTTPException(status_code=404, detail="案例不存在或无权删除")
    return ok({"deleted": True})
