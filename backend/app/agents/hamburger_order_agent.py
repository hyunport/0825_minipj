"""햄버거 주문 Agent의 Prompt와 Structured Output 결정 계약 뼈대."""


ALLOWED_AGENT_ACTIONS = {
    "ask_clarification",
    "search_menu",
    "calculate_order",
    "request_confirmation",
    "finish",
}


# TODO(inhye): Ollama Structured Output과 Pydantic 결정 모델 구현
