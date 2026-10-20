# 비전AI 안전관제

건설현장 CCTV · TC(타워크레인) 카메라 영상에서 AI가 위험 상황을 감지하면, 관제화면에 경보를 띄우고 처리 과정을 기록하는 웹 시스템입니다.

- **백엔드**: FastAPI · SQLAlchemy 2 · MySQL 8
- **프론트엔드**: 빌드 없는 HTML / CSS / JS (`frontend/`). 백엔드가 같은 주소로 함께 내려줍니다
- **데이터 구조**: [ERD 3차](docs/erd-v3.png) · [`db/schema.sql`](db/schema.sql) (이전: [ERD 2차](docs/erd-v2.png))
- **화면 구성**: [페이지 구성 1차](docs/page-structure.md) · 서버 실행 후 `/index.html`(페이지 지도)

## 폴더 구조

```
vision-safety-control/
├─ backend/
│  ├─ app/
│  │  ├─ main.py        FastAPI 앱 · 화면(frontend/) 내려주기
│  │  ├─ config.py      설정 (.env)
│  │  ├─ database.py    DB 연결
│  │  ├─ models.py      테이블 (ERD 3차)
│  │  ├─ schemas.py     API 요청 · 응답 형식
│  │  ├─ deps.py        로그인 · 권한 확인
│  │  ├─ security.py    비밀번호 해시 · JWT
│  │  ├─ seed.py        기본 데이터 · 첫 관리자 · 시연 데이터
│  │  └─ routers/       auth · users · meta · cameras · events
│  ├─ tests/            pytest (SQLite 로 돌아서 MySQL 없이 실행됨)
│  └─ requirements.txt
├─ frontend/            화면 33개 + common.css / common.js / api.js
├─ db/schema.sql        MySQL 스키마 (기준)
├─ docs/                ERD(erd-v3.png · .html) · 페이지 구성 · 원본 대시보드
└─ tools/
   ├─ weather/          기상청 날씨 수집 (weather.json → 관제화면 날씨 패널)
   ├─ erd.py            db/schema.sql → docs/erd-v3.png (ERD 그림 다시 만들기)
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
- `--demo` 로 넣는 시연 데이터: 회원 9명(승인 대기 3 · 잠금 1 포함) · 작업자 13명(특별관리 6 · 교육 이력 포함) · 작업 7건과 배정 · 구역 6곳(배치도 위치 포함) · 장비 10대와 3일치 일일 기록 · 카메라 8대 · ROI 4개와 ROI별 규칙 · 이벤트 9건(처리 기록 · 예시 스냅샷 포함). 날짜는 실행한 날 기준으로 들어갑니다. 통계 화면용으로 **지난 30일 이벤트(약 300건)**도 함께 들어가며, `--history-days 0` 으로 빼거나 일수를 바꿀 수 있습니다.
  시연 회원(`oh.sy`, `park.jw` 등)도 관리자와 같은 비밀번호로 로그인됩니다. 예시 스냅샷은 `storage/snapshots/` 에 만들어집니다.
- API 문서(직접 눌러 보기): <http://localhost:8000/docs>

> MySQL 없이 빨리 보고 싶으면 `.env` 에 `DATABASE_URL=sqlite:///./dev.db` 를 넣고
> `python -m app.seed --create-tables --admin-password "..." --demo` 로 시작할 수 있습니다.

### YOLO 탐지 영상 (선택)

관제화면(1-1)과 단일 카메라 확대(1-2)는 서버가 **YOLO 탐지 박스와 ROI 를 그려 넣은 영상**을 보여 줍니다. 나머지 화면(ROI 그리기 · 카메라 등록 등)은 원본 영상을 그대로 틉니다.

```bash
cd backend
pip install -r requirements-yolo.txt   # ultralytics (torch · opencv 포함, 용량이 큼) · openvino
```

