"""햄버거 키오스크 공통 API 계약.

인혜님 담당 파일입니다. 필드 변경 전 루트 `공통 API.md`를 먼저 확인하세요.
"""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


KioskMode = Literal["workflow", "agent"]
KioskStatus = Literal[
    "needs_clarification",
    "confirmation_required",
    "completed",
    "rejected",
    "error",
]
OrderOption = Literal["single", "set"]


class KioskOrderRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: KioskMode
    session_id: str = Field(min_length=1, max_length=100)
    message: str = Field(min_length=1, max_length=1000)
    confirmed: bool = False
    action_id: str | None = None


class MenuItem(BaseModel):
    menu_id: str
    name: str
    description: str
    single_price: int = Field(ge=0)
    set_price: int = Field(ge=0)
    active: bool = True


class CartItem(BaseModel):
    menu_id: str
    menu_name: str
    option: OrderOption
    quantity: int = Field(ge=1, le=20)
    unit_price: int = Field(ge=0)
    line_total: int = Field(ge=0)


class ToolCall(BaseModel):
    tool: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class TraceItem(BaseModel):
    step: int = Field(ge=1)
    stage: str
    data: dict[str, Any] = Field(default_factory=dict)


class KioskOrderResponse(BaseModel):
    mode: KioskMode
    session_id: str
    status: KioskStatus
    answer: str
    cart: list[CartItem] = Field(default_factory=list)
    total_price: int = Field(default=0, ge=0)
    action_id: str | None = None
    order_number: str | None = None
    tool_calls: list[ToolCall] = Field(default_factory=list)
    trace: list[TraceItem] = Field(default_factory=list)
    termination_reason: str


class MenuListResponse(BaseModel):
    menus: list[MenuItem]


class TranscriptionResponse(BaseModel):
    text: str
    provider: str
    model: str
    latency_ms: int = Field(ge=0)
