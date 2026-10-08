/* 모든 화면이 함께 쓰는 스크립트
   - 화면 목록(MENU)을 한 곳에 모아 두고, 상단 바 · 왼쪽 메뉴(☰) · 제목 칸 · 하위 화면 탭을 여기서 그린다
   - 메뉴 구성은 「비전AI 안전관제 페이지 구성 1차.txt」를 그대로 따른다
   - 화면을 추가하려면 MENU 에 [파일 이름, 화면 이름, 설명, 깊이] 한 줄만 넣으면 된다
     깊이 0 = 메모장의 "-" 화면, 1 = "ㄴ" 화면, 2 = "ㄴㄴ" 화면
     파일 이름이 빈 줄("")은 메뉴 안의 소제목으로만 쓴다 (예: 관리자 > 카메라 관리)
   - 아직 API 를 연결하지 않은 화면의 저장 · 삭제 버튼은 안내 문구(toast)만 띄운다
   - API 를 쓰는 화면은 api.js 를 이 파일보다 먼저 넣는다 */

const MENU = [
  { icon: "▣", name: "관제화면", pages: [
    ["monitor.html", "관제화면", "CCTV 4분할 · TC/작업구역 · 섹터 감지경보 · 특별관리근로자", 0],
    ["monitor-camera.html", "단일 카메라 확대", "카메라 한 대를 크게 보면서 ROI · 탐지 박스 · 최근 이벤트 확인", 1],
  ] },
  { icon: "◫", name: "구역 및 작업", pages: [
    ["zones.html", "전체 구역 표시", "현장 배치도 위에 작업구역과 구역별 작업 · 인원 · 장비 · 경보를 표시", 0],
    ["zone-works.html", "구역별 작업 목록", "구역을 고르면 그 구역에서 오늘 진행하는 작업을 보여 줌", 1],
    ["work-workers.html", "작업별 장비 · 작업자 목록", "작업 하나에 배정된 작업자 · 특별관리 대상과 그 구역에 투입된 장비 · 운전원 · 상태", 2],
  ] },
  { icon: "≡", name: "이벤트 로그", pages: [
    ["events.html", "이벤트 목록", "날짜 · 구역 · 종류 · 심각도로 지난 이벤트를 찾고 CSV로 내보내기", 0],
    ["event-detail.html", "이벤트 상세", "이벤트 하나의 스냅샷 · 탐지 정보 · 처리 상태", 1],
    ["event-snapshot.html", "스냅샷 조회 및 저장", "탐지 순간 이미지를 크게 보고 내려받기", 2],
    ["event-handle.html", "처리 기록", "확인 · 조치 · 오탐 처리와 메모를 시간순으로 기록", 2],
    ["event-export.html", "내보내기", "이벤트 목록의 [내보내기]로 여는 화면. 조건을 골라 CSV · 엑셀 · 스냅샷 묶음으로 받기", 1],
  ] },
  { icon: "▤", name: "통계", pages: [
    ["stats.html", "요약", "기간별 건수 · 처리율 · 처리 시간과 종류 · 구역별 건수", 0],
    ["stats-trend.html", "추이 차트", "일별 · 시간대별로 이벤트가 늘거나 줄었는지 확인", 0],
    ["stats-report.html", "리포트", "기간을 골라 요약 보고서를 만들고 PDF로 저장 · 인쇄", 0],
  ] },
  { icon: "⬠", name: "ROI", pages: [
    ["roi-draw.html", "ROI 그리기", "카메라 화면 위를 클릭해 감지 영역(ROI) 다각형 그리기", 0],
    ["roi-list.html", "ROI 목록", "만든 ROI 전체를 보고 켜고 끄기", 0],
    ["roi-rules.html", "ROI별 규칙", "ROI마다 알림 규칙 기본값을 덮어쓰기 (침범 · 체류 · 대상 클래스)", 0],
  ] },
  { icon: "⚙", name: "장비 현황", pages: [
    ["equipment.html", "장비 목록", "현장 중장비와 현재 상태 (하루 한 번 수동 업데이트)", 0],
    ["equipment-detail.html", "장비 상세", "장비 한 대의 일일 기록 · 투입 구역 · 관련 이벤트", 0],
  ] },
  { icon: "✚", name: "안전관리 업무", pages: [
    ["workers.html", "현장작업자 관리", "현장작업자 등록 · 수정 · 삭제", 0],
    ["worker-special.html", "특별관리 지정", "고령 · 고혈압 · 신규 투입 등 특별관리 대상 지정과 해제", 0],
    ["works.html", "작업 등록 및 배정", "작업을 만들고 구역 · 담당자 · 작업자를 배정", 0],
    ["equipment-assign.html", "장비 등록 및 배정", "중장비를 등록하고 투입 구역 · 운전원을 지정", 0],
  ] },
  { icon: "◆", name: "관리자", admin: true, pages: [
    ["", "회원 관리"],
    ["users.html", "회원 목록", "회원 조회 · 등록 · 삭제", 0],
    ["user-approval.html", "회원가입 승인", "가입 신청한 사람을 확인하고 승인 · 반려", 1],
    ["user-edit.html", "회원정보 수정", "기본 정보와 역할(권한) · 계정 상태 바꾸기", 1],
    ["org.html", "조직 · 부서 관리", "원청 · 협력사 · 부서 구조를 트리로 관리", 1],
    ["", "카메라 관리"],
    ["cameras.html", "카메라 목록", "등록된 카메라와 관제화면 배치 · 사용 여부", 1],
    ["camera-edit.html", "카메라 등록 및 수정", "스트림 주소 · 이름 · 설치 구역을 입력해 카메라 등록", 1],
    ["camera-map.html", "카메라 배치도", "현장 도면 위에 카메라 위치와 보는 방향 표시", 1],
    ["", "알림 규칙"],
    ["alert-threshold.html", "판정 기준", "감지 유형별 confidence 기준과 다시 알리기까지의 쿨다운", 1],
    ["alert-severity.html", "심각도 기준", "감지 유형별 심각도 기본값 (ROI별 규칙이 없을 때 적용)", 1],
    ["alert-targets.html", "알림", "누가 어떤 수단으로 알림을 받을지 (후순위)", 1],
  ] },
];
MENU.forEach((g, i) => { g.no = String(i + 1); });

