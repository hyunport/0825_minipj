# Backend 개발 명세 — 인혜님

## 1. 목표

기존 FastAPI 앱에 햄버거 키오스크 API를 추가한다. Workflow와 AI Agent가 같은 Schema,
Tool, Repository를 사용하고 진행 순서만 다르게 구현한다.

공통 계약은 루트의 [`공통 API.md`](../공통%20API.md)를 그대로 사용한다.

## 2. 수정 가능한 파일

- `backend/app/main.py`: Kiosk Router 등록만 추가
- `backend/app/core/config.py`: Kiosk 환경변수만 추가
- `backend/app/agents/hamburger_order_agent.py`
- `backend/app/repositories/kiosk_repository.py`
- `backend/app/routers/kiosk_router.py`
- `backend/app/schemas/kiosk.py`
- `backend/app/services/kiosk_agent_service.py`
- `backend/app/services/kiosk_workflow_service.py`
- `backend/app/tools/kiosk_tools.py`
- 필요하면 `backend/app/services/kiosk_speech_service.py` 신규 생성
- `backend/tests/test_kiosk.py`
- 루트 `requirements.txt`: `psycopg[binary]`, `faster-whisper`만 추가 가능
- 루트 `.env.example`: Kiosk 환경변수만 추가 가능

## 3. 수정하면 안 되는 파일

- `frontend/**`
- `db/**`
- `PLAN.md`
- `공통 API.md`
- 실제 루트 `.env`
- 기존 `stage_01_router.py`, `stage_02_router.py`, `stage_03_router.py`
- 기존 `lab_router.py`, 기존 Lab Agent·Service·Tool·Repository
- 기존 테스트를 삭제하거나 기대값을 변경하는 작업

공통 계약 변경이 필요하면 Backend에서 임의로 바꾸지 말고 오현님에게 요청한다.

## 4. API 구현

`kiosk_router.py`에 다음 Endpoint를 구현한다.

```text
GET  /api/kiosk/menu
POST /api/kiosk/transcribe
POST /api/kiosk/order
POST /api/kiosk/reset
```

Router는 HTTP 요청·응답과 오류 변환만 담당한다. Workflow, Agent, DB SQL, Tool 실행을
Router에 직접 작성하지 않는다.

## 5. 공통 Schema

`schemas/kiosk.py`에 만들어 둔 모델을 기준으로 구현한다.

- `KioskOrderRequest`
- `KioskOrderResponse`
- `CartItem`
- `MenuItem`
- `ToolCall`
- `TraceItem`

새 필드가 필요해도 Frontend와 협의 없이 공통 응답 필드를 변경하지 않는다.

## 6. Repository

`kiosk_repository.py`가 다음 경계를 소유한다.

- DB 메뉴 목록 조회
- 이름·별칭·설명 기반 메뉴 검색
- 가격 조회
- 최종 주문과 주문 항목 Transaction 저장
- Backend 메모리 Session
- 120초 pending action 생성·조회·한 번 소비

개발 순서는 `KIOSK_DB_MODE=mock`으로 먼저 구현하고, 이후 `postgres` 연결을 추가한다.
PostgreSQL SQL은 `db/init` 파일을 수정하지 않고 현재 Schema에 맞춰 작성한다.

## 7. Workflow 구현

`kiosk_workflow_service.py`에서 다음 순서를 코드로 고정한다.

1. 메시지와 기존 Session 병합
2. 메뉴명·별칭 추출
3. 단품/세트 추출
4. 숫자와 `한/두/세 개` 수량 추출
5. 누락값이면 재질문
6. `search_menu`
7. `calculate_order`
8. pending action 발급
9. 확인 요청 반환
10. 확인 요청에서는 pending action 소비 후 `create_order`

Workflow 경로에서 Ollama를 호출하지 않는다. 이를 Trace와 테스트로 증명한다.

## 8. Agent 구현

`hamburger_order_agent.py`는 Ollama Structured Output으로 다음 행동 중 하나만 반환한다.

```text
ask_clarification
search_menu
calculate_order
request_confirmation
finish
```

Agent 입력:

- 현재 사용자 메시지
- 해당 `session_id`의 주문 상태
- 간이 RAG 검색 문맥
- 허용 Tool 설명
- 직전 Tool Result

Agent 제한:

- 최대 6 Step
- Allowlist에 없는 행동·Tool 거절
- 메뉴·옵션·수량 누락 시 임의 기본값 금지
- 가격 생성 금지
- SQL 실행 금지
- 확인 전 `create_order` 금지
- JSON/Pydantic 검증 실패는 `error` 또는 안전한 재질문
- Ollama 장애 시 Workflow로 조용히 대체하지 않고 `agent_unavailable` 반환

`kiosk_agent_service.py`가 반복, Tool 실행, 상태 병합, 종료와 Trace를 소유한다. Agent
파일은 판단 계약과 Prompt에 집중한다.

### 8-1. Backend 정책 가드 (2026-08-26 통합 테스트 반영)