- 기본 모델은 **OpenVINO 로 변환한 `yolov8n`** 입니다 (Intel 내장 그래픽에서 PyTorch CPU 보다 2~3배 빠름. i3-1315U 기준 17ms vs 42ms). 처음 관제화면을 열 때 `yolov8n.pt` 를 내려받아 `backend/yolov8n_openvino_model/` 로 한 번 변환합니다 (인터넷 필요, 1분쯤). 이 폴더는 git 에 올리지 않습니다.
  - 직접 변환하려면: `yolo export model=yolov8n.pt format=openvino imgsz=640`
  - `YOLO_IMGSZ` 를 바꾸면 변환할 때 크기가 고정되므로 `yolov8n_openvino_model/` 폴더를 지우고 다시 변환되게 합니다.
  - `YOLO_DEVICE` 기본값 `intel:gpu` 는 Intel 내장 그래픽을 씁니다. 없는 PC(AMD 등)는 경고 한 줄 뒤 알아서 CPU 로 돕니다. 다만 CPU 만 쓸 때는 OpenVINO 가 PyTorch 보다 빠르지 않을 수 있으니, 그런 PC 는 `.env` 에 `YOLO_MODEL=yolov8n.pt` 를 넣어 비교해 보세요.
  - NVIDIA 그래픽카드가 있으면 PyTorch 가 더 빠릅니다: `.env` 에 `YOLO_MODEL=yolov8n.pt`, `YOLO_DEVICE=cuda:0`.
- 직접 학습한 모델은 `.env` 에 `YOLO_MODEL=모델파일.pt` (또는 변환한 `..._openvino_model` 폴더) 경로로 지정합니다.
- 설치하지 않았거나 `.env` 에 `YOLO_ENABLED=false` 를 넣으면, 1-1 · 1-2 도 원본 영상을 보여 줍니다. 단일 카메라 확대의 카메라 정보 `화면` 줄에 그 이유가 나옵니다.
- 그 밖의 설정: `YOLO_CONF`(이 confidence 미만 박스는 안 그림, 기본 0.35), `STREAM_FPS`(화면으로 보내는 초당 장수, 기본 8) · `STREAM_MAX_WIDTH`(보내는 영상 최대 가로 크기, 기본 960). 성능이 좋은 PC 는 12 · 1280 정도로 올려도 됩니다
- 탐지는 지금 보고 있는 카메라만 합니다. 관제화면은 보이는 페이지(1페이지 현장 CAM / 2페이지 TC CAM)의 4대만 받습니다. CPU 에서는 카메라 4대가 탐지 한 번씩을 나눠 쓰므로 박스가 영상보다 조금 늦게 따라옵니다.
- 발밑(박스 아래 가운데)이 ROI 안에 있으면 박스를 그 구역 색으로 그리고 `· 위험구역` 처럼 구역 이름을 붙입니다.
- 영상 주소: `GET /api/stream/{카메라번호}.mjpg?token=로그인토큰&roi=1` (`roi=0` 이면 박스만). RTSP 카메라도 이 주소로 볼 수 있습니다.

### ROI 이벤트 (YOLO → 이벤트 로그 · 스냅샷 · 통계)

YOLO 를 쓸 수 있으면 서버가 켜질 때부터 ROI 를 판정해 이벤트를 만듭니다 (`backend/app/zone_events.py`). 이벤트 목록 · 통계 · 관제화면 알림에 그대로 쌓입니다.

- **ROI 목록**에서 구역마다 저장한 설정을 씁니다. **침입 탐지 대상**(사람 · 트럭)을 저장하지 않았거나 비워 둔 구역은 판정하지 않습니다.
  - 체류 시간 `0초` → 들어오자마자 **ROI 침범**(`ZONE_INTRUSION`), `N초` → N초 넘게 머물면 **ROI 체류 초과**(`ZONE_DWELL`)
  - 체류 시간 `사용안함` · 구역 사용 스위치 · 적용 시간이 꺼져 있으면 판정하지 않습니다.
- **판정 기준(8-8)** 값을 그대로 씁니다: confidence 가 기준 미만인 박스는 세지 않고, `사용`을 끄면 판정하지 않습니다. 쿨다운 · 심각도(8-9)는 이벤트를 만들 때 적용합니다. 저장하면 5초 안에 반영됩니다.
- 발밑(박스 아래 가운데)이 구역 안이면 들어온 것으로 봅니다. 박스가 2초 안으로 잠깐 끊기는 건 계속 머문 것으로 보고, 한 번 머무는 동안 이벤트는 한 번만 만듭니다.
- 이벤트가 생기면 그 순간 화면(ROI · 탐지 박스)을 `storage/snapshots/날짜/` 에 JPEG 로 저장합니다. 그린 구역은 DB `roi` 에 `1번 위험구역` 같은 이름으로 이어져, 이벤트의 구역 · ROI별 규칙에 쓰입니다.
- 보는 사람이 없어도 판정할 구역이 있는 카메라는 계속 탐지합니다. 노트북이 버거우면 `.env` 에 `EVENT_WATCH=false` (관제화면 · 단일 카메라 확대를 보고 있을 때만 판정).