const EXTRA = {
  "index.html": ["0", "페이지 지도", "전체 화면 목록. 이름을 누르면 그 화면으로 이동", "이 폴더 안내"],
};

const ROLE_KO = { ADMIN: "관리자", MANAGER: "안전관리자", VIEWER: "조회 전용" };
// 로그인했으면(api.js 가 저장한 정보) 그 사람을, 아니면 예시 사람을 보여 준다
const USER = (() => {
  try {
    const u = JSON.parse(localStorage.getItem("safety.auth")).user;
    return { name: [u.name, u.position].filter(Boolean).join(" "), role: ROLE_KO[u.role], code: u.role };
  } catch (e) {
    return { name: "최동현 과장", role: "관리자", code: "ADMIN" };
  }
})();
const NAV_KEY = "safety.nav-open";

// ---------------------------------------------------------------- 역할별로 화면 가리기
// 권한이 모자란 사람에게는 쓰기 버튼을 아예 보이지 않게 한다. 서버도 따로 막으므로 화면만 정리하는 것.
//   data-need="MANAGER" | "ADMIN"  → 그 역할 미만이면 숨김 (common.css). 나중에 그리는 버튼에 붙여도 된다
//   data-lock="MANAGER" | "ADMIN"  → 그 안의 입력 칸을 보기 전용으로 (applyRoleLocks. 나중에 그린 칸은 그린 뒤 한 번 더 부른다)
//   data-lacks="MANAGER" | "ADMIN" → 반대로 그 역할 미만에게만 보임 ("조회 전용이라 바꿀 수 없습니다" 같은 안내)
const ROLE_RANK = { VIEWER: 1, MANAGER: 2, ADMIN: 3 };
document.documentElement.dataset.role = USER.code;

function can(need) {
  return (ROLE_RANK[USER.code] || 0) >= ROLE_RANK[need];
}

function applyRoleLocks(root = document) {
  root.querySelectorAll("[data-lock]").forEach((box) => {
    if (can(box.dataset.lock)) return;
    box.dataset.locked = "";
    box.querySelectorAll("input, select, textarea").forEach((el) => { el.disabled = true; });
  });
}
document.addEventListener("DOMContentLoaded", () => applyRoleLocks());

