# 햄버거 음성 키오스크 MVP 전체 계획

## 1. 프로젝트 목표

기존 `Mini Agent 03 · Tool Use` 프로젝트에 햄버거 음성 키오스크를 추가한다.
고객이 보는 화면과 주문 결과는 같고, 내부 주문 진행 방식만 두 가지로 나눈다.

- `workflow`: Backend 코드가 정해진 순서로 Tool을 실행한다.
- `agent`: Ollama가 현재 상태를 보고 재질문, 다음 Tool, 종료를 선택한다.

이번 결과물은 상용 서비스가 아니라 아래 내용을 짧게 확인하는 교육용 MVP다.

1. 음성 또는 텍스트로 햄버거를 주문할 수 있다.
2. Workflow와 AI Agent의 실행 Trace 차이를 확인할 수 있다.
3. 두 방식이 같은 Tool과 DB를 사용해 같은 주문 금액을 만든다.
4. macOS의 Ollama·DB, Windows의 Backend·Frontend를 같은 와이파이에서 연결한다.

## 2. 확정된 범위

### 필수 기능

- 한국어 주문
- Streamlit 마이크 입력과 인식 문장 수정
- 텍스트 직접 입력 대체 경로
- `Workflow / AI Agent` 실행 모드 선택
- 메뉴 검색, 단품/세트 선택, 수량 확인
- 누락된 정보 재질문
- 장바구니와 총금액 표시
- 사용자 확인 후 Mock 주문 DB 저장
- Tool Call, Trace, 종료 이유 표시
- PostgreSQL 메뉴·간이 RAG·주문 데이터
- Ollama를 이용한 Agent 판단

### 선택 기능

- 기존 TTS API를 이용한 음성 답변
- 메뉴 이미지
- 추가 메뉴와 자연어 별칭

### 구현하지 않는 기능

- 실제 카드 결제와 PG 연동
- 쿠폰, 할인, 회원, 배달
- 운영 수준 인증·권한·보안
- 실시간 재고와 동시성 처리
- 벡터 임베딩과 pgvector
- 관리자 화면

시간이 부족하면 `텍스트 주문 → Workflow → Agent → 원격 DB/Ollama 연결`을 먼저
완성하고 음성 입력은 마지막에 연결한다. 텍스트 입력은 항상 남겨 둔다.

## 3. 고정 메뉴와 가격

| ID | 메뉴 | 별칭 | 단품 | 세트 |
|---|---|---|---:|---:|
| B001 | 불고기버거 | 불고기, 불고기 버거 | 5,000원 | 7,500원 |
| B002 | 치즈버거 | 치즈, 치즈 버거 | 5,500원 | 8,000원 |
| B003 | 새우버거 | 새우, 새우 버거 | 6,000원 | 8,500원 |

주문 필수값은 `menu_id`, `option(single/set)`, `quantity` 세 가지다. 세트는 버거,
감자튀김, 콜라로 구성된 것으로 간주하며 세부 음료 변경은 이번 범위에서 제외한다.

대표 테스트 문장은 `불고기버거 세트 두 개 주세요`다. 기대 금액은 15,000원이다.

## 4. 전체 구조

```text
성엽님 Windows
Streamlit :8501
  └─ POST /api/kiosk/*
       ↓
인혜님 Windows
FastAPI :8000
  ├─ Workflow Service ─┐
  ├─ Agent Service ────┼─ 공통 Kiosk Tools ── PostgreSQL
  └─ STT Service       │                     태웅님 macOS :5432
                       └─ Ollama Provider ─── 태웅님 macOS :11434
```

Frontend는 Ollama나 DB에 직접 연결하지 않는다. Backend만 Ollama와 DB에 연결한다.
다른 PC의 서비스 주소에 `127.0.0.1`을 사용하지 않고 실제 와이파이 내부 IP를 사용한다.

## 5. 두 실행 방식

### Workflow

```text
메시지 수신
→ 코드로 메뉴·단품/세트·수량 추출
→ 누락값이면 재질문
→ search_menu
→ calculate_order
→ pending action 발급
→ 사용자 확인
→ 저장된 주문으로 create_order
→ 종료
```

실행 순서와 분기는 `kiosk_workflow_service.py`가 소유한다. Workflow에서는 주문 해석과
진행에 Ollama를 호출하지 않는다.

### AI Agent

```text
메시지와 Session 상태 수신
→ 간이 RAG 문맥 조회
→ Ollama Structured Output으로 다음 행동 결정
→ ask_clarification 또는 허용 Tool 실행
→ Tool Result를 상태에 병합
→ 최대 6회 반복
→ pending action 발급
→ 사용자 확인
→ 저장된 주문으로 create_order
→ 종료
```

Agent는 `search_menu`, `calculate_order`만 선택할 수 있다. 확인된 주문 저장은 Backend가
pending action을 검증한 후 실행한다. Agent는 가격을 만들거나 SQL을 실행할 수 없다.

## 6. 간이 RAG 데이터 계획

`knowledge_documents` 테이블에 다음 내용을 저장한다.

- 메뉴명과 설명
- 자연어 별칭: 불고기, 불고기 버거 등
- 세트 구성 설명
- 주문 필수값 안내

