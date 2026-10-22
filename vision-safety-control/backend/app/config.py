from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parents[2]  # 저장소 최상위 폴더
DEV_JWT_SECRET = "dev-only-secret-do-not-use-in-production"


class Settings(BaseSettings):
    """환경 변수 또는 backend/.env 에서 읽는 설정. 예시는 backend/.env.example 참고."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "mysql+pymysql://safety:safety@localhost:3306/safety_control?charset=utf8mb4"
    jwt_secret: str = DEV_JWT_SECRET
    jwt_expire_minutes: int = 8 * 60  # 관제 근무 한 교대 시간
    ingest_api_key: str = "change-me-too"  # AI 탐지 프로그램이 이벤트를 올릴 때 쓰는 키
    max_failed_logins: int = 5
    login_lock_minutes: int = 15  # 비밀번호를 max_failed_logins 번 틀리면 이만큼 로그인 금지 (지나면 자동 해제)

    @field_validator("ingest_api_key")
    @classmethod
    def ascii_only(cls, v: str) -> str:
        if not v.isascii():
            raise ValueError("INGEST_API_KEY 는 HTTP 헤더로 보내므로 영문 · 숫자 · 기호만 쓸 수 있습니다 (한글 X)")
        return v

    frontend_dir: Path = ROOT_DIR / "frontend"
    weather_dir: Path = ROOT_DIR / "tools" / "weather"
    snapshot_dir: Path = ROOT_DIR / "storage" / "snapshots"
    plan_dir: Path = ROOT_DIR / "storage" / "plans"  # 현장 도면 그림 (site_plan.image_path 는 "plans/...")
    max_plan_mb: int = 15
    roi_zones_file: Path = ROOT_DIR / "storage" / "roi-zones.json"  # ROI 그리기 화면이 그린 구역 (AI 탐지 프로그램이 읽음)
    video_dir: Path = ROOT_DIR / "storage" / "videos"  # 시연 · 개발용 영상 (카메라 대신)  # event_snapshot.image_path 는 이 폴더 기준 "snapshots/..." 경로

    # 휴대폰 · PC 브라우저 웹 푸시 (Web Push). 이벤트가 새로 생기면 알림을 켠 기기로 보낸다 (backend/app/push.py).
    # 서명 키(VAPID)는 처음 쓸 때 push_key_file 에 만든다. 지우거나 바꾸면 모든 기기가 알림을 다시 켜야 한다
    push_enabled: bool = True
    push_key_file: Path = ROOT_DIR / "storage" / "vapid_private.pem"
    push_subject: str = "mailto:admin@example.com"  # 푸시 서비스(구글 · 애플)가 문제 있을 때 연락할 곳 (mailto: 또는 https://)

    # YOLO 탐지 영상 (관제화면 1-1 · 단일 카메라 확대 1-2). 패키지는 requirements-yolo.txt
    yolo_enabled: bool = True
    # OpenVINO 모델 (Intel 내장 그래픽에서 PyTorch CPU 보다 2~3배 빠름). 폴더가 없으면 처음 실행할 때 yolov8n.pt 를 내려받아 변환한다.
    # PyTorch 그대로 쓰려면 "yolov8n.pt", 직접 학습한 모델은 파일 경로.
    # 사람 · 안전모 · 조끼 · 장비를 함께 학습한 모델(ppe_finetune.ipynb 의 site6c)이면 "site6c_openvino_model" 로 두고 YOLO_PPE_MODEL 은 비운다
    yolo_model: str = "yolov8n_openvino_model"
    yolo_seg_model: str = ""        # 시험용: 세그 모델을 하나 더 돌려 윤곽을 칠함 (예: excavator_seg_openvino_model). 비우면 안 씀
    yolo_conf: float = 0.50       # 이 confidence 미만인 탐지 박스는 그리지 않음
    yolo_imgsz: int = 640           # 바꾸면 OpenVINO 모델 폴더를 지우고 다시 변환해야 함 (변환할 때 크기가 고정됨)
    yolo_device: str = "intel:gpu"  # OpenVINO: Intel 내장 그래픽 (없으면 알아서 CPU). .pt 모델이면 비우거나 cpu · cuda:0
    stream_fps: int = 8             # 화면으로 보내는 초당 장수 (탐지는 CPU 가 되는 만큼만). 노트북 기준으로 낮춤
    stream_max_width: int = 960     # 이보다 큰 영상은 줄여서 보냄 (탐지도 줄인 영상으로 함)
    stream_jpeg_quality: int = 80
    event_watch: bool = True        # 보는 사람이 없어도 ROI 를 판정할 카메라는 계속 탐지해 이벤트를 남김 (false 면 화면을 볼 때만)

    # 객체 추적 (카메라마다 따로). bytetrack | botsort | 직접 고친 설정 파일(.yaml) 경로. 비우면 추적 · 장비 근접 판정을 안 함
    # botsort 는 카메라 흔들림 보정(GMC)이 있어 TC 카메라처럼 움직이는 화면에 낫지만 CPU 를 더 씀
    tracker: str = "bytetrack"
    # 장비 근접(EQUIPMENT_PROXIMITY): 작업자 발밑이 장비에서 proximity_m 미터 안에 proximity_hold_sec 초 넘게 있으면 경보
    proximity_classes: str = "truck,excavator,forklift"  # 장비로 볼 YOLO 클래스 (쉼표로 구분. 모델에 없는 이름은 그냥 안 잡힘)
    proximity_m: float = 3.0
    proximity_hold_sec: float = 1.0

    # 안전모 · 조끼 미착용(NO_HELMET · NO_VEST). tools/train/ppe_finetune.ipynb 로 학습한 모델(person · helmet · vest)을
    # 하나 더 돌려 안전모 · 조끼 박스만 더한다. 비우면 미착용 판정을 안 함 (기본 모델이 안전모 · 조끼까지 잡으면 그 모델로 판정)
    yolo_ppe_model: str = ""        # 예: ppe_openvino_model
    ppe_part_conf: float = 0.30     # 안전모 · 조끼 박스는 이만큼만 넘어도 착용으로 본다 (놓치면 미착용 오탐이라 낮게)
    ppe_window_sec: float = 3.0     # 작업자마다 이만큼 지켜본 뒤 다수결로 판정
    # PPE 모델은 탐지 이만큼에 한 번만 돌린다 (1 이면 매번). 판정이 3초 다수결이라 덜 봐도 결과는 거의 같고 탐지가 빨라짐.
    # 크게 올리면 PPE_WINDOW_SEC 안 표본이 MIN_SAMPLES(3) 보다 적어져 판정이 늦어질 수 있음
    ppe_every: int = 2
    ppe_min_person_px: int = 100    # 키가 이보다 작게 보이는 작업자는 판정하지 않음 (현장 영상에서 이보다 작으면 안전모를 거의 못 찾음)

    # 신호수 미배치(NO_SIGNALMAN): 빨간 계열 조끼 = 신호수, 노란 계열 = 일반 작업자 (PPE 모델의 조끼 박스 색으로 가림).
    # 카메라에 장비(signal_classes)가 있는데 신호수가 signal_hold_sec 초 넘게 안 보이면 경보. PPE 모델이 없으면 판정 안 함
    signal_classes: str = "truck,excavator,forklift"  # 신호수가 있어야 하는 장비 YOLO 클래스 (쉼표로 구분)
    signal_hold_sec: float = 10.0
    signal_min_person_px: int = 60  # 조끼 색은 안전모보다 멀리서도 보여 미착용 판정보다 작게 잡는다
    # 빨강 쪽 · 노랑 쪽을 가르는 색상(OpenCV H 0~179). 주황도 이 경계로 판정한다. 15 = 30도:
    # 형광 주황(255,100,0 · H 12) 은 신호수, 진한 노랑 주황(255,160,0 · H 19) 은 일반 작업자
    signal_hue_split: int = 15


settings = Settings()
