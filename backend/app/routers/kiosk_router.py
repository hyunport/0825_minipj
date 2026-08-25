"""햄버거 키오스크 HTTP 진입점 뼈대.

인혜님이 `backend/dev.md`와 `공통 API.md`에 맞춰 구현하고 `app.main`에 등록합니다.
현재는 기존 앱 실행에 영향을 주지 않도록 아직 등록하지 않았습니다.
"""

from fastapi import APIRouter


kiosk_router = APIRouter(prefix="/api/kiosk", tags=["04 · 햄버거 키오스크"])


# TODO(inhye): GET /menu, POST /transcribe, POST /order, POST /reset 구현
