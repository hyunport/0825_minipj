"""Workflow와 Agent가 공유하는 검증된 Kiosk Tool입니다."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.repositories.kiosk_repository import kiosk_repository
from app.schemas.kiosk import CartItem, OrderOption


class SearchMenuArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str = Field(min_length=1, max_length=1000)


class CalculateOrderArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    menu_id: str = Field(min_length=1, max_length=20)
    option: OrderOption
    quantity: int = Field(ge=1, le=20)


class CreateOrderArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action_id: str = Field(min_length=1, max_length=100)


ToolFunction = Callable[[BaseModel, str | None], dict[str, Any]]


@dataclass(frozen=True)
class KioskToolSpec:
    name: str
    description: str
    input_model: type[BaseModel]
    function: ToolFunction


def _search_menu(arguments: BaseModel, _session_id: str | None) -> dict[str, Any]:
    values = SearchMenuArgs.model_validate(arguments)
    matches = kiosk_repository.search_menu(values.query)
    return {"matches": [menu.model_dump(exclude={"active"}) for menu in matches]}


def _calculate_order(arguments: BaseModel, _session_id: str | None) -> dict[str, Any]:
    values = CalculateOrderArgs.model_validate(arguments)
    menu = kiosk_repository.get_menu(values.menu_id)
    if menu is None:
        raise ValueError("존재하지 않거나 판매 중이 아닌 메뉴입니다.")
    unit_price = menu.single_price if values.option == "single" else menu.set_price
    return CartItem(
        menu_id=menu.menu_id,
        menu_name=menu.name,
        option=values.option,
        quantity=values.quantity,
        unit_price=unit_price,
        line_total=unit_price * values.quantity,
    ).model_dump()


def _create_order(arguments: BaseModel, session_id: str | None) -> dict[str, Any]:
    values = CreateOrderArgs.model_validate(arguments)
    if not session_id:
        raise ValueError("주문 확인에 session_id가 필요합니다.")
    result = kiosk_repository.create_order_from_pending(values.action_id, session_id)
    if result is None:
        raise ValueError("만료되었거나 올바르지 않은 action_id입니다.")
    return result


KIOSK_TOOL_REGISTRY: dict[str, KioskToolSpec] = {
    "search_menu": KioskToolSpec("search_menu", "메뉴명, 별칭, 설명으로 메뉴를 검색합니다.", SearchMenuArgs, _search_menu),
    "calculate_order": KioskToolSpec("calculate_order", "DB 가격으로 주문 금액을 계산합니다.", CalculateOrderArgs, _calculate_order),
    "create_order": KioskToolSpec("create_order", "확인된 pending action의 주문을 한 번 저장합니다.", CreateOrderArgs, _create_order),
}

ALLOWED_KIOSK_TOOLS = set(KIOSK_TOOL_REGISTRY)


def execute_kiosk_tool(name: str, arguments: dict[str, Any], session_id: str | None = None) -> dict[str, Any]:
    """Allowlist 확인과 입력 검증 후 Tool을 실행하고 공통 Envelope로 반환합니다."""
    tool = KIOSK_TOOL_REGISTRY.get(name)
    if tool is None:
        return {"success": False, "tool_name": name, "data": None, "error": {"code": "TOOL_NOT_ALLOWED", "message": "허용되지 않은 Tool입니다."}}
    try:
        validated = tool.input_model.model_validate(arguments)
        return {"success": True, "tool_name": name, "data": tool.function(validated, session_id), "error": None}
    except ValidationError as error:
        return {"success": False, "tool_name": name, "data": None, "error": {"code": "TOOL_VALIDATION_ERROR", "details": error.errors(include_url=False)}}
    except Exception as error:
        return {"success": False, "tool_name": name, "data": None, "error": {"code": "TOOL_EXECUTION_ERROR", "message": str(error)}}
