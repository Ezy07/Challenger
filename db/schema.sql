-- =============================================================
-- 비전AI 안전관제 시스템 - MySQL 스키마 (ERD 2차 기준)
-- MySQL 8.0 이상 / InnoDB / utf8mb4
-- 그림: docs/erd-v2.png
-- 백엔드 모델(backend/app/models.py)과 같은 구조를 유지할 것
-- =============================================================

CREATE DATABASE IF NOT EXISTS safety_control
  DEFAULT CHARACTER SET utf8mb4
  DEFAULT COLLATE utf8mb4_0900_ai_ci;

USE safety_control;

-- -------------------------------------------------------------
-- 1. 회원 · 조직 (로그인하는 사람)
-- -------------------------------------------------------------
CREATE TABLE organization (
  id          BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  parent_id   BIGINT UNSIGNED NULL,                           -- 상위 조직 (회사 > 부서)
  type        ENUM('COMPANY', 'DEPT') NOT NULL,
  name        VARCHAR(100) NOT NULL,
  is_prime    TINYINT(1)   NOT NULL DEFAULT 0,                -- 원청이면 1
  PRIMARY KEY (id),
  CONSTRAINT fk_org_parent FOREIGN KEY (parent_id) REFERENCES organization (id)
) ENGINE=InnoDB;

CREATE TABLE users (
  id                  BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  org_id              BIGINT UNSIGNED NULL,
  login_id            VARCHAR(20)  NOT NULL,                  -- 영문 소문자 · 숫자 · 점 4~20자
  password_hash       VARCHAR(255) NOT NULL,                  -- bcrypt (평문 저장 금지)
  name                VARCHAR(50)  NOT NULL,
  position            VARCHAR(30)  NULL,                      -- 직급 (과장, 대리 ...)
  phone               VARCHAR(20)  NULL,
  role                ENUM('ADMIN', 'MANAGER', 'VIEWER') NOT NULL DEFAULT 'VIEWER',
  status              ENUM('PENDING', 'ACTIVE', 'REJECTED', 'LOCKED') NOT NULL DEFAULT 'PENDING',
  approved_by         BIGINT UNSIGNED NULL,                   -- 승인한 관리자
  approved_at         DATETIME     NULL,
  failed_login_count  TINYINT UNSIGNED NOT NULL DEFAULT 0,    -- 5회 실패 시 LOCKED
  last_login_at       DATETIME     NULL,
  created_at          DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at          DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uk_users_login_id (login_id),
  CONSTRAINT fk_users_org         FOREIGN KEY (org_id)      REFERENCES organization (id),
  CONSTRAINT fk_users_approved_by FOREIGN KEY (approved_by) REFERENCES users (id)
) ENGINE=InnoDB;

-- -------------------------------------------------------------
-- 2. 구역 · 카메라 · ROI
-- -------------------------------------------------------------
CREATE TABLE work_zone (
  id            BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  name          VARCHAR(100) NOT NULL,                        -- 101동 갱폼 인양구역 등
  plan_polygon  JSON         NULL,                            -- 배치도 위 영역 [[x,y], ...]
  PRIMARY KEY (id)
) ENGINE=InnoDB;

-- 작업자 · 작업 · 장비 (안전관리자가 매일 관리)
-- camera.equipment_id 가 equipment 를 가리키므로 먼저 만든다
CREATE TABLE worker (
  id               BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  name             VARCHAR(50)  NOT NULL,
  company          VARCHAR(100) NULL,                         -- 소속 협력사
  job_type         VARCHAR(50)  NULL,                         -- 형틀목공, 신호수 ...
  phone            VARCHAR(20)  NULL,
  birth_date       DATE         NULL,                         -- 동명이인 구분 · 고령 판단
  is_special_care  TINYINT(1)   NOT NULL DEFAULT 0,           -- 특별관리 대상
  special_reason   VARCHAR(200) NULL,                         -- 고령 · 고혈압 · 신규 투입 등 (민감정보)
  is_active        TINYINT(1)   NOT NULL DEFAULT 1,
  created_at       DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id)
) ENGINE=InnoDB;

