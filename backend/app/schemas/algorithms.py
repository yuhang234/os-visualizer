"""算法接口请求体（设计文档第 13.2 节）。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator

from ..engine.page_replacement import MAX_FRAMES, MIN_FRAMES, SUPPORTED_ALGORITHMS


class PageReplacementRequest(BaseModel):
    algorithm: str = Field(default="FIFO", description="FIFO / LRU / OPT / CLOCK")
    referenceString: list[int] = Field(default_factory=list, description="页面参考串，元素为 0~99 的整数")
    frameCount: int = Field(default=3, ge=MIN_FRAMES, le=MAX_FRAMES)

    @field_validator("algorithm")
    @classmethod
    def _normalize(cls, value: str) -> str:
        upper = value.strip().upper()
        if upper not in SUPPORTED_ALGORITHMS:
            raise ValueError(f"algorithm 必须是 {list(SUPPORTED_ALGORITHMS)} 之一")
        return upper

    @field_validator("referenceString")
    @classmethod
    def _validate_pages(cls, value: list[int]) -> list[int]:
        # 设计文档：参考串元素为 0~99 的页号，超出范围属于参数错误而不是静默接受
        for page in value:
            if page < 0 or page > 99:
                raise ValueError(f"参考串元素必须是 0~99 的页号，收到 {page}")
        return value


class BankerState(BaseModel):
    available: list[int]
    maxMatrix: list[list[int]]
    allocationMatrix: list[list[int]]
    needMatrix: list[list[int]] | None = None


class BankerSafetyRequest(BankerState):
    pass


class BankerRequestRequest(BaseModel):
    processIndex: int = Field(ge=0)
    requestVector: list[int]
    currentState: BankerState


class ThreadsRequest(BaseModel):
    bufferCapacity: int = Field(default=5, ge=1, le=10)
    producerCount: int = Field(default=2, ge=1, le=4)
    consumerCount: int = Field(default=2, ge=1, le=4)
    totalOperations: int = Field(default=20, ge=1, le=60)
    productionTime: float = Field(default=1.5, gt=0, le=30)
    consumptionTime: float = Field(default=2.0, gt=0, le=30)
    criticalTime: float = Field(
        default=0.35,
        ge=0,
        le=10,
        description="临界区写/取之后的持锁时间；>0 时其他线程可在该窗口内观察到 P(mutex) 阻塞（互斥锁争抢）",
    )
    seed: int = Field(default=20261017)


class ScenarioSaveRequest(BaseModel):
    kind: str = Field(description="page-replacement / banker / threads")
    name: str = Field(min_length=1, max_length=64)
    payload: dict[str, Any]


class ScenarioOut(BaseModel):
    id: int
    kind: str
    name: str
    payload: dict[str, Any]
    updatedAt: str