### 장비 근접 (추적 → EQUIPMENT_PROXIMITY 이벤트)

탐지 박스를 카메라마다 **ByteTrack**(기본) 또는 **BoT-SORT** 로 추적해 번호를 붙이고 (`backend/app/vision.py` 의 `Tracker`), 작업자 · 장비 번호 짝으로 근접을 판정합니다 (`backend/app/proximity.py`). 영상의 박스 이름 뒤에 `사람#12` 처럼 추적 번호가 붙습니다.

- 장비는 `PROXIMITY_CLASSES`(기본 `truck,excavator`. 굴삭기는 세그 모델을 켰을 때만 잡힘) 클래스입니다.
- 거리는 카메라 보정 없이 **작업자 키(약 1.7m)를 자로 삼아** 어림합니다: 작업자 발밑에서 장비 박스 아래쪽 절반(땅에 닿는 부분)까지의 픽셀 거리 ÷ 작업자 박스 높이 × 1.7m. 카메라에서 멀어지는 방향(깊이)은 화면에서 줄어 보여 실제보다 가깝게 나올 수 있습니다.
- 같은 작업자 · 장비가 `PROXIMITY_M`(기본 3m) 안에 `PROXIMITY_HOLD_SEC`(기본 1초) 넘게 있으면 경보 한 번. 2초 안으로 끊기는 건 이어진 것으로 보고, 멀어졌다 다시 오면 다시 판정합니다.
- 작업자 박스가 장비 박스 안에 거의 들어 있고 발밑이 장비 아래 끝보다 위면 운전석에 탄 사람으로 보고 뺍니다.
- **판정 기준(8-8)의 장비 근접** 값을 씁니다: 사용 끔 → 판정 안 함, 쿨다운(같은 카메라) · 심각도 그대로. confidence 는 작업자 · 장비 모두 추적하는 동안 한 번이라도 기준을 넘어야 셉니다 (넘은 뒤로는 잠깐 낮게 잡혀도 같은 물체로 이어 봄).
- ROI 와 상관없이 **탐지 중인 카메라**(화면에서 보고 있거나 ROI 이벤트 감시 중) 전체를 판정합니다. 이벤트에는 구역(ROI) 없이 카메라만 들어가고, 스냅샷에 작업자 ↔ 장비 붉은 선과 거리를 그립니다.
- 추적기는 `.env` 의 `TRACKER` 로 고릅니다: `bytetrack` · `botsort` · 직접 고친 설정 파일(`…yaml`, ultralytics 의 `cfg/trackers/` 를 복사해 수정). BoT-SORT 는 카메라 흔들림 보정(GMC)이 있어 **TC 카메라처럼 움직이는 화면**에 낫지만 CPU 를 더 씁니다. 비우면 추적과 장비 근접 판정을 하지 않습니다.
- 장비 근접처럼 **해제 항목(작업 허가)이 있는 유형**은 아래 「작업 허가 전 경보 지속」 규칙을 따릅니다.
- 추적기가 낮은 박스로도 번호를 이어 붙이도록 탐지는 confidence 0.1 까지 받고, 화면 · ROI 판정에는 예전처럼 기준(`YOLO_CONF` · 8-8) 이상만 넘깁니다.

### 작업 허가 전 경보 지속 (작업중지 유형)

해제 항목이 있는 감지 유형(신호수 미배치 · 장비 근접 · TC 후크 근접 · 직하부 작업자)은 이벤트가 한 번 생기면, **해제 항목을 모두 허가할 때까지** 경보가 계속 떠 있고, 그동안 같은 카메라 · ROI 에서 다시 탐지돼도 새 이벤트를 만들지 않습니다 (`routers/events.py` 의 `open_hold` · `holding`).