CREATE TABLE equipment (
  id            BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  name          VARCHAR(100) NOT NULL,                        -- TC 3호기, 굴착기 02 ...
  equip_type    ENUM('TC', 'EXCAVATOR', 'PUMP_CAR', 'CRANE', 'FORKLIFT', 'ETC') NOT NULL,
  work_zone_id  BIGINT UNSIGNED NULL,                         -- 투입 구역
  operator_id   BIGINT UNSIGNED NULL,                         -- 운전원 (현장작업자)
  status        ENUM('RUNNING', 'IDLE', 'MAINTENANCE', 'OUT') NOT NULL DEFAULT 'IDLE',  -- 현재 상태
  PRIMARY KEY (id),
  CONSTRAINT fk_equipment_zone     FOREIGN KEY (work_zone_id) REFERENCES work_zone (id),
  CONSTRAINT fk_equipment_operator FOREIGN KEY (operator_id)  REFERENCES worker (id)
) ENGINE=InnoDB;

CREATE TABLE camera (
  id             BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  name           VARCHAR(100) NOT NULL,                       -- CAM_0001
  work_zone_id   BIGINT UNSIGNED NULL,
  equipment_id   BIGINT UNSIGNED NULL,                        -- TC CAM 이면 달린 크레인
  camera_type    ENUM('FIXED', 'TC') NOT NULL DEFAULT 'FIXED',
  view_page      TINYINT UNSIGNED NOT NULL DEFAULT 1,         -- 관제화면 1페이지(현장) / 2페이지(TC)
  view_slot      TINYINT UNSIGNED NULL,                       -- 4분할 칸 1~4
  stream_url     VARCHAR(500) NULL,                           -- RTSP 주소 등
  location_desc  VARCHAR(255) NULL,
  is_active      TINYINT(1)   NOT NULL DEFAULT 1,
  PRIMARY KEY (id),
  UNIQUE KEY uk_camera_slot (view_page, view_slot),           -- 한 칸에 카메라 하나
  CONSTRAINT fk_camera_zone      FOREIGN KEY (work_zone_id) REFERENCES work_zone (id),
  CONSTRAINT fk_camera_equipment FOREIGN KEY (equipment_id) REFERENCES equipment (id),
  CONSTRAINT chk_camera_slot CHECK (view_slot IS NULL OR view_slot BETWEEN 1 AND 4)
) ENGINE=InnoDB;

CREATE TABLE roi (
  id            BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  camera_id     BIGINT UNSIGNED NOT NULL,
  work_zone_id  BIGINT UNSIGNED NULL,
  name          VARCHAR(100) NOT NULL,
  polygon       JSON         NOT NULL,                        -- 카메라 화면 좌표 [[x,y], ...]
  is_active     TINYINT(1)   NOT NULL DEFAULT 1,
  PRIMARY KEY (id),
  CONSTRAINT fk_roi_camera FOREIGN KEY (camera_id)    REFERENCES camera (id),
  CONSTRAINT fk_roi_zone   FOREIGN KEY (work_zone_id) REFERENCES work_zone (id)
) ENGINE=InnoDB;

-- -------------------------------------------------------------
-- 3. 감지 규칙 (기본값 + ROI별 덮어쓰기)
-- -------------------------------------------------------------
CREATE TABLE detection_type (
  id     BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  code   VARCHAR(40)  NOT NULL,                               -- NO_HELMET, LOAD_OVERHEAD_WORKER ...
  label  VARCHAR(50)  NOT NULL,                               -- 안전모 미착용
  PRIMARY KEY (id),
  UNIQUE KEY uk_detection_type_code (code)
) ENGINE=InnoDB;

