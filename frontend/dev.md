# Frontend 개발 명세 — 성엽님

## 1. 목표

기존 Streamlit 앱에 햄버거 음성 키오스크 Page를 추가한다. Workflow와 AI Agent의
고객 기능은 동일하고, 실행 모드와 Trace만 비교할 수 있게 한다.

공통 계약은 루트의 [`공통 API.md`](../공통%20API.md)를 그대로 사용한다.

## 2. 수정 가능한 파일

- `frontend/app.py`
- `frontend/app_pages/19_hamburger_kiosk.py`
- `frontend/clients/kiosk_client.py`
- Frontend 전용 이미지가 필요하면 `frontend/assets/kiosk/**` 신규 생성

## 3. 수정하면 안 되는 파일

- `backend/**`
- `db/**`
- `PLAN.md`
- `공통 API.md`
- 루트 `.env`, `.env.example`, `requirements.txt`
- `frontend/core/api_client.py`
- 기존 `frontend/app_pages/01_*`부터 `18_*`까지
- 기존 `frontend/clients/agent_client.py`

API 필드가 불편하더라도 Frontend에서 이름을 바꾸지 말고 오현님에게 계약 변경을
요청한다. Backend나 DB 파일을 임시로 수정해 문제를 해결하지 않는다.

## 4. 구현할 화면

`19_hamburger_kiosk.py` 한 Page 안에 아래 순서로 배치한다.

1. 제목: `햄버거 음성 키오스크`
2. 실행 모드: `Workflow`, `AI Agent`
3. Backend 연결 상태
4. DB에서 받은 메뉴와 가격
5. `st.audio_input` 마이크 녹음
6. `음성 변환` 버튼
7. 인식 결과를 수정할 수 있는 `st.text_area`
8. `주문 보내기` 버튼
9. Backend의 `answer`, 장바구니, 총금액
10. 확인 대기 시 `주문 확정`, `다시 입력` 버튼
11. `Tool Calls`, `Trace`, `termination_reason` Expander

두 모드의 화면 배치와 버튼은 같아야 한다. 모드 값만 `workflow` 또는 `agent`로 보낸다.

## 5. Session State

최소한 다음 Key를 사용한다.

```python
kiosk_session_id       # 최초 한 번 UUID 생성
kiosk_mode             # workflow 또는 agent
kiosk_transcript       # STT 결과와 사용자 수정 문장
kiosk_action_id        # Backend가 발급한 확인 대기 ID
kiosk_last_result      # 마지막 공통 응답
```

`mode`를 바꾸면 새 `session_id`를 생성하고 기존 `action_id`를 제거한다. 서로 다른 방식의
대화 상태가 섞이지 않게 한다.

## 6. API 연결

`frontend/clients/kiosk_client.py`에 다음 함수만 둔다.

```python
get_kiosk_menus()
transcribe_kiosk_audio(filename, content, content_type)
run_kiosk_order(mode, session_id, message, confirmed=False, action_id=None)
reset_kiosk_session()
```

실제 HTTP 처리는 기존 `frontend/core/api_client.py`의 `request`, `upload`를 재사용한다.
URL을 코드에 직접 쓰지 않는다.

## 7. 음성 실패 처리

- 마이크가 없어도 텍스트 입력은 항상 사용할 수 있어야 한다.
- STT가 503을 반환하면 오류를 보여주고 입력창을 비우지 않는다.
- 인식 문장을 사용자가 수정한 뒤 주문할 수 있게 한다.
- 녹음 파일을 로컬 디스크에 저장하지 않는다.
- TTS는 시간이 남을 때 기존 API를 재사용하며 필수 완료 조건이 아니다.

## 8. Backend 미완성 시 개발용 응답

화면 개발 중에는 아래 값을 Page 내부의 임시 함수로 사용해도 된다. 단, 최종 제출 전
임시 함수 호출은 제거하고 `kiosk_client.py`를 연결한다.

```python
{
    "mode": "workflow",
    "session_id": "frontend-test",
    "status": "confirmation_required",
    "answer": "불고기버거 세트 2개, 총 15,000원입니다. 주문하시겠습니까?",
    "cart": [{
        "menu_id": "B001",
        "menu_name": "불고기버거",
        "option": "set",
        "quantity": 2,
        "unit_price": 7500,
        "line_total": 15000,
    }],
    "total_price": 15000,
    "action_id": "frontend-mock-action",
    "order_number": None,
    "tool_calls": [],
    "trace": [],
    "termination_reason": "confirmation_required",
}
```

## 9. `frontend/app.py` 변경 범위

기존 Page 등록은 유지하고 아래 두 작업만 추가한다.

```python
hamburger_kiosk = st.Page(
    "app_pages/19_hamburger_kiosk.py",
    title="햄버거 음성 키오스크",
)
```

- `st.navigation(...)` 목록에 `hamburger_kiosk` 추가
- Sidebar에 `st.page_link(hamburger_kiosk, ...)` 추가

기존 Page의 순서, 이름, 링크를 삭제하거나 변경하지 않는다.

## 10. 환경과 실행

Windows PowerShell에서 프로젝트 루트 기준:

```powershell
.\.venv\Scripts\Activate.ps1
$env:BACKEND_API_URL="http://<INHYE_BACKEND_IP>:8000"
streamlit run .\frontend\app.py --server.address 0.0.0.0 --server.port 8501
```

같은 PC에서 Backend를 테스트할 때만 `http://127.0.0.1:8000`을 사용한다.

## 11. 완료 체크

- [x] 기존 Streamlit Page가 그대로 열린다.
- [x] 햄버거 키오스크 Page가 Sidebar에서 열린다.
- [x] DB 메뉴 세 개가 표시된다.
- [x] 모드 변경 시 주문 UI는 같고 요청 `mode`만 바뀐다.
- [x] 마이크 없이 텍스트 주문이 가능하다.
- [x] STT 결과를 수정할 수 있다.
- [x] `needs_clarification` 응답 후 같은 Session으로 추가 답변을 보낸다.
- [x] `confirmation_required`에서 `action_id`를 보관한다.
- [x] 확정 버튼이 `confirmed=true`와 해당 `action_id`를 보낸다.
- [x] 장바구니, 총금액, 주문번호가 표시된다.
- [x] Tool Calls와 Trace를 접어서 확인할 수 있다.
- [x] Backend 오류가 나도 Streamlit 앱 전체가 종료되지 않는다.

2026-08-26 검증: VPS에서 Backend(맥 PG `:5432` + Ollama `llama3.2`)에 붙여 Streamlit AppTest로
위 항목 전부 확인. Workflow·Agent 모두 대표 문장 15,000원 → 확정 → `orders` 저장까지 통과.