- 이벤트 목록 · 상세 API 의 `holding` 이 「작업 허가 대기」입니다 (처리 전 + 해제 항목이 남음). 쿨다운과 상관없이 막고, 스냅샷도 처음 것만 남습니다.
- 화면은 `holding` 인 동안 경보를 끊지 않습니다: 관제화면은 그 카메라의 섹터 감지경보 칸 · CCTV 칸 · TC 카드가 허가될 때까지 계속 빨갛게 깜빡이고, 헤더 🔔 은 계속 깜빡이며 알림 목록에 「작업 허가 대기 · 경보 지속」이 붙습니다. 이벤트 상세에도 표시됩니다.
- 항목을 모두 허가하거나(처리완료 전이라도) 처리완료 · 오탐으로 닫으면 경보가 멈추고, 다음 탐지부터는 다시 새 이벤트입니다.
- 카메라가 없는 경보(관제화면의 TC 후크 겹침 시뮬레이션)는 같은 자리인지 알 수 없어 예전처럼 따로 만듭니다.

### 3. 테스트

코드가 제대로 동작하는지 자동으로 확인합니다. MySQL · `.env` 없이 임시 SQLite DB 로 돌아갑니다.

```powershell
cd backend                      # 저장소 최상위 폴더에서 시작
.venv\Scripts\python -m pytest
```

마지막 줄에 `109 passed` 가 나오면 정상입니다. (가상환경을 활성화했다면 `pytest` 만 쳐도 됩니다)

> 끝날 때 임시 폴더를 지우다 `PermissionError` 가 나면(Windows) 테스트 결과와는 상관없습니다.
> `--basetemp=..\..\pytest-tmp` 처럼 다른 폴더를 주면 사라집니다.

### 4. 이미 DB 를 만들어 둔 경우 (구조가 바뀌었을 때)

`db/schema.sql` 이 바뀌면 처음부터 만든 DB 에는 새 칸이 없어서 오류가 납니다. 아래를 순서대로 한 번씩 실행하세요.
(MySQL 없이 SQLite `dev.db` 로 쓰는 경우는 파일을 지우고 `--create-tables` 로 다시 만들면 됩니다)

| 날짜 | 바뀐 것 | 실행할 SQL |
|---|---|---|
| 2026-10-05 | 비밀번호 5번 틀리면 15분 잠금 (`users.locked_until`) | `ALTER TABLE users ADD COLUMN locked_until DATETIME NULL AFTER failed_login_count;` |
| 2026-10-06 | 현장 도면(`site_plan` 새 테이블) · 카메라 배치도 위치(`camera.plan_x` · `plan_y` · `plan_dir`) | 아래 SQL |
| 2026-10-07 | 카메라 배치도 화각 색 (`camera.plan_color`) | `ALTER TABLE camera ADD COLUMN plan_color CHAR(7) NULL AFTER plan_dir;` |
| 2026-10-13 | 카메라 배치도 화각 폭 · 길이 (`camera.plan_fov` · `plan_range`, 360° 회전 카메라는 원으로) | `ALTER TABLE camera ADD COLUMN plan_fov SMALLINT UNSIGNED NULL AFTER plan_color, ADD COLUMN plan_range SMALLINT UNSIGNED NULL AFTER plan_fov;` |

```sql
-- 2026-10-06 현장 도면 · 카메라 배치도 위치
CREATE TABLE site_plan (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  title VARCHAR(100) NOT NULL DEFAULT '현장 배치도',
  image_path VARCHAR(500) NOT NULL,
  original_name VARCHAR(255) NULL,
  width INT UNSIGNED NOT NULL,
  height INT UNSIGNED NOT NULL,
  size_bytes INT UNSIGNED NOT NULL,
  uploaded_by BIGINT UNSIGNED NULL,
  uploaded_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  CONSTRAINT fk_site_plan_user FOREIGN KEY (uploaded_by) REFERENCES users (id)
) ENGINE=InnoDB;
ALTER TABLE camera
  ADD COLUMN plan_x DECIMAL(5,4) NULL AFTER is_active,
  ADD COLUMN plan_y DECIMAL(5,4) NULL AFTER plan_x,
  ADD COLUMN plan_dir SMALLINT UNSIGNED NULL AFTER plan_y;
```

앞으로 DB 구조를 바꾸면 이 표에 한 줄씩 더하고, `python tools/erd.py` 로 ERD 그림도 다시 만들어 주세요.

> **2026-10-05 `web` 브랜치 히스토리를 다시 썼습니다** (커밋 작성자 수정, force push).
> 그 전에 `web` 을 받아 둔 사람은 `git fetch origin` 후 `git reset --hard origin/web` 으로 맞추세요.
> 로컬에서 따로 만든 커밋이 있으면 reset 대신 `git rebase --onto origin/web dd2640f` 로 옮기면 됩니다.

