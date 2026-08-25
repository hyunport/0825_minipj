# Ollama·DB 개발 명세 — 태웅님

## 1. 목표

macOS에서 Ollama와 PostgreSQL을 실행하고, 같은 와이파이의 Windows Backend가 두
서비스에 접속할 수 있게 한다. 복잡한 운영 DB가 아니라 키오스크 실습용 최소 환경이다.

Backend 계약은 루트의 [`공통 API.md`](../공통%20API.md), 전체 구조는
[`PLAN.md`](../PLAN.md)를 참고한다.

## 2. 수정 가능한 파일

- `db/dev.md`
- `db/.env.example`
- `db/docker-compose.yml`
- `db/init/01_schema.sql`
- `db/init/02_seed.sql`
- DB 확인용 SQL이 필요하면 `db/check.sql` 신규 생성

## 3. 수정하면 안 되는 파일

- `frontend/**`
- `backend/**`
- 루트 `.env`, `.env.example`, `requirements.txt`
- `PLAN.md`
- `공통 API.md`
- 기존 프로젝트의 Python 코드

Backend 연결 때문에 Schema 변경이 필요하면 직접 Backend 코드를 바꾸지 말고 인혜님과
오현님에게 알린다. 공통 메뉴 ID와 가격은 임의로 변경하지 않는다.

## 4. 확정 환경

- 운영체제: macOS
- LLM: Ollama `llama3.2`
- DB: Docker PostgreSQL 16
- DB Port: `5432`
- Ollama Port: `11434`
- DB 이름: `kiosk`
- 개발 계정: `kiosk`
- 기본 개발 비밀번호: `kiosk_dev`

비밀번호는 같은 와이파이 실습용 기본값이다. 인터넷이나 공용 네트워크에는 노출하지
않고 필요하면 `db/.env`에서 변경한다.

## 5. DB 실행

터미널에서 프로젝트 루트 기준:

```bash
cd db
docker compose up -d
docker compose ps
```

개발용 `db/.env`는 미리 생성되어 있고 Git 제외 대상으로 지정되어 있다. 파일이 없어진
경우에만 `cp .env.example .env`로 다시 만든다. 최초 실행 시 `db/init/01_schema.sql`,
`02_seed.sql`이 자동 실행된다.

DB 확인:

```bash
docker compose exec postgres psql -U kiosk -d kiosk -c "SELECT menu_id, name, single_price, set_price FROM menu_items ORDER BY menu_id;"
```

기대 결과는 B001~B003 세 메뉴다.

## 5-1. 태웅 Mac 실제 실행 상태 (2026-08-25)

태웅 Mac에는 다른 실습(주차·분실물·RAG)이 쓰는 공용 PostgreSQL 컨테이너 `pg`
(`pgvector/pgvector:pg16`, host `:5432`)가 이미 떠 있어서 `docker compose up`으로
새 컨테이너를 띄우지 않고 **같은 컨테이너 안에 `kiosk` DB를 추가**했다. 팀이 쓰는
접속 문자열·계정·비밀번호·테이블은 위 4절과 동일하다.

```bash
# 최초 1회 (완료됨)
docker exec pg psql -U parking -d postgres -c "CREATE ROLE kiosk LOGIN PASSWORD 'kiosk_dev';"
docker exec pg psql -U parking -d postgres -c "CREATE DATABASE kiosk OWNER kiosk;"
docker exec -i pg psql -U kiosk -d kiosk < db/init/01_schema.sql
docker exec -i pg psql -U kiosk -d kiosk < db/init/02_seed.sql

# 확인
docker exec -i pg psql -U kiosk -d kiosk < db/check.sql
```

- 5절의 `docker compose` 절차는 다른 PC에서 DB를 띄울 때의 폴백이다. 호스트 5432가
  이미 사용 중이면 `db/.env`의 `POSTGRES_PORT`만 바꾸면 된다.
- 스키마를 수정하면 `docker exec -i pg psql -U kiosk -d kiosk < db/init/01_schema.sql`로
  다시 적용한다 (`IF NOT EXISTS`라 기존 테이블은 건드리지 않음).
- 검증 완료: LAN IP(`192.100.200.192`)로 `kiosk` 계정 접속 OK, 메뉴 3건·knowledge 5건 확인.

## 6. Ollama 실행

태웅 Mac은 Ollama도 Docker 컨테이너 `ollama`(`ollama/ollama`, `0.0.0.0:11434`)로 돌고
있고 `llama3.2`가 이미 받아져 있다. 별도 `ollama serve`는 띄우지 않는다 (Port 충돌).

