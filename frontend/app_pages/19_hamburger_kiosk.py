"""햄버거 음성 키오스크 Page.

Frontend는 가격 계산이나 Tool 실행을 하지 않습니다. 마이크·텍스트 입력을 Backend
`/api/kiosk/*`에 전달하고, 확인 대기 상태에서는 Backend가 발급한 `action_id`만 다시
보내는 화면 역할만 담당합니다. Workflow와 AI Agent는 화면·버튼이 같고 요청의 `mode`
값만 다릅니다.
"""

import uuid

import streamlit as st
from clients.agent_client import get_health
from clients.kiosk_client import get_kiosk_menus, reset_kiosk_session, run_kiosk_order, transcribe_kiosk_audio
from core.api_client import BackendAPIError


MODE_LABELS = {"workflow": "Workflow", "agent": "AI Agent"}
OPTION_LABELS = {"single": "단품", "set": "세트"}
STATUS_LABELS = {
    "needs_clarification": "정보 부족 · 재질문",
    "confirmation_required": "고객 확인 대기",
    "completed": "주문 저장 완료",
    "rejected": "확인 요청 거절",
    "error": "오류",
}


# ---------- Session State ----------

def _new_session() -> None:
    """모드 전환이나 초기화 시 대화 상태를 새로 시작합니다."""
    st.session_state.kiosk_session_id = str(uuid.uuid4())
    st.session_state.kiosk_action_id = None
    st.session_state.kiosk_last_result = None
    st.session_state.kiosk_error = None


if "kiosk_session_id" not in st.session_state:
    _new_session()
st.session_state.setdefault("kiosk_mode", "workflow")
st.session_state.setdefault("kiosk_transcript", "")
st.session_state.setdefault("kiosk_stt_info", None)


def _on_mode_change() -> None:
    # 서로 다른 방식의 Backend Session 상태가 섞이지 않도록 새 session_id를 만듭니다.
    _new_session()


def _on_retry() -> None:
    st.session_state.kiosk_action_id = None
    st.session_state.kiosk_last_result = None
    st.session_state.kiosk_error = None
    st.session_state.kiosk_transcript = ""


def _on_reset() -> None:
    try:
        reset_kiosk_session()
    except BackendAPIError as error:
        st.session_state.kiosk_error = str(error)
    _new_session()
    st.session_state.kiosk_transcript = ""
    st.session_state.kiosk_stt_info = None


def _send_order(message: str, confirmed: bool, action_id: str | None) -> None:
    try:
        result = run_kiosk_order(st.session_state.kiosk_mode, st.session_state.kiosk_session_id, message, confirmed, action_id)
    except BackendAPIError as error:
        st.session_state.kiosk_error = str(error)
        return
    st.session_state.kiosk_error = None
    st.session_state.kiosk_last_result = result
    # confirmation_required일 때만 action_id를 보관하고, 그 외 상태에서는 제거합니다.
    st.session_state.kiosk_action_id = result.get("action_id") if result.get("status") == "confirmation_required" else None


# ---------- 1. 제목 / 2. 실행 모드 ----------

st.title("🍔 햄버거 음성 키오스크")
st.caption("마이크 또는 텍스트 → Backend Workflow / AI Agent → 공통 Tool → PostgreSQL")

st.radio(
    "실행 모드",
    options=list(MODE_LABELS),
    format_func=MODE_LABELS.get,
    horizontal=True,
    key="kiosk_mode",
    on_change=_on_mode_change,
    help="Workflow는 Backend 코드가 정해진 순서로, AI Agent는 Ollama가 다음 행동을 선택합니다. 화면과 버튼은 같습니다.",
)

# ---------- 3. Backend 연결 상태 / 4. 메뉴 ----------

status_col, menu_col = st.columns([1, 2])
with status_col:
    st.subheader("Backend 연결")
    try:
        health = get_health()
        st.success(f"연결됨 · {health.get('status', 'ok')}")
    except BackendAPIError as error:
        st.error(str(error))
    st.caption(f"session_id: `{st.session_state.kiosk_session_id[:8]}…` · mode: `{st.session_state.kiosk_mode}`")

with menu_col:
    st.subheader("메뉴")
    try:
        menus = get_kiosk_menus().get("menus", [])
        st.table(
            [
                {
                    "ID": menu["menu_id"],
                    "메뉴": menu["name"],
                    "설명": menu["description"],
                    "단품": f"{menu['single_price']:,}원",
                    "세트": f"{menu['set_price']:,}원",
                }
                for menu in menus
            ]
        )
    except BackendAPIError as error:
        st.error(f"메뉴를 불러오지 못했습니다: {error}")

st.divider()

# ---------- 5. 마이크 / 6. 음성 변환 / 7. 인식 결과 수정 ----------

st.subheader("주문 입력")
voice_col, text_col = st.columns([1, 1])