`search_menu` Tool이 사용자 문장과 메뉴명·별칭을 검색하고, 찾은 설명과 정확한 메뉴
ID를 Agent Prompt 문맥에 넣는다. 정확한 가격은 항상 `menu_items` 테이블에서 읽는다.
이번 구현은 검색 기반 간이 RAG이며 벡터 검색은 후속 확장으로 남긴다.

## 7. 공통 Tool

| Tool | 역할 | 상태 변경 |
|---|---|---|
| `search_menu` | 메뉴명·별칭·설명 검색 | 없음 |
| `calculate_order` | DB 가격으로 주문 금액 계산 | 없음 |
| `create_order` | 확인된 주문을 DB에 저장 | 있음 |

모든 입력은 Pydantic으로 검증하고 Allowlist에 없는 Tool은 `TOOL_NOT_ALLOWED`로
거절한다. 공통 계약은 [`공통 API.md`](./공통%20API.md)를 단일 기준으로 사용한다.

## 8. 폴더와 담당자

```text
PLAN.md                         # 오현님 관리
공통 API.md                     # 오현님 관리
frontend/
├─ dev.md                       # 성엽님 작업 명세
├─ app.py                       # 키오스크 Page 등록 지점
├─ app_pages/19_hamburger_kiosk.py
└─ clients/kiosk_client.py
backend/
├─ dev.md                       # 인혜님 작업 명세
├─ app/main.py                  # 키오스크 Router 등록 지점
├─ app/agents/hamburger_order_agent.py
├─ app/repositories/kiosk_repository.py
├─ app/routers/kiosk_router.py
├─ app/schemas/kiosk.py
├─ app/services/kiosk_agent_service.py
├─ app/services/kiosk_speech_service.py
├─ app/services/kiosk_workflow_service.py
├─ app/tools/kiosk_tools.py
└─ tests/test_kiosk.py
db/
├─ dev.md                       # 태웅님 작업 명세
├─ .env                         # Git 제외 개발용 DB 설정
├─ .env.example
├─ .gitignore
├─ docker-compose.yml
└─ init/
   ├─ 01_schema.sql
   └─ 02_seed.sql
```

## 9. 파일 소유권

| 담당자 | 수정 가능 | 수정 금지 |
|---|---|---|
| 오현님 | `PLAN.md`, `공통 API.md` | 팀원 코드 직접 병렬 수정 |
| 성엽님 | `frontend/**` 중 `frontend/dev.md`에 허용된 파일 | `backend/**`, `db/**`, 공통 계약 문서 |
| 인혜님 | `backend/**` 중 `backend/dev.md`에 허용된 파일, `requirements.txt`, `.env.example` | `frontend/**`, `db/**`, 공통 계약 문서 |
| 태웅님 | `db/**` | `frontend/**`, `backend/**`, 루트 환경 파일, 공통 계약 문서 |

계약 변경이 필요하면 각자 임의로 바꾸지 않고 오현님에게 알려 `공통 API.md`를 먼저
수정한다. 기존 Stage 01~03와 7개 Lab 코드는 삭제하거나 이름을 바꾸지 않는다.

## 10. 개발 순서

### 병렬 개발

1. 태웅님: Mac에서 Docker PostgreSQL과 Ollama를 실행하고 DB seed를 확인한다.
2. 인혜님: Mock DB 모드로 API·Workflow·Agent·Tool을 먼저 구현한다.
3. 성엽님: 공통 API 예시 JSON으로 UI를 구현하고 Backend 주소만 환경변수로 둔다.
4. 오현님: 세 문서와 공통 계약을 관리하고 테스트 문장을 고정한다.

### 통합 순서

1. Frontend PC → Backend `/health`
2. Backend PC → DB `:5432`
3. Backend PC → Ollama `:11434`
4. `workflow` 텍스트 주문
5. `agent` 텍스트 주문
6. 두 방식의 15,000원 결과 일치
7. 음성 녹음과 STT
8. 확인 후 `orders`, `order_items` 저장 확인

## 11. 완료 기준

- `GET /health`와 `GET /api/kiosk/menu`가 성공한다.
- Workflow에서 대표 문장이 15,000원 확인 요청을 만든다.
- Agent에서 같은 문장이 같은 주문과 금액을 만든다.
- 확인 전에는 `orders`에 저장되지 않는다.
- 올바른 `action_id`를 확인하면 한 번만 저장된다.
- 존재하지 않는 메뉴는 임의 가격을 만들지 않고 재질문한다.
- Agent Trace에 Ollama 결정과 Tool Result가 표시된다.
- Workflow Trace에 고정된 단계 순서가 표시된다.
- 세 PC가 같은 와이파이에서 연결된다.
- 마이크 실패 시 텍스트 입력으로 전체 시연을 계속할 수 있다.

## 12. 남은 결정 사항

제품 범위, 메뉴, 가격, API, Tool, DB 구조, 담당 파일과 완료 조건은 모두 확정했다.
추가 기획 결정은 없다. 통합 당일 아래 실행값만 공유하면 된다.

- 태웅님 Mac의 와이파이 IPv4 주소
- 인혜님 Windows의 와이파이 IPv4 주소
- 개발용 DB 비밀번호(기본값을 그대로 쓰면 별도 결정 불필요)
- Windows 방화벽에서 Backend 8000 포트 허용 여부
- Mac에서 5432와 11434 포트가 같은 와이파이에서 접근되는지

이 값들은 설계 변경이 아니라 실행 환경 확인 항목이다.
