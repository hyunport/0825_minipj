"""Ollama 결정을 제한된 Tool Loop로 실행하는 Agent Service입니다."""

from typing import Any

from app.agents.hamburger_order_agent import ALLOWED_AGENT_ACTIONS, decide_kiosk_action
from app.core.config import settings
from app.repositories.kiosk_repository import kiosk_repository
from app.schemas.kiosk import CartItem, KioskOrderRequest, KioskOrderResponse, ToolCall, TraceItem
from app.services.kiosk_workflow_service import confirm_pending_order, extract_order_values, option_label
from app.tools.kiosk_tools import execute_kiosk_tool


KIOSK_AGENT_MAX_STEPS_DEFAULT = 6


def run_agent(payload: KioskOrderRequest) -> KioskOrderResponse:
    if payload.confirmed:
        return confirm_pending_order(payload)

    state = kiosk_repository.get_session(payload.session_id)
    parsed = extract_order_values(payload.message)
    state.update({key: value for key, value in parsed.items() if value is not None})
    context = [menu.model_dump() for menu in kiosk_repository.search_menu(payload.message)]
    tool_calls: list[ToolCall] = []
    trace: list[TraceItem] = []
    last_tool_result: dict[str, Any] | None = None

    for step in range(1, settings.kiosk_agent_max_steps + 1):
        try:
            decision = decide_kiosk_action(payload.message, state, context, last_tool_result)
        except Exception:
            return _agent_error(payload, trace, "AI Agent에 연결하지 못했습니다.", "agent_unavailable")

        trace.append(TraceItem(step=step, stage="agent_decision", data={"action": decision.action, "tool_name": decision.tool_name, "reason": decision.reason}))
        if decision.action not in ALLOWED_AGENT_ACTIONS:
            return _agent_error(payload, trace, "허용되지 않은 Agent 행동입니다.", "tool_error")

        # Backend 정책: 금액 계산이 끝난 뒤 같은 Tool을 다시 고르면 Step만 소모하므로
        # 확인 단계로 넘깁니다. Agent 결정은 Trace에 그대로 남깁니다.
        if decision.action in {"search_menu", "calculate_order"} and state.get("cart"):
            trace.append(TraceItem(step=step, stage="backend_policy", data={"rule": "cart_ready_skip_tool", "skipped": decision.action}))
            decision = decision.model_copy(update={"action": "request_confirmation"})

        if decision.action == "ask_clarification":
            kiosk_repository.update_session(payload.session_id, state)
            return KioskOrderResponse(
                mode=payload.mode,
                session_id=payload.session_id,
                status="needs_clarification",
                answer=decision.question or "메뉴, 단품 또는 세트, 수량을 알려주세요.",
                tool_calls=tool_calls,
                trace=trace,
                termination_reason="needs_user_input",
            )

        if decision.action == "search_menu":
            result = execute_kiosk_tool("search_menu", {"query": payload.message})
            tool_calls.append(ToolCall(tool="search_menu", arguments={"query": payload.message}))
            trace.append(TraceItem(step=step, stage="tool_execution", data={"tool_name": "search_menu", "success": result["success"]}))
            if not result["success"]:
                return _agent_error(payload, trace, "메뉴를 검색하지 못했습니다.", "tool_error", tool_calls)
            matches = result["data"]["matches"]
            if matches:
                state.update({"menu_id": matches[0]["menu_id"], "menu_name": matches[0]["name"]})
            last_tool_result = result
            continue

        if decision.action == "calculate_order":
            required = ("menu_id", "option", "quantity")
            if any(not state.get(name) for name in required):
                return _agent_error(payload, trace, "주문 정보가 부족합니다.", "tool_error", tool_calls)
            arguments = {name: state[name] for name in required}
            result = execute_kiosk_tool("calculate_order", arguments)
            tool_calls.append(ToolCall(tool="calculate_order", arguments=arguments))
            trace.append(TraceItem(step=step, stage="tool_execution", data={"tool_name": "calculate_order", "success": result["success"]}))
            if not result["success"]:
                return _agent_error(payload, trace, "주문 금액을 계산하지 못했습니다.", "tool_error", tool_calls)
            state["cart"] = [result["data"]]
            last_tool_result = result
            continue

        if decision.action in {"request_confirmation", "finish"}:
            if not state.get("cart"):
                required = ("menu_id", "option", "quantity")
                if not state.get("menu_id"):
                    # Backend 정책: 메뉴를 검색하지 않고 확인을 요청하면 읽기 전용 search_menu를 먼저 실행합니다.
                    result = execute_kiosk_tool("search_menu", {"query": payload.message})
                    tool_calls.append(ToolCall(tool="search_menu", arguments={"query": payload.message}))
                    trace.append(TraceItem(step=step, stage="backend_policy", data={"rule": "search_before_confirmation"}))
                    trace.append(TraceItem(step=step, stage="tool_execution", data={"tool_name": "search_menu", "success": result["success"]}))
                    matches = result["data"]["matches"] if result["success"] else []
                    if matches:
                        state.update({"menu_id": matches[0]["menu_id"], "menu_name": matches[0]["name"]})
                missing = [name for name in required if not state.get(name)]
                if missing:
                    # Backend 정책: 필수값이 없는데 확인을 요청하면 임의 기본값 대신 재질문합니다.
                    labels = {"menu_id": "메뉴", "option": "단품 또는 세트", "quantity": "수량"}
                    trace.append(TraceItem(step=step, stage="backend_policy", data={"rule": "missing_values_ask_clarification", "missing": missing}))
                    kiosk_repository.update_session(payload.session_id, state)
                    return KioskOrderResponse(
                        mode=payload.mode,
                        session_id=payload.session_id,
                        status="needs_clarification",
                        answer=f"{', '.join(labels[name] for name in missing)}을 알려주세요.",
                        tool_calls=tool_calls,
                        trace=trace,
                        termination_reason="needs_user_input",
                    )
                # Backend 정책: 금액은 Agent가 아니라 calculate_order Tool이 DB 가격으로 만듭니다.
                arguments = {name: state[name] for name in required}
                result = execute_kiosk_tool("calculate_order", arguments)
                tool_calls.append(ToolCall(tool="calculate_order", arguments=arguments))
                trace.append(TraceItem(step=step, stage="backend_policy", data={"rule": "calculate_before_confirmation"}))
                trace.append(TraceItem(step=step, stage="tool_execution", data={"tool_name": "calculate_order", "success": result["success"]}))
                if not result["success"]:
                    return _agent_error(payload, trace, "주문 금액을 계산하지 못했습니다.", "tool_error", tool_calls)
                state["cart"] = [result["data"]]
            cart = [CartItem.model_validate(item) for item in state["cart"]]
            total_price = sum(item.line_total for item in cart)
            action_id = kiosk_repository.create_pending_action(payload.session_id, payload.mode, cart, total_price)
            kiosk_repository.update_session(payload.session_id, state)
            item = cart[0]
            return KioskOrderResponse(
                mode=payload.mode,
                session_id=payload.session_id,
                status="confirmation_required",
                answer=f"{item.menu_name} {option_label(item.option)} {item.quantity}개, 총 {total_price:,}원입니다. 주문하시겠습니까?",
                cart=cart,
                total_price=total_price,
                action_id=action_id,
                tool_calls=tool_calls,
                trace=trace,
                termination_reason="confirmation_required",
            )

    return _agent_error(payload, trace, "Agent가 최대 실행 횟수에 도달했습니다.", "agent_max_steps", tool_calls)


def _agent_error(
    payload: KioskOrderRequest,
    trace: list[TraceItem],
    answer: str,
    termination_reason: str,
    tool_calls: list[ToolCall] | None = None,
) -> KioskOrderResponse:
    return KioskOrderResponse(
        mode=payload.mode,
        session_id=payload.session_id,
        status="error",
        answer=answer,
        tool_calls=tool_calls or [],
        trace=trace or [TraceItem(step=1, stage="agent_error", data={})],
        termination_reason=termination_reason,
    )
