"""햄버거 키오스크 전용 Backend Client — 성엽님 담당."""

from core.api_client import request, upload


def get_kiosk_menus():
    return request("GET", "/api/kiosk/menu")


def transcribe_kiosk_audio(filename: str, content: bytes, content_type: str):
    files = {"audio": (filename, content, content_type)}
    return upload("/api/kiosk/transcribe", files, {})


def run_kiosk_order(
    mode: str,
    session_id: str,
    message: str,
    confirmed: bool = False,
    action_id: str | None = None,
):
    payload = {
        "mode": mode,
        "session_id": session_id,
        "message": message,
        "confirmed": confirmed,
        "action_id": action_id,
    }
    return request("POST", "/api/kiosk/order", json=payload)


def reset_kiosk_session():
    return request("POST", "/api/kiosk/reset", json={})
