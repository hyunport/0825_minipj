"""햄버거 주문 Agent의 Prompt와 Structured Output 결정 계약입니다."""

import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.core.config import settings
from app.providers.registry import get_provider


AgentAction = Literal[
    "ask_clarification",
    "search_menu",
    "calculate_order",
    "request_confirmation",
    "finish",
]

ALLOWED_AGENT_ACTIONS = {
    "ask_clarification",
    "search_menu",
    "calculate_order",
    "request_confirmation",
    "finish",
}


class KioskAgentDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: AgentAction
    tool_name: str | None = None
    arguments: dict[str, Any] = Field(default_factory=dict)
    question: str = ""
    reason: str = ""


SYSTEM_PROMPT = """당신은 햄버거 주문의 다음 한 단계만 결정하는 Agent입니다.
허용 행동은 ask_clarification, search_menu, calculate_order,
request_confirmation, finish뿐입니다. 허용 Tool은 search_menu와 calculate_order뿐입니다.
메뉴, option(single/set), quantity 중 하나라도 없으면 값을 추측하지 마세요.
가격을 만들거나 SQL을 작성하거나 create_order를 선택하지 마세요.
사용자 확인 전에는 저장 행동을 선택하지 마세요."""


def decide_kiosk_action(
    message: str,
    state: dict[str, Any],
    search_context: list[dict[str, Any]],
    last_tool_result: dict[str, Any] | None,
) -> KioskAgentDecision:
    """Mock에서는 결정적으로, 실제 모드에서는 Ollama Structured Output으로 결정합니다."""
    if settings.llm_provider == "mock":
        return _mock_decision(message, state, search_context)

    provider = get_provider("ollama")
    agent_input = json.dumps(
        {
            "message": message,
            "state": state,
            "search_context": search_context,
            "allowed_tools": ["search_menu", "calculate_order"],
            "last_tool_result": last_tool_result,
        },
        ensure_ascii=False,
    )
    result = provider.generate_structured(SYSTEM_PROMPT, agent_input, KioskAgentDecision)
    return KioskAgentDecision.model_validate(result.content)


def _mock_decision(message: str, state: dict[str, Any], search_context: list[dict[str, Any]]) -> KioskAgentDecision:
    if not state.get("menu_id") and search_context:
        return KioskAgentDecision(action="search_menu", tool_name="search_menu", arguments={"query": message}, reason="검색 문맥에서 메뉴 후보 확인")
    missing = [name for name in ("menu_id", "option", "quantity") if not state.get(name)]
    if missing:
        labels = {"menu_id": "메뉴", "option": "단품 또는 세트", "quantity": "수량"}
        return KioskAgentDecision(action="ask_clarification", question=f"{', '.join(labels[name] for name in missing)}을 알려주세요.", reason="주문 필수값 부족")
    if not state.get("cart"):
        return KioskAgentDecision(
            action="calculate_order",
            tool_name="calculate_order",
            arguments={"menu_id": state["menu_id"], "option": state["option"], "quantity": state["quantity"]},
            reason="필수값 확인 완료",
        )
    return KioskAgentDecision(action="request_confirmation", reason="금액 계산 완료")