실제 `llama3.2`는 Mock과 달리 순서를 자주 어겼다 (cart 없이 `request_confirmation`,
계산 뒤 `search_menu` 반복으로 6 Step 소진). Ollama 결정은 Trace에 그대로 남기되
Backend가 아래 정책으로 안전하게 마무리한다 (`stage: backend_policy`).

- `cart_ready_skip_tool`: 금액 계산이 끝났는데 Tool을 다시 고르면 확인 단계로 진행
- `search_before_confirmation`: menu_id 없이 확인 요청 → 읽기 전용 `search_menu` 먼저 실행
- `missing_values_ask_clarification`: 필수값 없이 확인 요청 → 임의 기본값 대신 재질문
- `calculate_before_confirmation`: cart 없이 확인 요청 → `calculate_order`로 DB 가격 계산

Prompt에는 `missing_fields`, `cart_ready`와 결정 규칙 4개를 추가했다. 가격 생성·SQL·
확인 전 저장 금지 원칙은 그대로다.

## 9. Tool 구현

`kiosk_tools.py`에 Pydantic 입력 모델과 Allowlist를 둔다.

```python
KIOSK_TOOL_REGISTRY = {
    "search_menu": ...,
    "calculate_order": ...,
    "create_order": ...,
}
```

- `search_menu`: Repository의 간이 RAG 검색만 호출
- `calculate_order`: DB 가격으로 `unit_price`, `line_total` 계산
- `create_order`: 소비된 pending action 내용으로만 저장

Tool Result는 공통 Envelope를 사용한다.

```json
{
  "success": true,
  "tool_name": "calculate_order",
  "data": {},
  "error": null
}
```

## 10. STT

필수 최소 구현은 `st.audio_input`의 WAV 파일을 `faster-whisper` `tiny` 모델로 한국어
변환하는 것이다. 모델은 요청마다 다시 로드하지 않고 Service 수준에서 지연 로드한다.

- 최대 파일 크기 10MB
- WAV MIME 검사
- 원본 파일 영구 저장 금지
- 모델 미준비 시 HTTP 503
- 텍스트 주문 API는 STT 상태와 무관하게 작동

TTS는 기존 `/api/media/tts`를 변경하지 않는다.

## 11. 환경변수

`config.py`와 `.env.example`에 아래 값을 추가한다.

```env
KIOSK_DB_MODE=mock
DATABASE_URL=postgresql://kiosk:kiosk_dev@127.0.0.1:5432/kiosk
KIOSK_STT_MODE=faster_whisper
KIOSK_STT_MODEL=tiny
KIOSK_AGENT_MAX_STEPS=6
KIOSK_PENDING_TTL_SECONDS=120
```

통합 시 `DATABASE_URL`의 Host만 태웅님 Mac IP로 변경한다. 실제 비밀번호를 코드,
문서, Trace, Git에 넣지 않는다.

## 12. `main.py` 변경 범위

기존 Router 등록은 유지하고 다음만 추가한다.

```python
from app.routers.kiosk_router import kiosk_router
app.include_router(kiosk_router)
```

기존 Router 순서와 URL을 변경하거나 삭제하지 않는다.

## 13. 실행

Windows PowerShell에서:

```powershell
.\.venv\Scripts\Activate.ps1
cd backend
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Ollama와 DB를 태웅님 Mac에서 사용할 때 루트 `.env`에 다음처럼 설정한다.

```env
OLLAMA_BASE_URL=http://<TAEWOONG_MAC_IP>:11434
KIOSK_DB_MODE=postgres
DATABASE_URL=postgresql://kiosk:<PASSWORD>@<TAEWOONG_MAC_IP>:5432/kiosk
```

## 14. 테스트

`backend/tests/test_kiosk.py`에 최소한 아래를 작성한다.

- 메뉴 목록 반환
- Workflow 대표 문장 → 15,000원
- Agent Mock 결정 → 15,000원
- 두 방식 Cart 결과 일치
- 누락된 단품/세트·수량 재질문
- 확인 전 주문 미저장
- 올바른 action 한 번만 저장
- 재사용 action 거절
- 미등록 Tool 차단
- 최대 Agent Step 종료
- Ollama 장애를 Workflow 성공처럼 위장하지 않음

## 15. 완료 체크

- [ ] 기존 Backend 테스트가 계속 통과한다.
- [ ] Swagger에 Kiosk Endpoint 네 개가 보인다.
- [ ] Mock DB 모드에서 독립 테스트가 된다.
- [x] 태웅님 PostgreSQL 연결 모드가 된다. (2026-08-26 VPS→맥 Tailscale 검증)
- [x] 태웅님 Ollama로 Agent 모드가 된다. (2026-08-26 llama3.2 3회 연속 15,000원)
- [ ] Workflow는 Ollama 없이 동작한다.
- [x] Agent와 Workflow의 최종 Cart·금액이 같다.
- [x] 확인 전 DB 주문이 생성되지 않는다.
- [x] Trace에서 두 방식의 진행 차이를 확인할 수 있다.
