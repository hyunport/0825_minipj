# 햄버거 키오스크 공통 API 계약

이 문서는 Frontend와 Backend 사이의 단일 계약이다. 담당자가 임의로 필드명, 상태값,
Tool 이름을 바꾸지 않는다. 변경이 필요하면 오현님이 이 문서를 먼저 수정한 뒤 양쪽에
알린다.

## 1. 기본 규칙

- Backend 기본 주소: `http://<INHYE_BACKEND_IP>:8000`
- 요청과 응답: UTF-8 JSON
- 음성 업로드만 `multipart/form-data`
- 가격 단위: 원, 정수
- 날짜·시간: ISO 8601
- `session_id`: Frontend가 최초 접속 시 UUID를 생성하고 대화 동안 유지
- `mode`: `workflow` 또는 `agent`

## 2. 공통 상수

### 주문 상태

```text
needs_clarification     필수 정보가 부족해 재질문
confirmation_required  계산이 끝나 고객 확인 대기
completed              주문 DB 저장 완료
rejected               잘못되거나 만료된 확인 요청
error                  연결, Tool, Agent, DB 오류
```

### 주문 옵션

```text
single  단품
set     세트
```

### 종료 이유

```text
needs_user_input
confirmation_required
completed
invalid_action
tool_error
agent_max_steps
agent_unavailable
database_error
```

## 3. 상태 확인

기존 Endpoint를 그대로 사용한다.

```http
GET /health
```

Frontend는 시작 시 이 Endpoint로 Backend 연결을 확인한다.

## 4. 메뉴 목록

```http
GET /api/kiosk/menu
```

응답 `200 OK`:

```json
{
  "menus": [
    {
      "menu_id": "B001",
      "name": "불고기버거",
      "description": "달콤한 불고기 소스가 들어간 햄버거",
      "single_price": 5000,
      "set_price": 7500,
      "active": true
    }
  ]
}
```

Frontend는 메뉴를 화면에 표시할 때만 사용하며 가격 계산은 하지 않는다.

## 5. 음성 인식

```http
POST /api/kiosk/transcribe
Content-Type: multipart/form-data
```

Form field:

| 이름 | 형식 | 필수 | 설명 |
|---|---|---|---|
| `audio` | file | 예 | Streamlit `st.audio_input`의 WAV 데이터 |

응답 `200 OK`:

```json
{
  "text": "불고기버거 세트 두 개 주세요",
  "provider": "faster-whisper",
  "model": "tiny",
  "latency_ms": 824
}
```

STT 모델을 준비하지 못했을 때는 `503`을 반환한다. Frontend는 오류를 표시하되 텍스트
입력을 막지 않는다.

## 6. 주문 실행

```http
POST /api/kiosk/order
Content-Type: application/json
```

### 요청

```json
{
  "mode": "workflow",
  "session_id": "8c68e13c-f8b6-4d0a-a93a-301d0e77ca77",
  "message": "불고기버거 세트 두 개 주세요",
  "confirmed": false,
  "action_id": null
}
```

| 필드 | 형식 | 필수 | 설명 |
|---|---|---|---|
| `mode` | `workflow \| agent` | 예 | 내부 처리 방식 |
| `session_id` | string | 예 | 대화 상태 식별자 |
| `message` | string | 예 | STT 결과 또는 수정한 텍스트 |
| `confirmed` | boolean | 예 | 고객의 최종 확인 여부 |
| `action_id` | string/null | 확인 시 | Backend가 발급한 임시 주문 ID |

### 공통 응답

```json
{
  "mode": "workflow",
  "session_id": "8c68e13c-f8b6-4d0a-a93a-301d0e77ca77",
  "status": "confirmation_required",
  "answer": "불고기버거 세트 2개, 총 15,000원입니다. 주문하시겠습니까?",
  "cart": [
    {
      "menu_id": "B001",
      "menu_name": "불고기버거",
      "option": "set",
      "quantity": 2,
      "unit_price": 7500,
      "line_total": 15000
    }
  ],
  "total_price": 15000,
  "action_id": "31d70e7d-b987-4be0-8b51-478b74ffb2cb",
  "order_number": null,
  "tool_calls": [
    {
      "tool": "search_menu",
      "arguments": {"query": "불고기버거"}
    },
    {
      "tool": "calculate_order",
      "arguments": {
        "menu_id": "B001",
        "option": "set",
        "quantity": 2
      }
    }
  ],
  "trace": [
    {"step": 1, "stage": "workflow_parse", "data": {}},
    {"step": 2, "stage": "tool_execution", "data": {}}
  ],
  "termination_reason": "confirmation_required"
}
```