with voice_col:
    audio = st.audio_input("마이크 녹음 (선택)", key="kiosk_audio")
    if st.button("음성 변환", disabled=audio is None, use_container_width=True):
        try:
            with st.spinner("음성을 인식하는 중…"):
                stt = transcribe_kiosk_audio(
                    audio.name or "kiosk.wav",
                    audio.getvalue(),
                    audio.type or "audio/wav",
                )
            # text_area보다 먼저 실행되므로 인식 결과를 입력창 값으로 넣을 수 있습니다.
            st.session_state.kiosk_transcript = stt.get("text", "")
            st.session_state.kiosk_stt_info = stt
            st.session_state.kiosk_error = None
        except BackendAPIError as error:
            # STT 실패 시 입력창은 비우지 않고 오류만 표시합니다. 텍스트 주문은 계속 가능합니다.
            st.session_state.kiosk_error = f"음성 인식 실패: {error}"
    if st.session_state.kiosk_stt_info:
        info = st.session_state.kiosk_stt_info
        st.caption(f"STT: {info.get('provider')} / {info.get('model')} · {info.get('latency_ms')}ms")

with text_col:
    st.text_area(
        "주문 문장 (인식 결과를 수정하거나 직접 입력)",
        key="kiosk_transcript",
        height=120,
        placeholder="예) 불고기버거 세트 두 개 주세요",
    )

# ---------- 8. 주문 보내기 / 10. 확정·다시 입력 ----------

send_col, confirm_col, retry_col, reset_col = st.columns(4)
awaiting_confirmation = bool(st.session_state.kiosk_action_id)

send_clicked = send_col.button("주문 보내기", type="primary", use_container_width=True, disabled=awaiting_confirmation)
confirm_clicked = confirm_col.button("주문 확정", use_container_width=True, disabled=not awaiting_confirmation)
retry_col.button("다시 입력", use_container_width=True, on_click=_on_retry)
reset_col.button("대화 초기화", use_container_width=True, on_click=_on_reset, help="Backend 대화 상태를 초기화합니다. DB 주문 기록은 유지됩니다.")

if send_clicked:
    message = st.session_state.kiosk_transcript.strip()
    if not message:
        st.session_state.kiosk_error = "주문 문장을 입력하거나 음성을 변환해 주세요."
    else:
        with st.spinner(f"{MODE_LABELS[st.session_state.kiosk_mode]} 방식으로 주문을 처리하는 중…"):
            _send_order(message, confirmed=False, action_id=None)
        st.rerun()  # 버튼 활성/비활성 상태를 새 action_id 기준으로 다시 그립니다.

if confirm_clicked:
    # 확인 단계에서는 message를 다시 해석하지 않고 Backend가 발급한 action_id만 전달합니다.
    with st.spinner("주문을 저장하는 중…"):
        _send_order("주문할게요", confirmed=True, action_id=st.session_state.kiosk_action_id)
    st.rerun()

if st.session_state.kiosk_error:
    st.error(st.session_state.kiosk_error)

# ---------- 9. 답변 / 장바구니 / 총금액 ----------

result = st.session_state.kiosk_last_result
if result:
    status = result.get("status", "error")
    answer = result.get("answer", "")
    if status == "completed":
        st.success(answer)
    elif status == "confirmation_required":
        st.warning(answer)
        st.caption("위 내용이 맞으면 `주문 확정`, 아니면 `다시 입력`을 누르세요.")
    elif status == "needs_clarification":
        st.info(answer)
        st.caption("같은 대화에서 부족한 정보만 추가로 입력하고 다시 `주문 보내기`를 누르세요.")
    else:
        st.error(answer)

    left, right = st.columns([2, 1])
    with left:
        st.subheader("장바구니")
        cart = result.get("cart", [])
        if cart:
            st.table(
                [
                    {
                        "메뉴": item["menu_name"],
                        "옵션": OPTION_LABELS.get(item["option"], item["option"]),
                        "수량": item["quantity"],
                        "단가": f"{item['unit_price']:,}원",
                        "금액": f"{item['line_total']:,}원",
                    }
                    for item in cart
                ]
            )
        else:
            st.caption("장바구니가 비어 있습니다.")
    with right:
        st.metric("총금액", f"{result.get('total_price', 0):,}원")
        st.write(f"상태: **{STATUS_LABELS.get(status, status)}**")
        if result.get("order_number"):
            st.write(f"주문번호: **{result['order_number']}**")
        if result.get("action_id"):
            st.caption(f"action_id: `{result['action_id']}`")

    # ---------- 11. Tool Calls / Trace / termination_reason ----------

    with st.expander(f"Tool Calls ({len(result.get('tool_calls', []))})", expanded=False):
        st.json(result.get("tool_calls", []))
    with st.expander(f"Trace ({len(result.get('trace', []))}) · {MODE_LABELS.get(result.get('mode'), '')}", expanded=False):
        st.json(result.get("trace", []))
    with st.expander("termination_reason", expanded=False):
        st.code(result.get("termination_reason", ""))