```bash
docker ps --filter name=ollama            # Up 인지
docker exec ollama ollama list            # llama3.2:latest 있어야 함
docker exec ollama ollama pull llama3.2   # 없을 때만
```

Docker 없이 직접 띄우는 경우의 폴백:

```bash
ollama pull llama3.2
OLLAMA_HOST=0.0.0.0:11434 ollama serve
```

이미 Ollama 앱이나 다른 `ollama serve`가 실행 중이면 먼저 종료해 Port 충돌을 피한다.
Ollama가 LAN 요청을 받도록 `127.0.0.1`이 아닌 `0.0.0.0`에 Bind해야 한다.
검증 완료: LAN IP로 `/api/tags` 응답 + `llama3.2` chat completions 응답 OK.

로컬 확인:

```bash
curl http://127.0.0.1:11434/api/tags
```

## 7. Mac IP 확인과 공유

현재 와이파이 IP를 확인해 인혜님에게 전달한다.

```bash
ipconfig getifaddr en0
```

Mac에 따라 Wi-Fi Interface가 다르면 시스템 설정의 Wi-Fi 상세 화면에서 IPv4 주소를
확인한다. 공유할 값은 비밀번호가 아니라 아래 두 주소다.

```text
http://<TAEWOONG_MAC_IP>:11434
postgresql://kiosk:<PASSWORD>@<TAEWOONG_MAC_IP>:5432/kiosk
```

2026-08-25 수업 와이파이 기준 태웅 Mac IP는 `192.100.200.192`다. 와이파이가 바뀌면
다시 확인해서 공유한다. Mac 방화벽은 꺼져 있어(`socketfilterfw --getglobalstate`)
별도 허용 설정이 필요 없다.

## 8. 다른 PC 접속 확인

인혜님 Windows PC에서 먼저 Port를 확인한다.

```powershell
Test-NetConnection <TAEWOONG_MAC_IP> -Port 5432
Test-NetConnection <TAEWOONG_MAC_IP> -Port 11434
```

11434 확인:

```powershell
Invoke-RestMethod http://<TAEWOONG_MAC_IP>:11434/api/tags
```

연결되지 않으면 다음만 확인한다.

- 두 PC가 같은 와이파이인지
- Mac 방화벽이 Docker와 Ollama 수신을 차단하는지
- Ollama가 `0.0.0.0:11434`에 Bind했는지
- Docker Compose의 `5432:5432` Port가 열렸는지
- 학교·공용 와이파이가 기기 간 통신을 차단하는지

## 9. DB 테이블 책임

### `menu_items`

정확한 메뉴 ID, 이름, 별칭, 설명, 단품 가격, 세트 가격을 저장한다.

### `knowledge_documents`

간이 RAG에 사용할 메뉴 설명, 별칭, 세트 안내를 저장한다. 가격의 최종 기준으로
사용하지 않는다.

### `orders`

사용자 확인이 끝난 주문번호, 실행 방식, 총금액을 저장한다.

### `order_items`

주문별 메뉴, 단품/세트, 수량, 단가, 금액을 저장한다.

## 10. Schema 변경 규칙

- 기존 컬럼명을 임의로 바꾸지 않는다.
- 메뉴 ID B001~B003을 바꾸지 않는다.
- 가격을 바꾸면 `PLAN.md`, `공통 API.md`, 테스트도 함께 바뀌어야 하므로 오현님에게
  먼저 알린다.
- Python Backend가 만든 `orders`, `order_items`를 수동으로 수정하지 않는다.
- 팀 통합 중 `docker compose down -v`로 Volume을 삭제하지 않는다.
- 초기화가 꼭 필요하면 팀원에게 알린 후 실행한다.

## 11. 완료 체크

- [x] DB가 떠 있다 (태웅 Mac은 공용 `pg` 컨테이너에 `kiosk` DB 추가 — 5-1절).
- [x] 메뉴 세 개와 정확한 가격이 조회된다.
- [x] `knowledge_documents`에 seed가 있다.
- [x] Mac 로컬에서 Ollama `/api/tags`가 열린다.
- [ ] Windows Backend PC에서 5432 연결이 된다.
- [ ] Windows Backend PC에서 11434 연결이 된다.
- [ ] 인혜님에게 Mac IP와 접속 문자열 형식을 전달했다.
- [ ] Workflow 주문이 `orders`, `order_items`에 저장된다.
- [ ] Agent 주문도 같은 테이블에 저장된다.

## 12. 종료와 재실행

서비스만 중지하고 데이터는 유지한다.

```bash
cd db
docker compose stop
```

재실행:

```bash
cd db
docker compose start
```

`docker compose down -v`는 DB 데이터를 삭제하므로 사용하지 않는다.