`trace[].data`는 방식별로 자유로운 관찰 데이터가 들어갈 수 있지만 비밀번호, DB URL,
Prompt 전체 같은 민감정보는 넣지 않는다.

### 정보 부족 응답

요청:

```json
{
  "mode": "agent",
  "session_id": "test-1",
  "message": "불고기버거 주세요",
  "confirmed": false,
  "action_id": null
}
```

응답:

```json
{
  "mode": "agent",
  "session_id": "test-1",
  "status": "needs_clarification",
  "answer": "단품과 세트 중 무엇으로 몇 개 주문하시겠어요?",
  "cart": [],
  "total_price": 0,
  "action_id": null,
  "order_number": null,
  "tool_calls": [],
  "trace": [
    {
      "step": 1,
      "stage": "agent_decision",
      "data": {"action": "ask_clarification"}
    }
  ],
  "termination_reason": "needs_user_input"
}
```

같은 `session_id`로 `세트 두 개요`를 보내면 이전 메뉴 상태와 병합한다.

### 주문 확인 요청

```json
{
  "mode": "agent",
  "session_id": "test-1",
  "message": "주문할게요",
  "confirmed": true,
  "action_id": "31d70e7d-b987-4be0-8b51-478b74ffb2cb"
}
```

Backend는 확인 시 `message`를 다시 해석하지 않고 `action_id`에 저장된 주문만 실행한다.

완료 응답:

```json
{
  "mode": "agent",
  "session_id": "test-1",
  "status": "completed",
  "answer": "주문이 완료되었습니다. 주문번호는 K000001입니다.",
  "cart": [
    {
      "menu_id": "B001",
      "menu_name": "불고기버거",
      "option": "set",
      "quantity": 2,
      "unit_price": 7500,
      "line_total": 15000
    }
  ],
  "total_price": 15000,
  "action_id": null,
  "order_number": "K000001",
  "tool_calls": [
    {
      "tool": "create_order",
      "arguments": {"action_id": "31d70e7d-b987-4be0-8b51-478b74ffb2cb"}
    }
  ],
  "trace": [
    {"step": 1, "stage": "confirmed_tool_execution", "data": {}}
  ],
  "termination_reason": "completed"
}
```

## 7. 데모 상태 초기화

```http
POST /api/kiosk/reset
```

요청 Body는 `{}`다. Backend의 메모리 Session과 pending action만 초기화하며 DB 주문
기록은 삭제하지 않는다.

응답:

```json
{
  "reset": true,
  "note": "키오스크 대화 상태를 초기화했습니다."
}
```

## 8. Tool 계약

### `search_menu`

입력:

```json
{"query": "불고기"}
```

출력:

```json
{
  "matches": [
    {
      "menu_id": "B001",
      "name": "불고기버거",
      "description": "달콤한 불고기 소스가 들어간 햄버거",
      "single_price": 5000,
      "set_price": 7500
    }
  ]
}
```

### `calculate_order`

입력:

```json
{"menu_id": "B001", "option": "set", "quantity": 2}
```

출력:

```json
{
  "menu_id": "B001",
  "menu_name": "불고기버거",
  "option": "set",
  "quantity": 2,
  "unit_price": 7500,
  "line_total": 15000
}
```

### `create_order`

입력:

```json
{"action_id": "31d70e7d-b987-4be0-8b51-478b74ffb2cb"}
```

출력:

```json
{
  "created": true,
  "order_number": "K000001",
  "total_price": 15000
}
```

## 9. HTTP 오류 기준

| 상태 | 사용 시점 |
|---|---|
| 422 | Pydantic 요청 형식 오류 |
| 502 | Ollama 또는 DB 통신 오류 |
| 503 | STT 모델 미준비 또는 서비스 사용 불가 |

주문 도메인의 예상 가능한 실패는 가능하면 HTTP 200과 공통 `status`로 응답해 Frontend가
한 형태로 표시한다. 예외 메시지에 비밀번호나 전체 DB URL을 포함하지 않는다.