function currentFile() {
  return decodeURIComponent(location.pathname.split("/").pop()) || "index.html";
}

function realPages(group) {
  return group.pages.filter((p) => p[0]);
}

function findPage(file) {
  for (const group of MENU) {
    const pages = realPages(group);
    const i = pages.findIndex((p) => p[0] === file);
    if (i >= 0) return { group, index: i, page: pages[i] };
  }
  return null;
}

function pageNo(group, page) {
  return `${group.no}-${realPages(group).indexOf(page) + 1}`;
}

function readNav() {
  try { return localStorage.getItem(NAV_KEY) === "1"; } catch (e) { return false; }
}
function saveNav(open) {
  try { localStorage.setItem(NAV_KEY, open ? "1" : "0"); } catch (e) { /* 저장 못 해도 동작에는 문제 없음 */ }
}

function drawerHtml(file, found) {
  const groupHtml = (g) => {
    const open = found && found.group === g ? " open" : "";
    const items = g.pages.map((p) => {
      if (!p[0]) return `<div class="dlabel">${p[1]}</div>`;
      const on = p[0] === file ? " on" : "";
      return `<a class="ditem d${p[3] || 0}${on}" href="${p[0]}"><b>${pageNo(g, p)}</b>${p[1]}</a>`;
    }).join("");
    return `
      <section class="dgroup${open}">
        <button type="button" class="dgroup-btn" aria-expanded="${open ? "true" : "false"}">
          <i>${g.icon}</i><span>${g.name}</span><em class="chev" aria-hidden="true">▾</em>
        </button>
        <div class="dgroup-list">${items}</div>
      </section>`;
  };
  const work = MENU.filter((g) => !g.admin).map(groupHtml).join("");
  const admin = USER.code === "ADMIN" ? MENU.filter((g) => g.admin).map(groupHtml).join("") : "";
  return `
    <aside class="drawer" id="drawer" aria-label="전체 메뉴">
      <div class="drawer-head">
        <a class="brand" href="monitor.html"><i>▲</i>안전관제</a>
        <button type="button" class="drawer-x" id="drawer-x" aria-label="메뉴 닫기">✕</button>
      </div>
      <nav class="drawer-body">
        ${work}
        ${admin && `<div class="drawer-sep"><span>관리자 전용</span></div>${admin}`}
      </nav>
      <div class="drawer-foot">
        <a href="index.html">🗺 페이지 지도</a>
        <a href="login.html" data-logout>로그아웃</a>
      </div>
    </aside>
    <div class="scrim" id="scrim"></div>`;
}