## 지금 되는 것

| 구분 | API | 연결된 화면 |
|---|---|---|
| 로그인 · 회원가입 | `POST /api/auth/signup` · `POST /api/auth/login` · `GET /api/auth/me` | `login.html` · `signup.html` |
| 회원 관리 (관리자) | `GET/POST /api/users` · `POST /api/users/{id}/approve` · `/reject` · `/reset-password` · `PATCH/DELETE /api/users/{id}` | `users.html` · `user-approval.html` · `user-edit.html` |
| 조직 · 부서 | `GET/POST /api/orgs` · `PATCH/DELETE /api/orgs/{id}` (회사 아래 부서 최대 2단계) | `org.html` · 회원가입 |
| 작업구역 | `GET/POST /api/work-zones` · `PATCH/DELETE /api/work-zones/{id}` · `GET /api/work-zones/summary` (배치도 영역 `plan_polygon` = 도면 기준 0~1 꼭짓점 3~40개, null 이면 표시 안 함) | `zones.html` (도면 위에서 다각형 그리기 · 고치기) |
| 작업자 · 교육 | `GET/POST /api/workers` · `GET/PATCH/DELETE /api/workers/{id}` · `POST/DELETE /api/workers/{id}/special` · `GET /api/educations` · `POST /api/workers/{id}/educations` · `DELETE …/educations/{기록 id}` | `workers.html` · `worker-special.html` |
| 작업 · 배정 | `GET/POST /api/works` (`?on=날짜`, `?upcoming=true`) · `GET/PATCH/DELETE /api/works/{id}` · `PUT /api/works/{id}/workers` · `GET /api/users/staff` | `works.html` · `zone-works.html` · `work-workers.html` |
| 장비 · 일일 기록 | `GET/POST /api/equipment` · `GET/PATCH/DELETE /api/equipment/{id}` · `PUT /api/equipment/{id}/logs/{날짜}` · `POST /api/equipment/daily` | `equipment.html` · `equipment-detail.html` · `equipment-assign.html` · `work-workers.html`(작업 구역의 투입 장비) |
| 판정 · 심각도 기준 | `GET /api/detection-types` · `PATCH /api/detection-types/{id}/rule` · `POST /api/detection-types/reset-rules` | `alert-threshold.html` · `alert-severity.html` |
| 카메라 | `GET/POST /api/cameras` · `GET/PATCH/DELETE /api/cameras/{id}` (배치도 위치 `plan_x` · `plan_y` · `plan_dir` 포함) | `cameras.html` · `camera-edit.html` · `camera-map.html` |
| 현장 도면 | `GET /api/site-plan` · `PUT /api/site-plan` (본문 = 그림 파일, PNG · JPG · WebP 15MB) · `PATCH` (이름) · `DELETE` — 관리자만 바꿈, 그림은 `storage/plans` · `/plans/…` | `camera-map.html`(관리 · 카메라 배치 수정) · `zones.html`(배경) |
| ROI 구역 | `GET /api/roi-zones` · `PUT /api/roi-zones` (구역 전체를 바꿈, 관리자만) — `storage/roi-zones.json` 에 저장, AI 탐지 프로그램이 이 파일을 읽음. 카메라 목록은 DB(영상 파일이 연결된 카메라에만 그릴 수 있음) | `roi-draw.html` · `roi-list.html` |
| 이벤트 수집 (AI) | `POST /api/events` (헤더 `X-Ingest-Key`) | — |
| 이벤트 조회 | `GET /api/events` (날짜 · 구역 · 종류 · 심각도 · 상태 · 정렬 · 페이지) · `GET /api/events/{id}` | `events.html` · `event-detail.html` · `event-snapshot.html` |
| 이벤트 내보내기 | `GET /api/events/export?format=csv\|xlsx\|zip&columns=…` (목록과 같은 조건) · `GET /api/events/export/preview` | `event-export.html` |
| 통계 | `GET /api/stats/summary` (기간 · 앞 기간 비교) · `GET /api/stats/trend?date_from=&date_to=` (없으면 `days=14`) · `GET /api/stats/report` | `stats.html` · `stats-trend.html` · `stats-report.html` (PDF 는 브라우저 인쇄 → PDF로 저장) |
| 이벤트 처리 | `POST /api/events/{id}/actions` | `event-handle.html` |

