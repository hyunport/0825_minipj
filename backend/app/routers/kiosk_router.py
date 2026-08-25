"""햄버거 키오스크의 HTTP 요청·응답과 오류 변환만 담당합니다."""

from fastapi import APIRouter, File, HTTPException, UploadFile

from app.repositories.kiosk_repository import kiosk_repository
from app.schemas.kiosk import KioskOrderRequest, KioskOrderResponse, MenuListResponse, TranscriptionResponse
from app.services.kiosk_agent_service import run_agent
from app.services.kiosk_speech_service import InvalidAudioError, SpeechModelUnavailableError, transcribe_wav
from app.services.kiosk_workflow_service import run_workflow


kiosk_router = APIRouter(prefix="/api/kiosk", tags=["04 · 햄버거 키오스크"])


@kiosk_router.get("/menu", response_model=MenuListResponse)
def get_menu() -> MenuListResponse:
    try:
        return MenuListResponse(menus=kiosk_repository.list_menus())
    except Exception as error:
        raise HTTPException(status_code=502, detail="메뉴 DB에 연결하지 못했습니다.") from error


@kiosk_router.post("/transcribe", response_model=TranscriptionResponse)
async def transcribe_audio(audio: UploadFile = File(...)) -> TranscriptionResponse:
    data = await audio.read()
    try:
        return transcribe_wav(data, audio.content_type)
    except InvalidAudioError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except SpeechModelUnavailableError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


@kiosk_router.post("/order", response_model=KioskOrderResponse)
def order(payload: KioskOrderRequest) -> KioskOrderResponse:
    try:
        return run_workflow(payload) if payload.mode == "workflow" else run_agent(payload)
    except Exception as error:
        raise HTTPException(status_code=502, detail="Kiosk 주문 처리에 실패했습니다.") from error


@kiosk_router.post("/reset")
def reset_kiosk() -> dict[str, object]:
    kiosk_repository.reset_runtime_state()
    return {"reset": True, "note": "키오스크 대화 상태를 초기화했습니다."}
