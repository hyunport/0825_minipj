"""Workflow와 Agent가 공유하는 햄버거 키오스크 Tool 뼈대."""


ALLOWED_KIOSK_TOOLS = {
    "search_menu",
    "calculate_order",
    "create_order",
}


# TODO(inhye): Pydantic arguments, ToolSpec, Registry, 안전 실행 함수 구현