나머지 화면은 아직 예시 데이터로 보입니다. 화면에 API 를 붙일 때는 `api.js` 를 `common.js` 앞에 넣고 `api("/api/...")` 로 부르면 됩니다.

### 규칙 · 처리 흐름

1. **AI 감지 → 이벤트**: 서버의 YOLO ROI 판정과 외부 탐지 프로그램의 `POST /api/events` 가 같은 규칙으로, ROI별 규칙(`roi_rule`) → 기본 규칙(`alert_rule`) 순으로 판정 기준(confidence)과 심각도를 정하고, 기준 미달이거나 쿨다운 시간 안에 같은 경보가 있으면 이벤트를 만들지 않습니다.
2. **처리**: `ACK`(확인 시작) → 해제 항목(`release_check_item`)마다 `PERMIT` → 모두 허가되면 `RESOLVE` 로 처리완료. `FALSE_ALARM` 은 오탐 처리. 끝난 이벤트에는 `NOTE` 만 남길 수 있습니다.
3. **권한**: `ADMIN` 전체 · `MANAGER` 이벤트 처리 · `VIEWER` 조회만. 가입하면 `PENDING` 이고 관리자가 승인해야 로그인됩니다. 비밀번호를 5번 틀리면 15분 동안 로그인할 수 없고, 시간이 지나면 저절로 풀립니다(관리자가 바로 풀 수도 있음). 관리자가 직접 `잠금`으로 바꾼 계정은 풀어 줄 때까지 막힙니다.
4. **특별관리**: 사유(고령 · 고혈압 · 신규 투입 · 기타)를 여러 개 고를 수 있고, 신규 투입은 현장 투입일부터 7일이 지나면 자동으로 빠집니다. 감지 유형을 "사용 안 함"으로 끄면 그 유형은 이벤트를 만들지 않습니다.
5. **삭제 규칙**: 작업자 삭제는 이력 때문에 행을 남기고(끝나지 않은 배정 · 장비 운전원에서는 빠짐), 배정이 남은 작업 · 카메라가 달린 장비 · 쓰이는 구역 · 하위 부서나 회원이 있는 조직은 지울 수 없습니다.
6. **회원 삭제**: 처리 기록에 이름이 남아야 해서 행을 지우지 않고 `DELETED` 로 바꿉니다. 관리자가 직접 등록하거나 비밀번호를 초기화하면 임시 비밀번호가 화면에 한 번만 표시됩니다.

## 다음 할 일

- [x] 이벤트 상세 · 처리 기록 화면 연결
- [x] 회원가입 승인 · 회원 목록 · 회원정보 수정 · 카메라 목록 · 카메라 등록 화면 연결
- [x] 조직 · 부서 관리, 작업자 · 특별관리 · 교육, 작업 · 배정, 장비 · 일일 기록, 작업구역, 판정 · 심각도 기준 화면 연결
- [x] ROI 그리기 저장 (`storage/roi-zones.json`) · 카메라 목록 DB 연결
- [ ] ROI별 규칙 API (`roi-rules.html` 은 아직 예시. 그린 구역을 DB `roi` · `roi_rule` 과 이을지 정하기)
- [ ] 관제화면 패널(TC/작업구역 · 섹터 감지경보 · 특별관리근로자)을 실제 데이터로 (알림 팝업은 30초 조회로 연결됨)
- [x] 이벤트 내보내기(CSV · 엑셀 · 스냅샷 묶음) · 스냅샷 조회 · 통계(요약 · 추이 · 리포트 PDF) 화면 연결
- [ ] 카메라 배치도 · 단일 카메라 확대 화면 연결
- [x] YOLO 탐지 영상 (관제화면 · 단일 카메라 확대에 탐지 박스 · ROI 표시)
- [x] YOLO 탐지 결과 → ROI 침범 · 체류 이벤트 · 스냅샷 (`zone_events.py`)
- [x] 객체 추적(ByteTrack · BoT-SORT) → 장비 근접 이벤트 · 스냅샷 (`proximity.py`)
- [ ] 안전모 · 조끼 등 나머지 감지 유형 (전용 모델이 생기면)
- [ ] DB 변경 이력 관리 (Alembic)