function renderShell(file, found) {
  const where = !found ? ""
    : found.group.name === found.page[1] ? `<span class="gnb-where"><b>${found.group.name}</b></span>`
    : `<span class="gnb-where"><b>${found.group.name}</b> › ${found.page[1]}</span>`;
  document.body.insertAdjacentHTML("afterbegin", `
    ${drawerHtml(file, found)}
    <nav class="gnb">
      <button type="button" class="menu-btn" id="menu-btn" aria-label="메뉴 열기" aria-controls="drawer" aria-expanded="false">
        <span></span><span></span><span></span>
      </button>
      <a class="brand" href="monitor.html"><i>▲</i>안전관제</a>
      ${where}
      <span class="grow"></span>
      <div class="gnb-side">
        <div class="gnb-wx" id="gnb-wx" title="포항 송도동 날씨" hidden>
          <span class="wx-chip alert" id="wx-alert" hidden><b id="wx-alert-tag">주의</b><span id="wx-alert-text"></span></span>
          <span class="wx-chip"><span class="ico" id="wx-ico">⛅</span><b id="wx-temp">--°</b><span id="wx-sky"></span></span>
          <span class="wx-chip">체감 <b id="wx-feel">--°</b></span>
          <span class="wx-chip">풍속 <b id="wx-wind">--</b></span>
        </div>
        <button type="button" class="gnb-btn" id="gnb-alert" title="실시간 알림" aria-haspopup="dialog" aria-controls="alert-pop">🔔 알림 <span class="badge zero" id="alert-badge" hidden>0</span></button>
        <span class="gnb-user"><b>${USER.name}</b><br>${USER.role}</span>
        <a class="gnb-btn" href="login.html" data-logout>로그아웃</a>
      </div>
    </nav>`);

  const body = document.body;
  const btn = document.getElementById("menu-btn");
  const narrow = window.matchMedia("(max-width: 1100px)");
  const setOpen = (open, remember) => {
    body.classList.toggle("nav-open", open);
    btn.setAttribute("aria-expanded", open ? "true" : "false");
    if (remember) saveNav(open);
    // 넓은 화면에서는 본문이 옆으로 밀리므로 캔버스 같은 요소가 크기를 다시 잡게 한다
    setTimeout(() => window.dispatchEvent(new Event("resize")), 260);
  };
  // 처음 열 때는 움직이지 않고 바로 그 상태로 보이게 한다
  body.classList.add("nav-still");
  setOpen(!narrow.matches && readNav(), false);
  requestAnimationFrame(() => requestAnimationFrame(() => body.classList.remove("nav-still")));

  btn.addEventListener("click", () => setOpen(!body.classList.contains("nav-open"), !narrow.matches));
  document.getElementById("drawer-x").addEventListener("click", () => setOpen(false, !narrow.matches));
  document.getElementById("scrim").addEventListener("click", () => setOpen(false, false));
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && narrow.matches && body.classList.contains("nav-open")) setOpen(false, false);
  });
  document.querySelectorAll(".dgroup-btn").forEach((b) => b.addEventListener("click", () => {
    const g = b.closest(".dgroup");
    g.classList.toggle("open");
    b.setAttribute("aria-expanded", g.classList.contains("open") ? "true" : "false");
  }));
  document.querySelectorAll("[data-logout]").forEach((a) => a.addEventListener("click", () => {
    try { localStorage.removeItem("safety.auth"); } catch (e) { /* 무시 */ }
  }));
  document.getElementById("gnb-alert").addEventListener("click", () => {
    if (document.getElementById("alert-pop").hidden) openAlerts(); else closeAlerts();
  });
}

function renderHead(file, found) {
  // 브라우저 탭 제목도 메뉴 번호와 맞춘다
  if (found) document.title = `${pageNo(found.group, found.page)} ${found.page[1]} · 안전관제`;
  const head = document.querySelector("header.head");
  if (head && !head.children.length) {
    let no, groupName, title, text;
    if (found) {
      no = pageNo(found.group, found.page);
      groupName = found.group.name;
      [, title, text] = found.page;
    } else {
      const extra = EXTRA[file] || ["", document.title, "", ""];
      [no, title, text, groupName] = extra;
    }
    head.innerHTML = `
      <div class="where"><i class="dot"></i><b>${no}</b>${groupName}</div>
      <div class="title"><h1>${title}</h1><p>${text}</p></div>
      <div></div>`;
  }
}

/* ---------------------------------------------------------------- 실시간 알림 (헤더 🔔)
   어느 화면에서든 미처리 · 확인중 이벤트를 보여 준다. 30초마다 새로 불러오고, 새 미처리 이벤트가 오면 안내한다.
   api.js 가 없는 예시 화면에서도 쓰므로 로그인 토큰(safety.auth)을 직접 읽어 부른다. */
const ALERT_POLL_MS = 30 * 1000;
const ALERT_TONE = { HIGH: "stop", MEDIUM: "warn", LOW: "ok" };
let alertSeen = null; // 지금까지 본 미처리 이벤트 번호 (처음 불러올 때는 안내하지 않음)
let alertTimer = 0;

