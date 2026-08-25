from fastapi.testclient import TestClient

from app.agents.hamburger_order_agent import KioskAgentDecision
from app.main import app
from app.repositories.kiosk_repository import kiosk_repository
from app.services import kiosk_agent_service
from app.tools.kiosk_tools import execute_kiosk_tool


client = TestClient(app)


def setup_function() -> None:
    kiosk_repository.reset_all_for_test()


def order(mode: str, session_id: str, message: str, confirmed: bool = False, action_id: str | None = None):
    return client.post(
        "/api/kiosk/order",
        json={"mode": mode, "session_id": session_id, "message": message, "confirmed": confirmed, "action_id": action_id},
    )


def test_menu_returns_three_fixed_items() -> None:
    response = client.get("/api/kiosk/menu")
    assert response.status_code == 200
    assert [menu["menu_id"] for menu in response.json()["menus"]] == ["B001", "B002", "B003"]


def test_workflow_calculates_15000_and_saves_only_after_confirmation() -> None:
    prepared = order("workflow", "workflow-1", "불고기버거 세트 두 개 주세요").json()
    assert prepared["status"] == "confirmation_required"
    assert prepared["total_price"] == 15000
    assert kiosk_repository.mock_order_count() == 0

    completed = order("workflow", "workflow-1", "주문할게요", True, prepared["action_id"]).json()
    assert completed["status"] == "completed"
    assert completed["order_number"] == "K000001"
    assert kiosk_repository.mock_order_count() == 1


def test_pending_action_can_be_used_only_once() -> None:
    prepared = order("workflow", "once", "불고기버거 세트 두 개 주세요").json()
    first = order("workflow", "once", "확인", True, prepared["action_id"]).json()
    second = order("workflow", "once", "다시 확인", True, prepared["action_id"]).json()
    assert first["status"] == "completed"
    assert second["status"] == "rejected"
    assert second["termination_reason"] == "invalid_action"
    assert kiosk_repository.mock_order_count() == 1


def test_workflow_merges_missing_values_in_same_session() -> None:
    first = order("workflow", "merge", "불고기버거 주세요").json()
    second = order("workflow", "merge", "세트 두 개요").json()
    assert first["status"] == "needs_clarification"
    assert second["status"] == "confirmation_required"
    assert second["cart"][0]["menu_id"] == "B001"
    assert second["total_price"] == 15000


def test_mock_agent_matches_workflow_cart_and_total() -> None:
    workflow = order("workflow", "wf", "불고기버거 세트 두 개 주세요").json()
    agent = order("agent", "agent", "불고기버거 세트 두 개 주세요").json()
    assert agent["status"] == "confirmation_required"
    assert agent["cart"] == workflow["cart"]
    assert agent["total_price"] == workflow["total_price"] == 15000
    assert any(item["stage"] == "agent_decision" for item in agent["trace"])


def test_unknown_tool_is_blocked() -> None:
    result = execute_kiosk_tool("delete_database", {})
    assert result["success"] is False
    assert result["error"]["code"] == "TOOL_NOT_ALLOWED"


def test_agent_stops_at_max_steps(monkeypatch) -> None:
    monkeypatch.setattr(
        kiosk_agent_service,
        "decide_kiosk_action",
        lambda *_args: KioskAgentDecision(action="search_menu", tool_name="search_menu", arguments={"query": "불고기"}),
    )
    response = order("agent", "max", "불고기버거 세트 두 개 주세요").json()
    assert response["status"] == "error"
    assert response["termination_reason"] == "agent_max_steps"


def test_agent_failure_is_not_changed_to_workflow_success(monkeypatch) -> None:
    def unavailable(*_args):
        raise ConnectionError("Ollama unavailable")

    monkeypatch.setattr(kiosk_agent_service, "decide_kiosk_action", unavailable)
    response = order("agent", "down", "불고기버거 세트 두 개 주세요").json()
    assert response["status"] == "error"
    assert response["termination_reason"] == "agent_unavailable"
    assert response["total_price"] == 0


def test_transcribe_rejects_non_wav_file() -> None:
    response = client.post("/api/kiosk/transcribe", files={"audio": ("audio.txt", b"not wav", "text/plain")})
    assert response.status_code == 422


def test_reset_keeps_saved_orders_but_clears_pending_action() -> None:
    prepared = order("workflow", "reset", "불고기버거 세트 두 개 주세요").json()
    response = client.post("/api/kiosk/reset")
    rejected = order("workflow", "reset", "확인", True, prepared["action_id"]).json()
    assert response.json()["reset"] is True
    assert rejected["status"] == "rejected"
