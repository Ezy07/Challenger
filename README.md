# 비전AI 안전관제

건설현장 CCTV · TC(타워크레인) 카메라 영상에서 AI가 위험 상황을 감지하면, 관제화면에 경보를 띄우고 처리 과정을 기록하는 웹 시스템입니다.

- **백엔드**: FastAPI · SQLAlchemy 2 · MySQL 8
- **프론트엔드**: 빌드 없는 HTML / CSS / JS (`frontend/`). 백엔드가 같은 주소로 함께 내려줍니다
- **데이터 구조**: [ERD 2차](docs/erd-v2.png) · [`db/schema.sql`](db/schema.sql)
- **화면 구성**: [페이지 구성 1차](docs/page-structure.md) · 서버 실행 후 `/index.html`(페이지 지도)

## 폴더 구조

```
vision-safety-control/
├─ backend/
│  ├─ app/
│  │  ├─ main.py        FastAPI 앱 · 화면(frontend/) 내려주기
│  │  ├─ config.py      설정 (.env)
│  │  ├─ database.py    DB 연결
│  │  ├─ models.py      테이블 (ERD 2차)
│  │  ├─ schemas.py     API 요청 · 응답 형식
│  │  ├─ deps.py        로그인 · 권한 확인
│  │  ├─ security.py    비밀번호 해시 · JWT
│  │  ├─ seed.py        기본 데이터 · 첫 관리자 · 시연 데이터
│  │  └─ routers/       auth · users · meta · cameras · events
│  ├─ tests/            pytest (SQLite 로 돌아서 MySQL 없이 실행됨)
│  └─ requirements.txt
├─ frontend/            화면 33개 + common.css / common.js / api.js
├─ db/schema.sql        MySQL 스키마 (기준)
├─ docs/                ERD · 페이지 구성 · 원본 대시보드
└─ tools/
   ├─ weather/          기상청 날씨 수집 (weather.json → 관제화면 날씨 패널)
   └─ tc_simulation.py  TC 선회 반경 시뮬레이션
```

## 처음 실행하기

### 1. DB 만들기 (MySQL 8)

```sql
-- MySQL 에 root 로 접속해서
SOURCE db/schema.sql;
CREATE USER 'safety'@'localhost' IDENTIFIED BY '비밀번호';
GRANT ALL ON safety_control.* TO 'safety'@'localhost';
```

### 2. 백엔드 실행

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate          # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env          # 그리고 .env 안의 CHANGE_ME 값을 바꾸기 (영문 · 숫자만)

python -m app.seed --admin-password "관리자비밀번호" --demo   # 기본 데이터 + 관리자(choi.dh) + 시연 데이터
uvicorn app.main:app --reload
```

- 화면: <http://localhost:8000> → 로그인 화면 (`choi.dh` / 위에서 정한 비밀번호)
- `--demo` 로 넣는 시연 데이터: 회원 9명(승인 대기 3 · 잠금 1 포함) · 작업자 14명 · 오늘 작업 5건 · 장비 6대와 3일치 일일 기록 · 카메라 7대 · ROI 4개와 ROI별 규칙 · 이벤트 9건(처리 기록 · 예시 스냅샷 포함).
  시연 회원(`oh.sy`, `park.jw` 등)도 관리자와 같은 비밀번호로 로그인됩니다. 예시 스냅샷은 `storage/snapshots/` 에 만들어집니다.
- API 문서(직접 눌러 보기): <http://localhost:8000/docs>

> MySQL 없이 빨리 보고 싶으면 `.env` 에 `DATABASE_URL=sqlite:///./dev.db` 를 넣고
> `python -m app.seed --create-tables --admin-password "..." --demo` 로 시작할 수 있습니다.

### 3. 테스트

코드가 제대로 동작하는지 자동으로 확인합니다. MySQL · `.env` 없이 임시 SQLite DB 로 돌아갑니다.

```powershell
cd backend                      # 저장소 최상위 폴더에서 시작
.venv\Scripts\python -m pytest
```

마지막 줄에 `21 passed` 가 나오면 정상입니다. (가상환경을 활성화했다면 `pytest` 만 쳐도 됩니다)

## 지금 되는 것

| 구분 | API | 연결된 화면 |
|---|---|---|
| 로그인 · 회원가입 | `POST /api/auth/signup` · `POST /api/auth/login` · `GET /api/auth/me` | `login.html` · `signup.html` |
| 회원 관리 (관리자) | `GET/POST /api/users` · `POST /api/users/{id}/approve` · `/reject` · `/reset-password` · `PATCH/DELETE /api/users/{id}` | `users.html` · `user-approval.html` · `user-edit.html` |
| 기준 정보 | `GET /api/orgs` · `POST /api/orgs` · `GET /api/work-zones` · `GET /api/equipment` · `GET /api/detection-types` | 회사 · 부서 · 구역 · 장비 선택, 이벤트 필터 |
| 카메라 | `GET/POST /api/cameras` · `GET/PATCH/DELETE /api/cameras/{id}` | `cameras.html` · `camera-edit.html` |
| 이벤트 수집 (AI) | `POST /api/events` (헤더 `X-Ingest-Key`) | — |
| 이벤트 조회 | `GET /api/events` (날짜 · 구역 · 종류 · 심각도 · 상태 · 정렬 · 페이지) · `GET /api/events/{id}` · `GET /api/events/export.csv` | `events.html` · `event-detail.html` |
| 이벤트 처리 | `POST /api/events/{id}/actions` | `event-handle.html` |

나머지 화면은 아직 예시 데이터로 보입니다. 화면에 API 를 붙일 때는 `api.js` 를 `common.js` 앞에 넣고 `api("/api/...")` 로 부르면 됩니다.

### 규칙 · 처리 흐름

1. **AI 감지 → 이벤트**: `POST /api/events` 가 ROI별 규칙(`roi_rule`) → 기본 규칙(`alert_rule`) 순으로 판정 기준(confidence)과 심각도를 정하고, 기준 미달이거나 쿨다운 시간 안에 같은 경보가 있으면 이벤트를 만들지 않습니다.
2. **처리**: `ACK`(확인 시작) → 해제 항목(`release_check_item`)마다 `PERMIT` → 모두 허가되면 `RESOLVE` 로 처리완료. `FALSE_ALARM` 은 오탐 처리. 끝난 이벤트에는 `NOTE` 만 남길 수 있습니다.
3. **권한**: `ADMIN` 전체 · `MANAGER` 이벤트 처리 · `VIEWER` 조회만. 가입하면 `PENDING` 이고 관리자가 승인해야 로그인됩니다. 비밀번호 5회 실패 시 잠김.
4. **회원 삭제**: 처리 기록에 이름이 남아야 해서 행을 지우지 않고 `DELETED` 로 바꿉니다. 관리자가 직접 등록하거나 비밀번호를 초기화하면 임시 비밀번호가 화면에 한 번만 표시됩니다.

## 다음 할 일

- [x] 이벤트 상세 · 처리 기록 화면 연결
- [x] 회원가입 승인 · 회원 목록 · 회원정보 수정 · 카메라 목록 · 카메라 등록 화면 연결
- [ ] 조직 · 부서 관리 화면 연결 (`org.html`)
- [ ] 작업자 · 작업 · 장비 CRUD API
- [ ] ROI 그리기 저장 · ROI별 규칙 API
- [ ] 관제화면 실시간 알림 (WebSocket 또는 주기적 조회)
- [ ] YOLO 탐지 파이프라인 → `POST /api/events` 연동
- [ ] 스냅샷 이미지 업로드 · 저장 위치 정하기
- [ ] DB 변경 이력 관리 (Alembic)