function authToken() {
  try { return JSON.parse(localStorage.getItem("safety.auth")).access_token; } catch (e) { return null; }
}
const escHtml = (t) => String(t ?? "").replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`);

// YOLO 탐지 영상: 서버가 탐지 박스 · ROI 를 그려 넣은 MJPEG. 관제화면(1-1) · 단일 카메라 확대(1-2)만 쓰고,
// 나머지 화면은 원본 영상(/videos/...)을 튼다. 서버에 YOLO 가 없으면 enabled = false
let detectStatusOnce = null;
function detectStatus() {
  return (detectStatusOnce ||= alertFetch("/api/stream/status").catch(() => ({ enabled: false, reason: "탐지 영상 상태를 확인하지 못했습니다." })));
}
// <img> 는 헤더를 못 붙여서 로그인 토큰을 주소에 붙인다
const detectSrc = (cam, roi = true) => `/api/stream/${cam.id}.mjpg?roi=${roi ? 1 : 0}&token=${encodeURIComponent(authToken() || "")}`;
// MJPEG 는 브라우저마다 load 이벤트가 달라서, 첫 장면이 들어왔는지 그림 크기로 확인한다
function waitFirstFrame(img, ms = 20000) {
  return new Promise((resolve, reject) => {
    const until = Date.now() + ms;
    img.addEventListener("error", () => reject(new Error("error")), { once: true });
    (function check() {
      if (img.naturalWidth) return resolve(img);
      if (!img.getAttribute("src") || Date.now() > until) return reject(new Error("timeout"));
      setTimeout(check, 200);
    })();
  });
}

async function alertFetch(path, options = {}) {
  const token = authToken();
  if (!token) throw new Error("login");
  const res = await fetch(path, { ...options, headers: { Authorization: "Bearer " + token, "Content-Type": "application/json" } });
  if (res.status === 401) throw new Error("login");
  if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || "알림을 불러오지 못했습니다.");
  return res.json();
}

function alertPopHtml() {
  return `
    <div class="pop" id="alert-pop" hidden>
      <div class="pop-card" role="dialog" aria-modal="true" aria-labelledby="alert-title">
        <div class="pop-head">
          <div>
            <span class="role">미처리 <b id="alert-left">0</b>건 · 확인중 <b id="alert-ack">0</b>건</span>
            <h2 id="alert-title">실시간 알림</h2>
            <p>처리가 끝나지 않은 이벤트 · 30초마다 새로 고침</p>
          </div>
          <button type="button" class="btn sm" id="alert-close">닫기</button>
        </div>
        <div class="feed" id="feed"></div>
        <div class="feed-foot">
          <span class="muted" id="alert-time"></span>
          <a href="events.html">지난 알림은 이벤트 목록에서 →</a>
        </div>
      </div>
    </div>`;
}

// items 는 최근 30건만, 숫자는 전체 건수(total)로 센다
function renderAlerts(items, newTotal, openTotal) {
  const canHandle = can("MANAGER");
  const fresh = items.filter((e) => e.status === "NEW");
  const badge = document.getElementById("alert-badge");
  badge.textContent = newTotal;
  badge.hidden = false;
  badge.classList.toggle("zero", newTotal === 0);
  document.getElementById("alert-left").textContent = newTotal;
  document.getElementById("alert-ack").textContent = openTotal - newTotal;
  document.getElementById("alert-time").textContent = "마지막 확인 " + new Date().toTimeString().slice(0, 8);
  document.getElementById("feed").innerHTML = items.length ? items.map((e) => {
    const conf = e.confidence == null ? "" : ` · 신뢰도 ${Math.round(e.confidence * 100)}%`;
    const ack = e.status === "NEW" && canHandle ? `<button type="button" class="mini-btn" data-ack="${e.id}">확인</button>` : "";
    const state = e.status === "NEW" ? '<span class="status stop">미처리</span>' : '<span class="status warn">확인중</span>';
    return `<div class="alert ${ALERT_TONE[e.severity]}${e.status === "ACK" ? " seen" : ""}">
      <time>${e.detected_at.slice(11, 16)}</time>
      <div><b>${escHtml(e.detection_label)} · ${escHtml(e.camera_name || "카메라 없음")}</b><small>EV-${e.id} · ${escHtml(e.work_zone_name || "구역 없음")}${conf}</small></div>
      <div class="acts">${state}${ack}<a class="mini-btn primary" href="${canHandle ? "event-handle" : "event-detail"}.html?id=${e.id}">${canHandle ? "처리" : "상세"}</a></div>
    </div>`;
  }).join("") : '<p class="muted" style="padding:18px 4px">처리할 알림이 없습니다 👍</p>';

  // 새로 들어온 미처리 이벤트가 있으면 안내
  const ids = new Set(fresh.map((e) => e.id));
  if (alertSeen) {
    const added = fresh.filter((e) => !alertSeen.has(e.id));
    if (added.length) {
      toast(`🔔 새 알림: ${added[0].detection_label}${added.length > 1 ? ` 외 ${added.length - 1}건` : ""}`);
      badge.classList.remove("ping");
      void badge.offsetWidth; // 애니메이션 다시 시작
      badge.classList.add("ping");
    }
  }
  alertSeen = ids;
}

function loadAlerts() {
  return Promise.all([alertFetch("/api/events?status=NEW&status=ACK&size=30"), alertFetch("/api/events?status=NEW&size=1")])
    .then(([open, fresh]) => renderAlerts(open.items, fresh.total, open.total))
    .catch((err) => {
      if (err.message === "login") {
        // 로그인 전(예시로 여는 화면)에는 숫자 없이 두고, 팝업에서 로그인을 안내
        clearInterval(alertTimer);
        document.getElementById("feed").innerHTML = '<p class="muted" style="padding:18px 4px">로그인하면 실시간 알림을 볼 수 있습니다. <a href="login.html" style="color:var(--orange)">로그인 →</a></p>';
      } else {
        document.getElementById("alert-time").textContent = err.message;
      }
    });
}

function openAlerts() {
  const pop = document.getElementById("alert-pop");
  pop.hidden = false;
  document.getElementById("gnb-alert").setAttribute("aria-expanded", "true");
  document.getElementById("alert-close").focus();
  loadAlerts();
}

function closeAlerts() {
  const pop = document.getElementById("alert-pop");
  if (!pop) return;
  pop.hidden = true;
  document.getElementById("gnb-alert").setAttribute("aria-expanded", "false");
}

function wireAlerts() {
  document.body.insertAdjacentHTML("beforeend", alertPopHtml());
  const pop = document.getElementById("alert-pop");
  pop.addEventListener("click", async (e) => {
    if (e.target === pop || e.target.closest("#alert-close")) return closeAlerts();
    const ack = e.target.closest("[data-ack]");
    if (!ack) return;
    ack.disabled = true;
    try {
      await alertFetch(`/api/events/${ack.dataset.ack}/actions`, { method: "POST", body: JSON.stringify({ action_type: "ACK" }) });
      await loadAlerts();
    } catch (err) {
      toast(err.message === "login" ? "로그인이 필요합니다." : err.message);
      ack.disabled = false;
    }
  });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeAlerts(); });
  loadAlerts();
  alertTimer = setInterval(loadAlerts, ALERT_POLL_MS);
  if (location.hash === "#alerts") openAlerts();
}

/* ---------------------------------------------------------------- 헤더 날씨 */
function skyIcon(name) {
  name = name || "";
  if (name.includes("비 또는 눈") || name.includes("빗방울/눈날림")) return "🌨️";
  if (name.includes("눈")) return "🌨️";
  if (name.includes("비") || name.includes("소나기") || name.includes("빗방울")) return "☔";
  if (name.includes("구름")) return "⛅";
  if (name.includes("흐림")) return "☁️";
  if (name.includes("맑음")) return "☀️";
  return "⛅";
}
const firstNumber = (text) => { const m = (text || "").match(/-?\d+(?:\.\d+)?/); return m ? m[0] : "--"; };
const gapUnit = (text) => (text || "--").replace(/([가-힣])(\d)/, "$1 $2");

// 지금 시각의 관측값. 없으면 그 앞 시각, 그래도 없으면(자정 직후 등) 파일에 있는 가장 늦은 시각 것
function currentSlot(data) {
  const now = new Date().getHours();
  const hours = [...Array(24).keys()];
  const order = [...hours.slice(0, now + 1).reverse(), ...hours.slice(now + 1).reverse()];
  for (const h of order) {
    const slot = data[pad2(h) + "시"];
    if (slot && slot.온도) return slot;
  }
  return null;
}

// 특보 · 폭염 정보가 있으면 빨간 칩으로
function weatherAlert(data, slot) {
  const bits = [(data.특보 || "").trim(), ((slot && slot.폭염) || "").trim()]
    .filter((t) => t && t !== "--" && !t.includes("없"));
  return bits.join(" · ");
}

function renderWeather(data) {
  const box = document.getElementById("gnb-wx");
  const slot = currentSlot(data);
  if (!box || !slot) return;
  document.getElementById("wx-ico").textContent = skyIcon(slot.날씨);
  document.getElementById("wx-temp").textContent = firstNumber(slot.온도) + "°";
  document.getElementById("wx-sky").textContent = slot.날씨 || "";
  document.getElementById("wx-feel").textContent = firstNumber(slot.체감온도) + "°";
  document.getElementById("wx-wind").textContent = gapUnit(slot.풍속);
  const alertText = weatherAlert(data, slot);
  const chip = document.getElementById("wx-alert");
  chip.hidden = !alertText;
  chip.title = alertText;
  document.getElementById("wx-alert-tag").textContent = /경보|위험/.test(alertText) ? "경보" : "주의";
  document.getElementById("wx-alert-text").textContent = alertText;
  box.hidden = false;
}

function loadWeather() {
  fetch("../weather/weather.json?t=" + Date.now())
    .then((res) => { if (!res.ok) throw new Error("weather"); return res.json(); })
    .then(renderWeather)
    .catch(() => { /* 날씨 파일이 없으면 헤더에서 날씨 칸을 숨긴 채로 둔다 */ });
}

/* ---------------------------------------------------------------- 검색 조건 칸
   목록 화면 맨 위의 .searchbar 안에서 [data-search-toggle] 버튼을 누르면 .search-panel 이 내려온다.
   검색 조건이 바뀌면 화면 쪽에서 searchSummary("오늘 · 미처리 외 2") 처럼 요약을 버튼 옆에 적는다. */
function setSearchOpen(bar, open) {
  const panel = bar.querySelector(".search-panel");
  const btn = bar.querySelector("[data-search-toggle]");
  panel.hidden = !open;
  bar.classList.toggle("open", open);
  btn.setAttribute("aria-expanded", open ? "true" : "false");
}

function searchSummary(text) {
  document.querySelectorAll(".searchbar .search-sum").forEach((el) => {
    el.textContent = text || "";
    el.hidden = !text;
  });
}

/* 기간 고르기: 시작일 · 끝일 달력 두 칸을 묶는다. 끝일이 시작일보다 앞서지 않게 서로 min · max 를 맞추고,
   한쪽을 반대쪽 너머로 옮기면 다른 쪽을 같은 날로 따라 옮긴다 */
function linkDateRange(fromEl, toEl) {
  const sync = () => {
    toEl.min = fromEl.value || "";
    fromEl.max = toEl.value || "";
  };
  fromEl.addEventListener("change", () => { if (fromEl.value && toEl.value && toEl.value < fromEl.value) toEl.value = fromEl.value; sync(); });
  toEl.addEventListener("change", () => { if (fromEl.value && toEl.value && fromEl.value > toEl.value) fromEl.value = toEl.value; sync(); });
  sync();
  return sync; // 값을 코드로 바꾼 뒤 다시 맞출 때 부른다
}

// "2026.10.01 ~ 10.07" (같은 날이면 하루만)
function rangeText(from, to) {
  const d = (s) => s.replaceAll("-", ".");
  if (!from && !to) return "";
  if (!from || !to || from === to) return d(from || to);
  return `${d(from)} ~ ${from.slice(0, 4) === to.slice(0, 4) ? d(to).slice(5) : d(to)}`;
}

function closeSearch() {
  document.querySelectorAll(".searchbar").forEach((bar) => setSearchOpen(bar, false));
}

function toast(msg) {
  let el = document.querySelector(".toast");
  if (!el) {
    el = document.createElement("div");
    el.className = "toast";
    document.body.appendChild(el);
  }
  el.textContent = msg;
  el.classList.add("show");
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => el.classList.remove("show"), 2200);
}

function pad2(n) { return String(n).padStart(2, "0"); }
function tickClock() {
  const now = new Date();
  const time = pad2(now.getHours()) + ":" + pad2(now.getMinutes()) + ":" + pad2(now.getSeconds());
  document.querySelectorAll(".js-cam-time").forEach((el) => { el.textContent = time; });
}

function wireCommon() {
  // 표의 줄을 누르면 data-href 화면으로 이동
  document.querySelectorAll("[data-href]").forEach((el) => {
    el.addEventListener("click", (e) => {
      if (e.target.closest("a, button, .switch, input, select")) return;
      location.href = el.dataset.href;
    });
  });
  // 칩: data-single 이 있으면 하나만, 없으면 여러 개 선택
  document.querySelectorAll(".chips").forEach((box) => {
    box.querySelectorAll(".chip").forEach((chip) => chip.addEventListener("click", () => {
      if (box.hasAttribute("data-single")) box.querySelectorAll(".chip").forEach((c) => c.classList.remove("on"));
      chip.classList.toggle("on", box.hasAttribute("data-single") ? true : !chip.classList.contains("on"));
    }));
  });
  // 켜기 / 끄기 스위치
  document.querySelectorAll(".switch").forEach((sw) => sw.addEventListener("click", () => sw.classList.toggle("on")));
  // 같은 목록 안에서 하나만 선택 (data-pick)
  document.querySelectorAll("[data-pick]").forEach((box) => {
    box.querySelectorAll(".tc-card, .thumb, .pager").forEach((card) => card.addEventListener("click", () => {
      box.querySelectorAll(".tc-card, .thumb, .pager").forEach((c) => c.classList.remove("active", "on"));
      card.classList.add(card.classList.contains("tc-card") ? "active" : "on");
    }));
  });
  // 저장 · 삭제처럼 데이터베이스가 필요한 버튼
  document.querySelectorAll("[data-toast]").forEach((el) => el.addEventListener("click", (e) => {
    e.preventDefault();
    toast(el.dataset.toast || "예시 화면입니다. 데이터베이스를 연결하면 실제로 동작합니다.");
  }));
  // 범위 슬라이더 옆 숫자
  document.querySelectorAll("input[type=range][data-out]").forEach((r) => {
    const out = document.getElementById(r.dataset.out);
    const show = () => { out.textContent = r.value + (r.dataset.unit || ""); };
    r.addEventListener("input", show);
    show();
  });
  document.querySelectorAll(".searchbar").forEach((bar) => {
    bar.querySelector("[data-search-toggle]").addEventListener("click", () => {
      setSearchOpen(bar, !bar.classList.contains("open"));
    });
    bar.querySelectorAll("[data-search-close]").forEach((b) => b.addEventListener("click", () => setSearchOpen(bar, false)));
    bar.addEventListener("keydown", (e) => { if (e.key === "Escape" && bar.classList.contains("open")) setSearchOpen(bar, false); });
    // 예시 화면(data-auto-summary): 칩 묶음마다 첫 칩("전체")이 아닌 것을 골랐으면 버튼 옆에 적는다
    const panel = bar.querySelector(".search-panel[data-auto-summary]");
    if (panel) panel.addEventListener("click", (e) => {
      if (!e.target.closest(".chip")) return;
      searchSummary([...panel.querySelectorAll(".chips")].map((box) => {
        const on = box.querySelector(".chip.on");
        return on && on !== box.querySelector(".chip") ? on.firstChild.textContent.trim() : "";
      }).filter(Boolean).join(" · "));
    });
  });
  // data-open="팝업id" 버튼은 팝업을 열고, 팝업 안의 [data-close] 나 바깥 영역은 닫는다
  document.querySelectorAll("[data-open]").forEach((b) => b.addEventListener("click", () => {
    const pop = document.getElementById(b.dataset.open);
    if (pop) pop.hidden = false;
  }));
  document.querySelectorAll(".pop").forEach((pop) => {
    pop.addEventListener("click", (e) => { if (e.target === pop || e.target.closest("[data-close]")) pop.hidden = true; });
  });
}

(function init() {
  const file = currentFile();
  const found = findPage(file);
  if (!document.body.hasAttribute("data-no-gnb")) {
    renderShell(file, found);
    wireAlerts();
    loadWeather();
    setInterval(loadWeather, 10 * 60 * 1000);
  }
  renderHead(file, found);
  wireCommon();
  tickClock();
  setInterval(tickClock, 1000);
})();
