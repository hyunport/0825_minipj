"""Ollama 없이 정해진 순서로 주문을 처리하는 Workflow Service입니다."""

import re
from typing import Any

from app.repositories.kiosk_repository import kiosk_repository
from app.schemas.kiosk import CartItem, KioskOrderRequest, KioskOrderResponse, ToolCall, TraceItem
from app.tools.kiosk_tools import execute_kiosk_tool


KOREAN_QUANTITIES = {
    "한": 1,
    "하나": 1,
    "두": 2,
    "둘": 2,
    "세": 3,
    "셋": 3,
}


def run_workflow(payload: KioskOrderRequest) -> KioskOrderResponse:
    if payload.confirmed:
        return confirm_pending_order(payload)

    state = kiosk_repository.get_session(payload.session_id)
    parsed = extract_order_values(payload.message)
    state.update({key: value for key, value in parsed.items() if value is not None})

    search_result = execute_kiosk_tool("search_menu", {"query": payload.message})
    matches = search_result.get("data", {}).get("matches", []) if search_result["success"] else []
    if matches:
        state["menu_id"] = matches[0]["menu_id"]
        state["menu_name"] = matches[0]["name"]
    kiosk_repository.update_session(payload.session_id, state)

    missing = [name for name in ("menu_id", "option", "quantity") if not state.get(name)]
    if missing:
        return _clarification_response(payload, state, missing)

    calculation = execute_kiosk_tool(
        "calculate_order",
        {"menu_id": state["menu_id"], "option": state["option"], "quantity": state["quantity"]},
    )
    if not calculation["success"]:
        return _error_response(payload, "주문 금액을 계산하지 못했습니다.", calculation)

    cart_item = CartItem.model_validate(calculation["data"])
    action_id = kiosk_repository.create_pending_action(payload.session_id, payload.mode, [cart_item], cart_item.line_total)
    return KioskOrderResponse(
        mode=payload.mode,
        session_id=payload.session_id,
        status="confirmation_required",
        answer=f"{cart_item.menu_name} {option_label(cart_item.option)} {cart_item.quantity}개, 총 {cart_item.line_total:,}원입니다. 주문하시겠습니까?",
        cart=[cart_item],
        total_price=cart_item.line_total,
        action_id=action_id,
        tool_calls=[
            ToolCall(tool="search_menu", arguments={"query": payload.message}),
            ToolCall(tool="calculate_order", arguments={"menu_id": state["menu_id"], "option": state["option"], "quantity": state["quantity"]}),
        ],
        trace=[
            TraceItem(step=1, stage="workflow_parse", data={"menu_id": state["menu_id"], "option": state["option"], "quantity": state["quantity"]}),
            TraceItem(step=2, stage="tool_execution", data={"tool_name": "search_menu", "success": search_result["success"]}),
            TraceItem(step=3, stage="tool_execution", data={"tool_name": "calculate_order", "success": True}),
            TraceItem(step=4, stage="pending_action_created", data={}),
        ],
        termination_reason="confirmation_required",
    )


def confirm_pending_order(payload: KioskOrderRequest) -> KioskOrderResponse:
    if not payload.action_id:
        return _rejected_response(payload)
    result = execute_kiosk_tool("create_order", {"action_id": payload.action_id}, session_id=payload.session_id)
    if not result["success"]:
        return _rejected_response(payload)
    data = result["data"]
    cart = [CartItem.model_validate(item) for item in data["cart"]]
    return KioskOrderResponse(
        mode=payload.mode,
        session_id=payload.session_id,
        status="completed",
        answer=f"주문이 완료되었습니다. 주문번호는 {data['order_number']}입니다.",
        cart=cart,
        total_price=data["total_price"],
        order_number=data["order_number"],
        tool_calls=[ToolCall(tool="create_order", arguments={"action_id": payload.action_id})],
        trace=[TraceItem(step=1, stage="confirmed_tool_execution", data={"success": True})],
        termination_reason="completed",
    )


def extract_order_values(message: str) -> dict[str, Any]:
    compact = "".join(message.split())
    option = "set" if "세트" in compact else "single" if "단품" in compact else None
    quantity: int | None = None
    digit_match = re.search(r"(\d+)\s*개?", message)
    if digit_match:
        quantity = int(digit_match.group(1))
    else:
        word_match = re.search(r"(하나|한|둘|두|셋|세)\s*개", message)
        if word_match:
            quantity = KOREAN_QUANTITIES[word_match.group(1)]
    if quantity is not None and not 1 <= quantity <= 20:
        quantity = None
    return {"option": option, "quantity": quantity}


def _clarification_response(payload: KioskOrderRequest, state: dict[str, Any], missing: list[str]) -> KioskOrderResponse:
    labels = {"menu_id": "메뉴", "option": "단품 또는 세트", "quantity": "수량"}
    question = ", ".join(labels[name] for name in missing)
    return KioskOrderResponse(
        mode=payload.mode,
        session_id=payload.session_id,
        status="needs_clarification",
        answer=f"{question}을 알려주세요.",
        trace=[TraceItem(step=1, stage="workflow_parse", data={key: state.get(key) for key in ("menu_id", "option", "quantity")})],
        termination_reason="needs_user_input",
    )


def _rejected_response(payload: KioskOrderRequest) -> KioskOrderResponse:
    return KioskOrderResponse(
        mode=payload.mode,
        session_id=payload.session_id,
        status="rejected",
        answer="만료되었거나 올바르지 않은 주문 확인 요청입니다.",
        trace=[TraceItem(step=1, stage="confirmed_tool_execution", data={"success": False})],
        termination_reason="invalid_action",
    )


def _error_response(payload: KioskOrderRequest, answer: str, tool_result: dict[str, Any]) -> KioskOrderResponse:
    return KioskOrderResponse(
        mode=payload.mode,
        session_id=payload.session_id,
        status="error",
        answer=answer,
        trace=[TraceItem(step=1, stage="tool_execution", data={"tool_name": tool_result["tool_name"], "success": False})],
        termination_reason="tool_error",
    )


def option_label(option: str) -> str:
    return "세트" if option == "set" else "단품"