-- 감지 유형별 기본값
CREATE TABLE alert_rule (
  id                 BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  detection_type_id  BIGINT UNSIGNED NOT NULL,
  min_confidence     DECIMAL(4,3) NOT NULL DEFAULT 0.500,
  default_severity   ENUM('HIGH', 'MEDIUM', 'LOW') NOT NULL DEFAULT 'MEDIUM',
  cooldown_sec       INT UNSIGNED NOT NULL DEFAULT 60,        -- 같은 경보를 다시 알리기까지
  PRIMARY KEY (id),
  UNIQUE KEY uk_alert_rule_type (detection_type_id),
  CONSTRAINT fk_alert_rule_type FOREIGN KEY (detection_type_id) REFERENCES detection_type (id),
  CONSTRAINT chk_alert_rule_conf CHECK (min_confidence BETWEEN 0 AND 1)
) ENGINE=InnoDB;

-- 경보 해제 전에 하나씩 허가해야 하는 항목 (예: 인양 중지 · 대피 · 반경 통제)
CREATE TABLE release_check_item (
  id                 BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  detection_type_id  BIGINT UNSIGNED NOT NULL,
  title              VARCHAR(100) NOT NULL,
  sort_order         INT          NOT NULL DEFAULT 0,
  PRIMARY KEY (id),
  CONSTRAINT fk_check_item_type FOREIGN KEY (detection_type_id) REFERENCES detection_type (id)
) ENGINE=InnoDB;

-- ROI별 덮어쓰기 (NULL 이면 alert_rule 기본값 사용)
CREATE TABLE roi_rule (
  id                 BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  roi_id             BIGINT UNSIGNED NOT NULL,
  detection_type_id  BIGINT UNSIGNED NOT NULL,
  min_confidence     DECIMAL(4,3) NULL,
  severity           ENUM('HIGH', 'MEDIUM', 'LOW') NULL,
  PRIMARY KEY (id),
  UNIQUE KEY uk_roi_rule (roi_id, detection_type_id),
  CONSTRAINT fk_roi_rule_roi  FOREIGN KEY (roi_id)            REFERENCES roi (id) ON DELETE CASCADE,
  CONSTRAINT fk_roi_rule_type FOREIGN KEY (detection_type_id) REFERENCES detection_type (id)
) ENGINE=InnoDB;

-- -------------------------------------------------------------
-- 4. 이벤트 (AI 감지 → 알림 → 처리)
-- -------------------------------------------------------------
CREATE TABLE event (
  id                 BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  camera_id          BIGINT UNSIGNED NULL,                    -- 기상 경보처럼 카메라가 없는 경우 NULL
  roi_id             BIGINT UNSIGNED NULL,                    -- ROI 밖이면 NULL
  detection_type_id  BIGINT UNSIGNED NOT NULL,
  severity           ENUM('HIGH', 'MEDIUM', 'LOW') NOT NULL,  -- 발생 당시 값 저장
  confidence         DECIMAL(4,3) NULL,
  bbox               JSON         NULL,                       -- [x1, y1, x2, y2]
  status             ENUM('NEW', 'ACK', 'DONE', 'FALSE') NOT NULL DEFAULT 'NEW',
  detected_at        DATETIME(3)  NOT NULL,
  PRIMARY KEY (id),
  KEY idx_event_time (detected_at),
  KEY idx_event_status (status, detected_at),
  CONSTRAINT fk_event_camera FOREIGN KEY (camera_id)         REFERENCES camera (id),
  CONSTRAINT fk_event_roi    FOREIGN KEY (roi_id)            REFERENCES roi (id),
  CONSTRAINT fk_event_type   FOREIGN KEY (detection_type_id) REFERENCES detection_type (id),
  CONSTRAINT chk_event_conf CHECK (confidence IS NULL OR confidence BETWEEN 0 AND 1)
) ENGINE=InnoDB;

-- 처리 기록 (시간순 로그). PERMIT / REVOKE 는 release_check_item 하나에 대한 허가 · 취소
CREATE TABLE event_action (
  id             BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  event_id       BIGINT UNSIGNED NOT NULL,
  user_id        BIGINT UNSIGNED NOT NULL,                    -- 처리자
  check_item_id  BIGINT UNSIGNED NULL,                        -- 허가한 항목
  action_type    ENUM('ACK', 'NOTE', 'ESCALATE', 'PERMIT', 'REVOKE', 'RESOLVE', 'FALSE_ALARM') NOT NULL,
  memo           VARCHAR(1000) NULL,
  created_at     DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY idx_event_action_event (event_id, created_at),
  CONSTRAINT fk_action_event FOREIGN KEY (event_id)      REFERENCES event (id) ON DELETE CASCADE,
  CONSTRAINT fk_action_user  FOREIGN KEY (user_id)       REFERENCES users (id),
  CONSTRAINT fk_action_item  FOREIGN KEY (check_item_id) REFERENCES release_check_item (id),
  CONSTRAINT chk_action_item CHECK (action_type NOT IN ('PERMIT', 'REVOKE') OR check_item_id IS NOT NULL)
) ENGINE=InnoDB;

CREATE TABLE event_snapshot (
  id          BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  event_id    BIGINT UNSIGNED NOT NULL,
  image_path  VARCHAR(500) NOT NULL,
  created_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  CONSTRAINT fk_snapshot_event FOREIGN KEY (event_id) REFERENCES event (id) ON DELETE CASCADE
) ENGINE=InnoDB;

-- -------------------------------------------------------------
-- 5. 작업 · 배정 · 장비 일일 기록
-- -------------------------------------------------------------
CREATE TABLE work (
  id            BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  work_zone_id  BIGINT UNSIGNED NOT NULL,
  manager_id    BIGINT UNSIGNED NULL,                         -- 담당자 (users)
  name          VARCHAR(100) NOT NULL,                        -- 갱폼 인양, 거푸집 설치 ...
  work_date     DATE         NOT NULL,
  status        ENUM('PLANNED', 'IN_PROGRESS', 'DONE', 'STOPPED') NOT NULL DEFAULT 'PLANNED',
  PRIMARY KEY (id),
  KEY idx_work_date (work_date),
  CONSTRAINT fk_work_zone    FOREIGN KEY (work_zone_id) REFERENCES work_zone (id),
  CONSTRAINT fk_work_manager FOREIGN KEY (manager_id)   REFERENCES users (id)
) ENGINE=InnoDB;

CREATE TABLE work_assignment (
  work_id        BIGINT UNSIGNED NOT NULL,
  worker_id      BIGINT UNSIGNED NOT NULL,
  assigned_date  DATE NOT NULL,
  PRIMARY KEY (work_id, worker_id, assigned_date),
  KEY idx_assignment_worker (worker_id),
  CONSTRAINT fk_assignment_work   FOREIGN KEY (work_id)   REFERENCES work (id) ON DELETE CASCADE,
  CONSTRAINT fk_assignment_worker FOREIGN KEY (worker_id) REFERENCES worker (id)
) ENGINE=InnoDB;

CREATE TABLE equipment_daily_log (
  id            BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  equipment_id  BIGINT UNSIGNED NOT NULL,
  log_date      DATE         NOT NULL,
  status        ENUM('RUNNING', 'IDLE', 'MAINTENANCE', 'OUT') NOT NULL,
  note          VARCHAR(500) NULL,
  recorded_by   BIGINT UNSIGNED NULL,
  created_at    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uk_equipment_log_day (equipment_id, log_date),   -- 하루 한 번 수동 업데이트
  CONSTRAINT fk_equipment_log_equipment FOREIGN KEY (equipment_id) REFERENCES equipment (id) ON DELETE CASCADE,
  CONSTRAINT fk_equipment_log_user      FOREIGN KEY (recorded_by)  REFERENCES users (id)
) ENGINE=InnoDB;
