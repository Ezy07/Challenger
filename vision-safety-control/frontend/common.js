/* 모든 화면이 함께 쓰는 스크립트
   - 화면 목록(MENU)을 한 곳에 모아 두고, 상단 바 · 왼쪽 메뉴(☰) · 제목 칸 · 하위 화면 탭을 여기서 그린다
   - 메뉴 구성은 「비전AI 안전관제 페이지 구성 1차.txt」를 그대로 따른다
   - 화면을 추가하려면 MENU 에 [파일 이름, 화면 이름, 설명, 깊이] 한 줄만 넣으면 된다
     깊이 0 = 메모장의 "-" 화면, 1 = "ㄴ" 화면, 2 = "ㄴㄴ" 화면
     파일 이름이 빈 줄("")은 메뉴 안의 소제목으로만 쓴다 (예: 관리자 > 카메라 관리)
     다섯째 칸 { hide: true } = 메뉴에는 안 보이고 목록에서 한 항목을 골라 들어가는 화면 (번호도 차지하지 않음)
              { need: "MANAGER" } = 그 역할 미만이면 메뉴에서 빠지고, 주소로 열어도 관제화면으로 돌려보낸다
     묶음의 admin: true = 왼쪽 메뉴 "관리자 전용" 칸에 둔다 (need 를 같이 주면 화면도 막는다)
   - 아직 API 를 연결하지 않은 화면의 저장 · 삭제 버튼은 안내 문구(toast)만 띄운다
   - API 를 쓰는 화면은 api.js 를 이 파일보다 먼저 넣는다 */

(function bootModeChange() {
  const base = document.currentScript && document.currentScript.src;
  const src = base ? new URL("mode_change.js", base).href : "mode_change.js";
  if (document.readyState === "loading") {
    document.write('<script src="' + src + '"><\/script>');
    return;
  }
  const tag = document.createElement("script");
  tag.src = src;
  document.head.appendChild(tag);
})();

const MENU = [
  { icon: "▣", name: "관제화면", pages: [
    ["monitor.html", "관제화면", "CCTV 4분할 · TC/작업구역 · 섹터 감지경보 · 특별관리근로자", 0],
    ["monitor-camera.html", "카메라 상세", "카메라 한 대를 크게 보면서 ROI · 탐지 박스 · 최근 이벤트 확인", 1],
  ] },
  { icon: "◫", name: "구역 및 작업", pages: [
    ["zones.html", "전체 구역 표시", "현장 배치도 위에 작업구역과 구역별 작업 · 인원 · 장비 · 경보를 표시", 0],
    ["zone-works.html", "구역별 작업 목록", "구역을 고르면 그 구역에서 오늘 진행하는 작업을 보여 줌", 1],
    ["works.html", "작업 등록 및 배정", "작업을 만들고 구역 · 담당자 · 작업자를 배정", 0, { need: "MANAGER" }],
    ["work-workers.html", "작업별 장비 · 작업자 목록", "작업 하나에 배정된 작업자 · 특별관리 대상과 그 구역에 투입된 장비 · 운전원 · 상태", 2, { hide: true }],
  ] },
  { icon: "≡", name: "이벤트", pages: [
    ["events.html", "이벤트 목록", "날짜 · 구역 · 종류 · 심각도로 지난 이벤트를 찾고 CSV로 내보내기", 0],
    ["event-detail.html", "이벤트 상세", "이벤트 하나의 스냅샷 · 탐지 정보 · 처리 상태", 1, { hide: true }],
    ["event-snapshot.html", "스냅샷 조회 및 저장", "탐지 순간 이미지를 크게 보고 내려받기", 2, { hide: true }],
    ["event-handle.html", "처리 기록", "확인 · 조치 · 오탐 처리와 메모를 시간순으로 기록", 2, { hide: true }],
    ["event-export.html", "내보내기", "이벤트 목록의 [내보내기]로 여는 화면. 조건을 골라 CSV · 엑셀 · 스냅샷 묶음으로 받기", 1],
  ] },
  { icon: "▤", name: "통계", pages: [
    ["stats.html", "요약", "기간별 건수 · 처리율 · 처리 시간과 종류 · 구역별 건수", 0],
    ["stats-trend.html", "추이 차트", "일별 · 시간대별로 이벤트가 늘거나 줄었는지 확인", 0],
    ["stats-report.html", "보고서", "기간을 골라 요약 보고서를 만들고 인쇄 (인쇄 창에서 PDF로 저장)", 0],
  ] },
  { icon: "⚙", name: "장비", pages: [
    ["equipment.html", "장비 목록", "현장 중장비와 현재 상태 (하루 한 번 수동 업데이트)", 0],
    ["equipment-assign.html", "장비 등록 및 배정", "중장비를 등록하고 투입 구역 · 운전원을 지정", 0, { need: "MANAGER" }],
    ["equipment-detail.html", "장비 상세", "장비 한 대의 일일 기록 · 투입 구역 · 구비 서류와 안전교육", 0, { hide: true }],
  ] },
  { icon: "✚", name: "작업자", pages: [
    ["workers.html", "현장작업자 관리", "현장작업자 등록 · 수정 · 삭제", 0],
    ["worker-special.html", "특별관리 지정", "고령 · 고혈압 · 신규 투입 등 특별관리 대상 지정과 해제", 0, { need: "MANAGER" }],
  ] },
  { icon: "⬠", name: "ROI", admin: true, need: "ADMIN", pages: [
    ["roi-draw.html", "ROI 그리기", "카메라 화면 위를 클릭해 감지 영역(ROI) 다각형 그리기", 0],
    ["roi-list.html", "ROI 목록", "만든 ROI 전체를 보고 켜고 끄기", 0],
  ] },
  { icon: "◆", name: "관리자", admin: true, need: "ADMIN", pages: [
    ["", "회원 관리"],
    ["users.html", "회원 목록", "회원 조회 · 등록 · 삭제", 0],
    ["user-approval.html", "회원가입 승인", "가입 신청한 사람을 확인하고 승인 · 반려", 1],
    ["user-edit.html", "회원정보 수정", "기본 정보와 역할(권한) · 계정 상태 바꾸기", 1, { hide: true }],
    ["org.html", "조직 · 부서 관리", "원청 · 협력사 · 부서 구조를 트리로 관리", 1],
    ["", "카메라 관리"],
    ["cameras.html", "카메라 목록", "등록된 카메라와 관제화면 배치 · 사용 여부", 1],
    ["camera-edit.html", "카메라 등록 및 수정", "스트림 주소 · 이름 · 설치 구역을 입력해 카메라 등록", 1, { hide: true }],
    ["camera-map.html", "카메라 배치도", "현장 도면 위에 카메라 위치와 시야 표시", 1],
    ["", "알림 규칙"],
    ["alert-threshold.html", "판정 기준", "감지 유형별 confidence 기준과 다시 알리기까지의 쿨다운", 1],
    ["alert-severity.html", "심각도 기준", "감지 유형별 심각도 기본값 (ROI별 규칙이 없을 때 적용)", 1],
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

// 그 화면을 열 수 있는 가장 낮은 역할 (없으면 로그인만 하면 됨)
function pageNeed(group, page) {
  return (page[4] && page[4].need) || group.need || null;
}

function pageNo(group, page) {
  const shown = realPages(group).filter((p) => !(p[4] && p[4].hide));
  let i = shown.indexOf(page);
  if (i < 0) {
    const all = realPages(group);
    i = all.slice(0, all.indexOf(page)).filter((p) => !(p[4] && p[4].hide)).length - 1;
  }
  return `${group.no}-${i + 1}`;
}

function readNav() {
  try { return localStorage.getItem(NAV_KEY) === "1"; } catch (e) { return false; }
}
function saveNav(open) {
  try { localStorage.setItem(NAV_KEY, open ? "1" : "0"); } catch (e) { /* 저장 못 해도 동작에는 문제 없음 */ }
}

// 메뉴에서 다른 화면으로 넘어가도, 펼쳐 둔 묶음과 스크롤 위치는 이 탭에서 유지한다
const NAV_GROUPS_KEY = "safety.nav-groups";
const NAV_SCROLL_KEY = "safety.nav-scroll";
function readOpenGroups() {
  try {
    const list = JSON.parse(sessionStorage.getItem(NAV_GROUPS_KEY) || "[]");
    return new Set(Array.isArray(list) ? list : []);
  } catch (e) { return new Set(); }
}
function saveOpenGroups(names) {
  try { sessionStorage.setItem(NAV_GROUPS_KEY, JSON.stringify(names)); } catch (e) { /* 저장 못 해도 동작에는 문제 없음 */ }
}
function readDrawerScroll() {
  try {
    const n = Number(sessionStorage.getItem(NAV_SCROLL_KEY));
    return Number.isFinite(n) && n > 0 ? n : 0;
  } catch (e) { return 0; }
}
function saveDrawerScroll(y) {
  try { sessionStorage.setItem(NAV_SCROLL_KEY, String(y)); } catch (e) { /* 저장 못 해도 동작에는 문제 없음 */ }
}

function drawerHtml(file, found) {
  const opened = readOpenGroups();
  if (found) opened.add(found.group.no);
  const groupHtml = (g) => {
    const open = opened.has(g.no);
    if (g.link) {
      const here = file === g.link || (found && found.group === g);
      return `
      <section class="dgroup">
        <a class="dgroup-btn${here ? " on" : ""}" href="${g.link}">
          <i>${g.icon}</i><span>${g.name}</span>
        </a>
      </section>`;
    }
    const items = g.pages.map((p) => {
      if (!p[0]) return `<div class="dlabel">${p[1]}</div>`;
      if ((p[4] && p[4].hide) || (pageNeed(g, p) && !can(pageNeed(g, p)))) return "";
      const on = p[0] === file ? " on" : "";
      return `<a class="ditem d${p[3] || 0}${on}" href="${p[0]}"><b>${pageNo(g, p)}</b>${p[1]}</a>`;
    }).join("");
    return `
      <section class="dgroup${open ? " open" : ""}" data-group="${g.no}">
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
        <div class="mode-change" id="mode-change" role="group" aria-label="화면 모드">
          <button type="button" data-mode-set="light" aria-pressed="false">☀ 라이트</button>
          <button type="button" data-mode-set="dark" aria-pressed="true">☾ 다크</button>
        </div>
        <div class="text-size" role="group" aria-label="글자 크기">
          <span>글자 크기</span>
          <button type="button" data-text-step="-1" title="글자 작게" aria-label="글자 작게">－</button>
          <b id="text-size-now">100%</b>
          <button type="button" data-text-step="1" title="글자 크게" aria-label="글자 크게">＋</button>
        </div>
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
        <span class="wx-chip gnb-clock"><b id="now-time">--:--:--</b><span id="now-date">----.--.--</span></span>
        <div class="gnb-wx" id="gnb-wx" title="포항 송도동 날씨" hidden>
          <span class="wx-chip alert" id="wx-alert" hidden><b id="wx-alert-tag">주의</b><span id="wx-alert-text"></span></span>
          <span class="wx-chip"><span class="ico" id="wx-ico">⛅</span><b id="wx-temp">--°</b><span id="wx-sky"></span></span>
          <span class="wx-chip">체감 <b id="wx-feel">--°</b></span>
          <span class="wx-chip">풍속 <b id="wx-wind">--</b></span>
        </div>
        <button type="button" class="gnb-btn" id="gnb-alert" title="실시간 알림" aria-haspopup="dialog" aria-controls="alert-pop">🔔<span class="gnb-label">알림</span> <span class="badge zero" id="alert-badge" hidden>0</span></button>
        <div class="gnb-me">
          <button type="button" class="gnb-btn gnb-me-btn" id="me-btn" title="내 계정" aria-haspopup="menu" aria-expanded="false" aria-controls="me-menu">
            <span class="gnb-ico" id="me-ico" aria-hidden="true">👤</span><span class="gnb-user"><b>${USER.name}</b><small>${USER.role}</small></span><i class="chev" aria-hidden="true">▾</i>
          </button>
          <div class="me-menu" id="me-menu" role="menu" hidden>
            <button type="button" role="menuitem" id="me-edit">👤 회원정보 수정</button>
            <a role="menuitem" href="login.html" data-logout>↪ 로그아웃</a>
          </div>
        </div>
      </div>
    </nav>
    <div class="pop" id="me-pop" hidden>
      <div class="pop-card" role="dialog" aria-modal="true" aria-labelledby="me-title">
        <div class="pop-head">
          <div>
            <span class="role">내 계정</span>
            <h2 id="me-title">회원정보 수정</h2>
            <p>사진 · 휴대폰 알림 · 이름 · 전화번호 · 비밀번호를 바꿀 수 있습니다. 사진 · 알림은 고르면 바로 저장됩니다.</p>
          </div>
          <button type="button" class="x-btn" data-close title="닫기" aria-label="닫기">✕</button>
        </div>
        <form class="pop-body" id="me-form">
          <div class="photo-field" id="me-photo"></div>
          <div class="push-box" id="push-box">
            <b>📱 이 기기로 알림 받기</b>
            <select class="input" id="push-sev" aria-label="받을 심각도">
              <option value="HIGH">높음만</option>
              <option value="MEDIUM" selected>중간 이상</option>
              <option value="LOW">전체</option>
            </select>
            <button type="button" class="mini-btn primary" id="push-toggle" disabled>켜기</button>
            <button type="button" class="mini-btn" id="push-test" hidden>테스트</button>
            <div class="push-zones">
              <span class="muted">받을 구역</span>
              <div class="chips" id="push-zones" role="group" aria-label="받을 구역"></div>
              <label class="push-high" id="push-high-row" hidden><input type="checkbox" id="push-high" checked /> 높음은 구역과 상관없이 받기</label>
            </div>
            <small class="muted" id="push-note"></small>
          </div>
          <label class="field">이름<input class="input" id="me-name" maxlength="50" required /></label>
          <label class="field">전화번호<input class="input" id="me-phone" maxlength="20" placeholder="010-0000-0000" autocomplete="tel" /></label>
          <label class="field">비밀번호<input class="input" id="me-pw" type="password" maxlength="72" placeholder="바꾸지 않으면 비워 두세요" autocomplete="new-password" /></label>
          <label class="field">비밀번호 확인<input class="input" id="me-pw2" type="password" maxlength="72" autocomplete="new-password" /></label>
          <div class="row end"><button type="button" class="btn" data-close>취소</button><button type="submit" class="btn primary">저장</button></div>
        </form>
      </div>
    </div>`);

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
  const drawerBody = document.querySelector(".drawer-body");
  const rememberDrawer = () => {
    saveOpenGroups([...document.querySelectorAll(".dgroup.open")].map((g) => g.dataset.group));
    saveDrawerScroll(drawerBody.scrollTop);
  };
  drawerBody.scrollTop = readDrawerScroll();
  drawerBody.addEventListener("scroll", () => saveDrawerScroll(drawerBody.scrollTop), { passive: true });
  document.querySelectorAll("button.dgroup-btn").forEach((b) => b.addEventListener("click", () => {
    const g = b.closest(".dgroup");
    g.classList.toggle("open");
    b.setAttribute("aria-expanded", g.classList.contains("open") ? "true" : "false");
    rememberDrawer();
  }));
  document.querySelectorAll(".drawer a").forEach((a) => a.addEventListener("click", rememberDrawer));
  document.querySelectorAll("[data-logout]").forEach((a) => a.addEventListener("click", () => {
    try { localStorage.removeItem("safety.auth"); } catch (e) { /* 무시 */ }
  }));
  wireMeMenu();
  wireMeEdit();
  paintMeIcon((savedAuthUser() || {}).photo_url);
  wireTextSize();
  document.getElementById("gnb-alert").addEventListener("click", () => {
    if (document.getElementById("alert-pop").hidden) openAlerts(); else closeAlerts();
  });
  if (typeof mountModeChange === "function") mountModeChange();
}

// 헤더 로그인 사용자를 누르면 아래로 펼치는 메뉴 (회원정보 수정 · 로그아웃). 바깥을 누르거나 Esc 면 닫힌다
function wireMeMenu() {
  const btn = document.getElementById("me-btn");
  const menu = document.getElementById("me-menu");
  const setOpen = (open) => {
    menu.hidden = !open;
    btn.setAttribute("aria-expanded", open ? "true" : "false");
  };
  btn.addEventListener("click", () => setOpen(menu.hidden));
  menu.addEventListener("click", (e) => { if (e.target.closest("[role=menuitem]")) setOpen(false); });
  document.addEventListener("click", (e) => { if (!menu.hidden && !e.target.closest(".gnb-me")) setOpen(false); });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && !menu.hidden) { setOpen(false); btn.focus(); }
  });
}

// 글자 크기: 본문(.page · 관제화면 .board) · 팝업을 zoom 으로 키우고 줄인다. 이 브라우저에 기억하고,
// 화면을 열 때 깜빡이지 않게 각 화면 <head> 의 첫 스크립트도 같은 값을 먼저 넣는다
const TEXT_ZOOM_KEY = "safety.text-zoom";
const TEXT_ZOOMS = [0.8, 0.9, 1, 1.1, 1.2, 1.3];
function textZoom() {
  try { const z = Number(localStorage.getItem(TEXT_ZOOM_KEY)); return TEXT_ZOOMS.includes(z) ? z : 1; } catch (e) { return 1; }
}
function applyTextZoom(z) {
  document.documentElement.style.setProperty("--text-zoom", z);
  const now = document.getElementById("text-size-now");
  if (now) now.textContent = Math.round(z * 100) + "%";
  document.querySelectorAll("[data-text-step]").forEach((b) => {
    const i = TEXT_ZOOMS.indexOf(z) + Number(b.dataset.textStep);
    b.disabled = i < 0 || i >= TEXT_ZOOMS.length;
  });
  window.dispatchEvent(new Event("resize")); // 캔버스 · 배치도처럼 크기를 재는 요소가 다시 잡게
}
// 글자 크기(zoom) 안 요소의 크기. getBoundingClientRect 는 화면에 보이는(키운) 크기라,
// 그 값으로 style 에 px 를 넣으면 한 번 더 키워진다 → zoom 으로 나눈 크기를 쓴다
function layoutSize(el) {
  const r = el.getBoundingClientRect();
  const z = el.currentCSSZoom || Number(getComputedStyle(document.documentElement).getPropertyValue("--text-zoom")) || 1;
  return { width: r.width / z, height: r.height / z };
}
function wireTextSize() {
  applyTextZoom(textZoom());
  document.querySelectorAll("[data-text-step]").forEach((b) => b.addEventListener("click", () => {
    const z = TEXT_ZOOMS[TEXT_ZOOMS.indexOf(textZoom()) + Number(b.dataset.textStep)];
    if (z === undefined) return;
    try { localStorage.setItem(TEXT_ZOOM_KEY, String(z)); } catch (e) { /* 기억 못 해도 이번 화면은 바뀜 */ }
    applyTextZoom(z);
  }));
}

// 회원 목록의 최동현 과장(이름 최동현, 직급 과장)을 로그인 전 초기값으로 쓴다.
const ME_FALLBACK = { name: "최동현", phone: "" };

function savedAuthUser() {
  try { return JSON.parse(localStorage.getItem("safety.auth")).user; } catch (e) { return null; }
}

function fillMeForm(user) {
  const box = document.getElementById("me-photo");
  if (user && user.id) {
    mountPhotoField(box, { path: `/api/users/${user.id}/photo`, person: user, onChange: (url) => {
      user.photo_url = url;
      try {
        const auth = JSON.parse(localStorage.getItem("safety.auth"));
        auth.user.photo_url = url;
        localStorage.setItem("safety.auth", JSON.stringify(auth));
      } catch (err) { /* 다음 로그인 때 반영 */ }
      paintMeIcon(url);
      document.dispatchEvent(new CustomEvent("profile-changed", { detail: user }));
    } });
  } else {
    box.innerHTML = "";
  }
  document.getElementById("me-name").value = (user && user.name) || ME_FALLBACK.name;
  document.getElementById("me-phone").value = (user && user.phone) || ME_FALLBACK.phone;
  document.getElementById("me-pw").value = "";
  document.getElementById("me-pw2").value = "";
}

function wireMeEdit() {
  const btn = document.getElementById("me-edit");
  const pop = document.getElementById("me-pop");
  const form = document.getElementById("me-form");
  if (!btn || !pop || !form) return;
  btn.addEventListener("click", async () => {
    fillMeForm(savedAuthUser());
    pop.hidden = false;
    loadPush();
    if (!authToken()) return;
    try { fillMeForm(await alertFetch("/api/auth/me")); } catch (e) { /* 저장해 둔 값을 유지 */ }
  });
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const name = document.getElementById("me-name").value.trim();
    const phone = document.getElementById("me-phone").value.trim();
    const pw = document.getElementById("me-pw").value;
    const pw2 = document.getElementById("me-pw2").value;
    if (!name) { toast("이름을 입력하세요."); return; }
    if (pw || pw2) {
      if (pw !== pw2) { toast("비밀번호가 서로 다릅니다."); return; }
      if (pw.length < 8) { toast("비밀번호는 8자 이상이어야 합니다."); return; }
    }
    if (!authToken()) { toast("로그인 후 저장할 수 있습니다."); return; }
    const body = { name, phone: phone || null };
    if (pw) body.password = pw;
    try {
      const user = await alertFetch("/api/auth/me", { method: "PATCH", body: JSON.stringify(body) });
      try {
        const auth = JSON.parse(localStorage.getItem("safety.auth"));
        auth.user = user;
        localStorage.setItem("safety.auth", JSON.stringify(auth));
      } catch (err) { /* 다음 화면에서 다시 읽는다 */ }
      const label = [user.name, user.position].filter(Boolean).join(" ");
      document.querySelectorAll(".gnb-user b").forEach((el) => { el.textContent = label; });
      document.dispatchEvent(new CustomEvent("profile-changed", { detail: user }));
      try { localStorage.setItem("safety.profileChanged", JSON.stringify({ at: Date.now(), user })); } catch (err2) { /* 다른 창은 다음 새로 고침 때 반영 */ }
      pop.hidden = true;
      toast("회원정보를 저장했습니다.");
    } catch (err) {
      toast(err.message === "login" ? "로그인이 필요합니다." : (err.message || "저장하지 못했습니다."));
    }
  });
}

function renderHead(file, found) {
  // 브라우저 탭 제목도 메뉴 번호와 맞춘다
  if (found) document.title = `${pageNo(found.group, found.page)} ${found.page[1]} · 안전관제`;
  const head = document.querySelector("header.head");
  if (head && !head.querySelector(".title")) {
    let title, text;
    if (found) {
      [, title, text] = found.page;
    } else {
      const extra = EXTRA[file] || ["", document.title, "", ""];
      [, title, text] = extra;
    }
    // 버튼 자리 통일: 왼쪽 = 뒤로(←, <header data-back="목록.html">) · 제목, 오른쪽 = 화면의 주요 행동(<header> 안 .head-acts)
    const acts = head.querySelector(".head-acts");
    const back = head.dataset.back;
    head.innerHTML = `
      <div class="head-l">
        ${back ? `<a class="head-back" id="head-back" href="${back}" title="뒤로" aria-label="뒤로">←</a>` : ""}
        <div class="title"><h1>${title}</h1><p>${text}</p></div>
      </div>`;
    if (acts) head.append(acts);
  }
}
// 뒤로(←) 가 갈 곳이 불러온 데이터에 따라 바뀌는 화면 (예: 처리 기록 → 그 이벤트의 상세)
function setBack(href) {
  const a = document.getElementById("head-back");
  if (a) a.href = href;
}

/* ---------------------------------------------------------------- 실시간 알림 (헤더 🔔)
   어느 화면에서든 미처리 · 확인중 이벤트를 보여 준다. 30초마다 새로 불러오고, 새 미처리 이벤트가 오면 안내한다.
   작업 허가 대기 중(holding)인 이벤트가 하나라도 있으면 허가될 때까지 🔔 배지가 계속 경보한다.
   api.js 가 없는 예시 화면에서도 쓰므로 로그인 토큰(safety.auth)을 직접 읽어 부른다. */
const ALERT_POLL_MS = 30 * 1000;
const ALERT_TONE = { HIGH: "stop", MEDIUM: "warn", LOW: "ok" };
let alertSeen = null; // 지금까지 본 미처리 이벤트 번호 (처음 불러올 때는 안내하지 않음)
let alertTimer = 0;

function authToken() {
  try { return JSON.parse(localStorage.getItem("safety.auth")).access_token; } catch (e) { return null; }
}
const escHtml = (t) => String(t ?? "").replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`);

/* ---------------------------------------------------------------- 프로필 사진 (회원 · 작업자)
   사진은 로그인한 사람만 열리는 주소(photo_url)라 <img> 에 토큰을 붙인다 (헤더를 못 붙이므로 ?token=).
   [data-photo] 를 누르면 크게 본다. 올리기 · 지우기는 mountPhotoField 로 만든 칸에서 한다. */
function photoSrc(url) {
  return url ? `${url}&token=${encodeURIComponent(authToken() || "")}` : "";
}

// 동그란 사진 (없으면 이름 첫 글자). 크기는 cls(.av 등)를 쓰는 화면이 정한다
function avatarHtml(person, cls = "av") {
  const name = person.name || "";
  if (!person.photo_url) return `<span class="${cls}">${escHtml(name[0] || "?")}</span>`;
  const src = escHtml(photoSrc(person.photo_url));
  return `<span class="${cls} has-photo" role="button" tabindex="0" data-photo="${src}" data-photo-name="${escHtml(name)}" title="${escHtml(name)} 사진 크게 보기"><img src="${src}" alt="${escHtml(name)}" loading="lazy" /></span>`;
}

function openPhoto(src, name) {
  let pop = document.getElementById("photo-pop");
  if (!pop) {
    document.body.insertAdjacentHTML("beforeend", `
      <div class="pop photo-pop" id="photo-pop" hidden>
        <div class="pop-card" role="dialog" aria-modal="true" aria-labelledby="photo-title">
          <div class="pop-head">
            <div><span class="role">프로필 사진</span><h2 id="photo-title"></h2></div>
            <button type="button" class="x-btn" data-close title="닫기" aria-label="닫기">✕</button>
          </div>
          <img id="photo-img" alt="" />
        </div>
      </div>`);
    pop = document.getElementById("photo-pop");
    pop.addEventListener("click", (e) => { if (e.target === pop || e.target.closest("[data-close]")) pop.hidden = true; });
    document.addEventListener("keydown", (e) => { if (e.key === "Escape") pop.hidden = true; });
  }
  document.getElementById("photo-title").textContent = name;
  const img = document.getElementById("photo-img");
  img.src = src;
  img.alt = name;
  pop.hidden = false;
}
document.addEventListener("click", (e) => {
  const el = e.target.closest("[data-photo]");
  if (el) openPhoto(el.dataset.photo, el.dataset.photoName);
});
document.addEventListener("keydown", (e) => {
  const el = e.target.closest && e.target.closest("[data-photo]");
  if (el && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); openPhoto(el.dataset.photo, el.dataset.photoName); }
});

async function sendPhoto(path, file) {
  const headers = { Authorization: "Bearer " + authToken() };
  if (file) headers["Content-Type"] = file.type || "application/octet-stream";
  const res = await fetch(path, { method: file ? "PUT" : "DELETE", headers, body: file || undefined });
  if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || "사진을 저장하지 못했습니다.");
  return file ? (await res.json()).photo_url : null;
}

/* 사진 칸: 큰 사진 + [사진 올리기] [사진 삭제]. path = "/api/users/3/photo" · "/api/workers/5/photo"
   고르면 바로 올리고 onChange(새 photo_url) 를 부른다. editable=false 면 보기만 */
function mountPhotoField(box, { path, person, editable = true, onChange }) {
  let url = person.photo_url || null;
  const paint = (note) => {
    box.innerHTML = avatarHtml({ name: person.name, photo_url: url }, "photo-big")
      + `<div class="photo-acts">${editable
        ? `<label class="btn sm">📷 ${url ? "사진 바꾸기" : "사진 올리기"}<input type="file" accept="image/jpeg,image/png,image/webp" hidden /></label>`
          + (url ? '<button type="button" class="btn sm del-text" data-photo-del>사진 삭제</button>' : "")
          + `<small class="muted">${escHtml(note || "JPG · PNG · WebP, 10MB 까지. 작게 줄여 저장하고 촬영 위치 정보는 지웁니다.")}</small>`
        : ""}</div>`;
  };
  const done = (next, msg) => {
    url = next;
    paint();
    toast(msg);
    if (onChange) onChange(url);
  };
  paint();
  box.onchange = async (e) => {
    const file = e.target.files && e.target.files[0];
    if (!file) return;
    paint("올리는 중…");
    try { done(await sendPhoto(path, file), "사진을 저장했습니다."); } catch (err) { paint(); toast(err.message); }
  };
  box.onclick = async (e) => {
    if (!e.target.closest("[data-photo-del]")) return;
    try { done(await sendPhoto(path, null), "사진을 지웠습니다."); } catch (err) { toast(err.message); }
  };
}

// 헤더 👤 자리에 내 사진
function paintMeIcon(url) {
  const ico = document.getElementById("me-ico");
  if (!ico) return;
  ico.classList.toggle("gnb-photo", Boolean(url));
  ico.innerHTML = url ? `<img src="${escHtml(photoSrc(url))}" alt="" />` : "👤";
}

// YOLO 탐지 영상: 서버가 탐지 박스 · ROI 를 그려 넣은 MJPEG. 관제화면(1-1) · 카메라 상세(1-2)만 쓰고,
// 나머지 화면은 원본 영상(/videos/...)을 튼다. 서버에 YOLO 가 없으면 enabled = false
let detectStatusOnce = null;
function detectStatus() {
  return (detectStatusOnce ||= alertFetch("/api/stream/status").catch(() => ({ enabled: false, reason: "탐지 영상 상태를 확인하지 못했습니다." })));
}
// <img> 는 헤더를 못 붙여서 로그인 토큰을 주소에 붙인다
const detectSrc = (cam, roi = true, boxes = true) =>
  `/api/stream/${cam.id}.mjpg?roi=${roi ? 1 : 0}&boxes=${boxes ? 1 : 0}&token=${encodeURIComponent(authToken() || "")}`;

// 관제화면에서 ROI · 탐지 박스를 그려 보일지 (이 브라우저에 기억). 꺼도 서버의 탐지 · 이벤트 판정 · 스냅샷은 그대로
const OVERLAY_KEY = "safety.detect-overlay";
function overlayShown() {
  try { return localStorage.getItem(OVERLAY_KEY) !== "0"; } catch (e) { return true; }
}
function rememberOverlay(on) {
  try { localStorage.setItem(OVERLAY_KEY, on ? "1" : "0"); } catch (e) { /* 기억 못 해도 지금 화면은 바뀜 */ }
}
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
  if (!res.ok) {
    const err = new Error((await res.json().catch(() => ({}))).detail || "알림을 불러오지 못했습니다.");
    err.status = res.status;
    throw err;
  }
  return res.status === 204 ? null : res.json();
}

// 이벤트를 지우면 알림 · 관제화면 목록을 30초 기다리지 않고 바로 고친다.
// 같은 브라우저의 다른 창에는 localStorage 로 알리고, 각 창은 "events-changed" 로 받는다
const EVENTS_CHANGED_KEY = "safety.eventsChanged";
function eventsChanged() {
  try { localStorage.setItem(EVENTS_CHANGED_KEY, String(Date.now())); } catch (e) { /* 다른 창은 다음 새로 고침 때 반영 */ }
  document.dispatchEvent(new Event("events-changed"));
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
          <button type="button" class="x-btn" id="alert-close" title="닫기" aria-label="닫기">✕</button>
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
    const hold = e.holding ? ' · <b class="hold-tag">작업 허가 대기 · 경보 지속</b>' : "";
    const ack = e.status === "NEW" && canHandle ? `<button type="button" class="mini-btn" data-ack="${e.id}">확인</button>` : "";
    const state = e.status === "NEW" ? '<span class="status stop">미처리</span>' : '<span class="status warn">확인중</span>';
    return `<div class="alert ${ALERT_TONE[e.severity]}${e.status === "ACK" && !e.holding ? " seen" : ""}${e.holding ? " holding" : ""}">
      <time>${e.detected_at.slice(11, 16)}</time>
      <div><b>${escHtml(e.detection_label)} · ${escHtml(e.camera_name || "카메라 없음")}</b><small>EV-${e.id} · ${escHtml(e.work_zone_name || "구역 없음")}${conf}${hold}</small></div>
      <div class="acts">${state}${ack}<a class="mini-btn primary" href="${canHandle ? "event-handle" : "event-detail"}.html?id=${e.id}">${canHandle ? "처리" : "상세"}</a></div>
    </div>`;
  }).join("") : '<p class="muted" style="padding:18px 4px">처리할 알림이 없습니다 👍</p>';

  // 작업 허가 대기 중인 이벤트가 있으면 허가될 때까지 🔔 이 계속 경보한다
  const holding = items.filter((e) => e.holding);
  badge.classList.toggle("hold", holding.length > 0);
  document.getElementById("gnb-alert").classList.toggle("holding", holding.length > 0);
  document.getElementById("gnb-alert").title = holding.length ? `작업 허가 대기 ${holding.length}건 · 허가될 때까지 경보` : "실시간 알림";

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

/* ---------------------------------------------------------------- 웹 푸시 (휴대폰 · PC 알림)
   헤더 회원정보 수정 팝업에서 이 기기 알림을 켜고 끈다. 켜면 서비스 워커(sw.js)가 브라우저 푸시 서비스에 구독하고,
   그 주소를 서버에 저장한다 → 이벤트가 생기면 서버가 보낸다 (backend/app/push.py). 화면을 닫아 둬도 온다.
   - HTTPS 주소(또는 이 PC 의 localhost)에서만 된다. 휴대폰은 서버를 HTTPS 로 열어야 한다 (README 「웹 푸시」)
   - 아이폰은 Safari 공유 → 「홈 화면에 추가」 한 앱에서만 된다 (iOS 16.4 이상) */
const pushSupported = () => window.isSecureContext && "serviceWorker" in navigator && "PushManager" in window && "Notification" in window;
const isIos = () => /iPhone|iPad|iPod/.test(navigator.userAgent) || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
let pushSub = null; // 이 기기의 구독 (켜져 있을 때)

function registerServiceWorker() {
  if (!window.isSecureContext || !("serviceWorker" in navigator)) return;
  navigator.serviceWorker.register("/sw.js").catch(() => { /* 알림만 못 씀 */ });
}

function base64UrlBytes(text) {
  const raw = atob((text + "=".repeat((4 - (text.length % 4)) % 4)).replace(/-/g, "+").replace(/_/g, "/"));
  return Uint8Array.from(raw, (c) => c.charCodeAt(0));
}

function showPush(on, note) {
  const toggle = document.getElementById("push-toggle");
  toggle.disabled = false;
  toggle.textContent = on ? "끄기" : "켜기";
  toggle.classList.toggle("primary", !on);
  document.getElementById("push-test").hidden = !on;
  document.getElementById("push-note").textContent = note || (on ? "이 기기로 알림이 옵니다." : "");
}

// 팝업을 열 때마다 이 기기가 켜져 있는지 다시 본다 (다른 계정으로 켰거나 브라우저에서 끈 경우)
async function loadPush() {
  const toggle = document.getElementById("push-toggle");
  if (!pushSupported()) {
    toggle.disabled = true;
    document.getElementById("push-note").textContent = !window.isSecureContext
      ? "HTTPS 주소에서만 켤 수 있습니다."
      : isIos() ? "아이폰은 공유 → 「홈 화면에 추가」 한 앱에서 켤 수 있습니다." : "이 브라우저는 알림을 지원하지 않습니다.";
    return;
  }
  if (Notification.permission === "denied") {
    toggle.disabled = true;
    document.getElementById("push-note").textContent = "브라우저에서 이 사이트 알림을 차단했습니다. 사이트 설정에서 허용으로 바꾸세요.";
    return;
  }
  try {
    const reg = await navigator.serviceWorker.ready;
    const sub = await reg.pushManager.getSubscription();
    const mine = sub ? await alertFetch("/api/push/subscriptions") : [];
    const saved = sub && mine.find((d) => d.endpoint === sub.endpoint);
    pushSub = saved ? sub : null;
    await paintPushZones(saved);
    if (saved) document.getElementById("push-sev").value = saved.min_severity;
    showPush(Boolean(saved));
  } catch (err) {
    showPush(false, err.message === "login" ? "로그인하면 켤 수 있습니다." : err.message);
  }
}

// 받을 구역: 「전체」 또는 작업구역 여러 개. 구역을 고르면 「높음은 구역과 상관없이 받기」(기본 켬)가 보인다
let pushZoneList = null;
async function paintPushZones(saved) {
  if (!pushZoneList) pushZoneList = await alertFetch("/api/work-zones").catch(() => []);
  const picked = new Set(saved ? saved.zone_ids : []);
  document.getElementById("push-zones").innerHTML = `<span class="chip${picked.size ? "" : " on"}" data-zone="">전체</span>`
    + pushZoneList.map((z) => `<span class="chip${picked.has(z.id) ? " on" : ""}" data-zone="${z.id}">${escHtml(z.name)}</span>`).join("");
  document.getElementById("push-high").checked = saved ? saved.high_any_zone : true;
  document.getElementById("push-high-row").hidden = !picked.size;
}

function pickedPushZones() {
  return [...document.querySelectorAll("#push-zones .chip.on[data-zone]")].map((c) => Number(c.dataset.zone)).filter(Boolean);
}

async function savePush(sub) {
  const body = {
    ...sub.toJSON(),
    min_severity: document.getElementById("push-sev").value,
    zone_ids: pickedPushZones(),
    high_any_zone: document.getElementById("push-high").checked,
  };
  await alertFetch("/api/push/subscriptions", { method: "PUT", body: JSON.stringify(body) });
}

async function turnPushOn() {
  // 알림 허용 창은 누른 직후에 띄워야 해서 다른 일보다 먼저 묻는다
  if (await Notification.requestPermission() !== "granted") throw new Error("브라우저에서 알림을 허용해야 받을 수 있습니다.");
  const key = await alertFetch("/api/push/key");
  if (!key.enabled) throw new Error(key.reason);
  const reg = await navigator.serviceWorker.ready;
  const options = { userVisibleOnly: true, applicationServerKey: base64UrlBytes(key.public_key) };
  let sub;
  try {
    sub = await reg.pushManager.subscribe(options);
  } catch (err) {
    // 서버 서명 키가 바뀌었으면 예전 구독을 지우고 다시 구독한다
    const old = await reg.pushManager.getSubscription();
    if (!old) throw err;
    await old.unsubscribe();
    sub = await reg.pushManager.subscribe(options);
  }
  await savePush(sub);
  pushSub = sub;
}

async function turnPushOff() {
  const sub = pushSub;
  pushSub = null;
  if (!sub) return;
  await alertFetch("/api/push/subscriptions?endpoint=" + encodeURIComponent(sub.endpoint), { method: "DELETE" });
  await sub.unsubscribe().catch(() => {});
}

function wirePush() {
  registerServiceWorker();
  const toggle = document.getElementById("push-toggle");
  toggle.addEventListener("click", async () => {
    toggle.disabled = true;
    try {
      if (pushSub) {
        await turnPushOff();
        showPush(false, "이 기기 알림을 껐습니다.");
      } else {
        await turnPushOn();
        showPush(true);
        toast("📱 이 기기로 알림을 받습니다. 테스트를 눌러 확인해 보세요.");
      }
    } catch (err) {
      showPush(Boolean(pushSub), err.message === "login" ? "로그인이 필요합니다." : err.message);
    }
  });
  document.getElementById("push-sev").addEventListener("change", async () => {
    if (!pushSub) return;
    try {
      await savePush(pushSub);
      toast("받을 심각도를 바꿨습니다.");
    } catch (err) {
      toast(err.message);
    }
  });
  const saveZones = async (what) => {
    if (!pushSub) return; // 켜기 전이면 켤 때 같이 저장한다
    try {
      await savePush(pushSub);
      toast(what);
    } catch (err) {
      toast(err.message);
    }
  };
  document.getElementById("push-zones").addEventListener("click", (e) => {
    const chip = e.target.closest(".chip");
    if (!chip) return;
    const all = document.querySelector('#push-zones .chip[data-zone=""]');
    if (chip === all) {
      document.querySelectorAll("#push-zones .chip").forEach((c) => c.classList.toggle("on", c === all));
    } else {
      chip.classList.toggle("on");
      all.classList.toggle("on", !pickedPushZones().length);
    }
    document.getElementById("push-high-row").hidden = !pickedPushZones().length;
    saveZones("받을 구역을 바꿨습니다.");
  });
  document.getElementById("push-high").addEventListener("change", () => saveZones("높음 알림 설정을 바꿨습니다."));
  document.getElementById("push-test").addEventListener("click", async (e) => {
    e.target.disabled = true;
    try {
      const res = await alertFetch("/api/push/test", { method: "POST" });
      toast(`테스트 알림을 보냈습니다 (기기 ${res.devices}대). 몇 초 안에 와야 합니다.`);
    } catch (err) {
      toast(err.message);
    } finally {
      e.target.disabled = false;
    }
  });
}

// 관제 화면 TC / 작업구역 패널을 누르면 1~4호기 후크가 움직이기 시작한다.
// 그 시각은 이 브라우저에 남아, 다른 화면을 보고 있어도 약 5초 뒤 겹칠 때 같은 경고창과 이벤트가 생긴다.
// 위치 계산은 monitor.html 의 craneGeometry 와 같다.
// 마스트 좌표는 그대로 둔다. 지브는 한 바퀴씩 돌고 후크는 반경을 오가며, 겹침은 처음 1분 안에 한 번, 이후 10분마다 한 번이다.
const TC_HOOKS = [
  { id: "1호기", kind: "T", x: -8, y: -8, jib: 55, speed: 0.08, phase: 300, trolleyPhase: 0 },
  { id: "2호기", kind: "L", x: 42, y: 52, jib: 50, speed: -0.05, minLuff: 15, maxLuff: 80 },
  { id: "3호기", kind: "T", x: 80, y: -8, jib: 55, speed: -0.08, phase: 240, trolleyPhase: 0.9 },
  { id: "4호기", kind: "L", x: 14, y: 90, jib: 46, speed: 0.042, minLuff: 15, maxLuff: 80 },
];
const TC_HOOK_HIT = 14;
const TC_HOOK_CLEAR = 18;
const TC_HOOK_AHEAD = 200; // 한 프레임 25ms × 200 = 5초 뒤. 이 시점에 겹침 경고
const TC_HOOK_INSPECT = 400; // 10초 뒤면 패널은 현장점검
const TC_WATCH_KEY = "safety.tcWatch";
const TC_HOLD_KEY = "safety.tcHookHolds"; // 겹침 경고가 만든 이벤트. 작업 허가 전까지 해당 호기는 작업중지
const TC_LAG_KEY = "safety.tcHookLag"; // 멈춘 동안 밀린 프레임. 허가가 나면 그 자리에서 다시 움직인다
const TC_INSPECT_KEY = "safety.tcInspect"; // 현장점검으로 올라간 호기. 작업 허가 전까지 유지
let tcHookSeen = null;

function readTcWatch() {
  try { return JSON.parse(localStorage.getItem(TC_WATCH_KEY)) || null; } catch (e) { return null; }
}
function writeTcWatch(state) {
  try { localStorage.setItem(TC_WATCH_KEY, JSON.stringify(state)); } catch (e) { /* 저장을 못 해도 이 화면에서는 동작 */ }
}
function startTcWatch() {
  const prev = readTcWatch();
  if (prev && prev.on) return;
  writeTcWatch({ on: 1, t0: Date.now(), latched: false, seq: 0 });
}
function syncTcServerBoot() {
  fetch("/api/health").then((res) => res.ok ? res.json() : null).then((body) => {
    const boot = body && Number(body.started_at);
    if (!boot) return;
    const prev = readTcWatch();
    if (prev && prev.boot === boot && prev.on) return;
    writeTcWatch({ on: 1, t0: boot, boot: boot, latched: false, seq: 0 });
    writeHookHolds([]);
    writeTcLag({});
    writeTcInspect([]);
  }).catch(() => { /* 서버 시각을 못 받아도 이 화면의 시계로 겹침은 진행된다 */ });
}
function tcFrameNow() {
  const watch = readTcWatch();
  if (!watch || !watch.on) return null;
  return Math.max(0, Math.floor((Date.now() - watch.t0) / 25));
}
function tcTurn(n, m) { return ((n % m) + m) % m; }
function tcMaxReach(spec) {
  if (spec.kind === "L") return spec.jib * Math.cos((spec.minLuff == null ? 15 : spec.minLuff) * Math.PI / 180);
  return spec.jib * 0.92;
}
function tcMinReach(spec) {
  if (spec.kind === "L") return spec.jib * Math.cos((spec.maxLuff == null ? 80 : spec.maxLuff) * Math.PI / 180);
  return spec.jib * 0.38;
}
// 러핑(2·4호기): 지브를 세우면 반경이 줄고, 눕히면 반경이 넓어진다
function tcLuffRadius(spec, frame) {
  const minL = spec.minLuff == null ? 15 : spec.minLuff;
  const maxL = spec.maxLuff == null ? 80 : spec.maxLuff;
  const range = maxL - minL;
  const luff = minL + range / 2 + (range / 2) * Math.sin(frame * 0.006);
  return spec.jib * Math.cos(luff * Math.PI / 180);
}
function tcMeetPlan(peers) {
  let best = null;
  for (let i = 0; i < peers.length; i++) {
    for (let j = i + 1; j < peers.length; j++) {
      const d = Math.hypot(peers[i].x - peers[j].x, peers[i].y - peers[j].y);
      const can = tcMaxReach(peers[i]) + tcMaxReach(peers[j]) >= d - 14;
      if (!best || (can && !best.can) || (can === best.can && d < best.d)) best = { i, j, d, can };
    }
  }
  return best;
}
function tcMeetRadii(a, b, dist) {
  const maxA = tcMaxReach(a), maxB = tcMaxReach(b);
  const minA = tcMinReach(a), minB = tcMinReach(b);
  const need = Math.max(0, dist - 12);
  let rA = Math.min(maxA, Math.max(minA, need * maxA / (maxA + maxB)));
  let rB = Math.min(maxB, Math.max(minB, need - rA));
  if (rA + rB < need) {
    rA = Math.min(maxA, Math.max(rA, need - rB));
    rB = Math.min(maxB, Math.max(rB, need - rA));
  }
  return [rA, rB];
}
function tcSmooth(t) {
  const x = Math.min(1, Math.max(0, t));
  return x * x * (3 - 2 * x);
}
const TC_LOGIN_WAIT = 1200; // 25ms × 1200 = 로그인 후 30초
const TC_MEET_INN = 320;
const TC_MEET_HOLD = 48;
const TC_MEET_OUT = 320;
const TC_MEET_GAP = 24000; // 25ms × 24000 = 10분
const TC_LOGIN_KEY = "safety.tcLoginAt";
function tcClockFrame(frame) {
  const live = tcFrameNow();
  return live == null ? frame : live;
}
function ensureFirstMeet() {
  const watch = readTcWatch();
  if (!watch || !watch.on || watch.firstMeet != null || watch.nextMeet != null) return;
  const now = tcFrameNow();
  if (now == null || !watch.t0) return;
  let loginAt = 0;
  try { loginAt = Number(localStorage.getItem(TC_LOGIN_KEY)) || 0; } catch (e) { /* 로그인 시각이 없으면 지금부터 센다 */ }
  let contact = loginAt ? Math.floor((loginAt + TC_LOGIN_WAIT * 25 - watch.t0) / 25) : now + TC_LOGIN_WAIT;
  if (contact <= now) contact = now + TC_LOGIN_WAIT;
  watch.firstMeet = contact;
  writeTcWatch(watch);
}
function tcContactFrame(clock) {
  const watch = readTcWatch() || {};
  const after = TC_MEET_HOLD + TC_MEET_OUT;
  if (watch.nextMeet != null) {
    if (clock != null && clock >= watch.nextMeet + after) return null;
    return watch.nextMeet;
  }
  if (watch.firstMeet == null) return null;
  if (clock != null && clock >= watch.firstMeet + after) return null;
  return watch.firstMeet;
}
function tcMeetWindow(frame) {
  const clock = tcClockFrame(frame);
  const contact = tcContactFrame(clock);
  if (contact == null) return null;
  const begin = contact - TC_MEET_INN;
  const span = TC_MEET_INN + TC_MEET_HOLD + TC_MEET_OUT;
  if (clock < begin || clock >= begin + span) return null;
  const u = clock - begin;
  const leaving = u >= TC_MEET_INN + TC_MEET_HOLD;
  const blend = u < TC_MEET_INN
    ? tcSmooth(u / TC_MEET_INN)
    : leaving
      ? tcSmooth(1 - (u - TC_MEET_INN - TC_MEET_HOLD) / TC_MEET_OUT)
      : 1;
  return { begin: begin, end: begin + span, blend: blend, leaving: leaving };
}
function tcFramesUntilMeet(frame) {
  const clock = tcClockFrame(frame);
  const at = tcContactFrame(clock);
  if (at == null || clock >= at) return null;
  return at - clock;
}
function tcAngleOff(from, to) {
  return Math.abs(tcTurn(to - from + 180, 360) - 180);
}
// 작동중지는 두 지브가 서로를 향해 후크가 맞닿을 때만. 간격만 좁아진 상태는 경고로 남긴다.
function tcPosesMeet(a, b, pa, pb) {
  if (!a || !b || !pa || !pb) return false;
  const mast = Math.hypot(a.x - b.x, a.y - b.y);
  if (pa.radius + pb.radius < mast) return false;
  const faceA = tcTurn(Math.atan2(b.y - a.y, b.x - a.x) * 180 / Math.PI, 360);
  const faceB = tcTurn(Math.atan2(a.y - b.y, a.x - b.x) * 180 / Math.PI, 360);
  if (tcAngleOff(pa.angle, faceA) > 20 || tcAngleOff(pb.angle, faceB) > 20) return false;
  const ax = a.x + pa.radius * Math.cos(pa.angle * Math.PI / 180);
  const ay = a.y + pa.radius * Math.sin(pa.angle * Math.PI / 180);
  const bx = b.x + pb.radius * Math.cos(pb.angle * Math.PI / 180);
  const by = b.y + pb.radius * Math.sin(pb.angle * Math.PI / 180);
  return Math.hypot(ax - bx, ay - by) <= TC_HOOK_HIT;
}
function tcHooksMeet(peers, i, j, frame) {
  const a = peers[i], b = peers[j];
  if (!a || !b) return false;
  return tcPosesMeet(a, b, tcHookPose(a, peers, tcShownFrame(a, frame)), tcHookPose(b, peers, tcShownFrame(b, frame)));
}
function dropMissedHolds() {
  const holds = readHookHolds();
  const left = holds.filter((hold) => {
    const names = hold.names || [];
    const pa = hold.poses && hold.poses[names[0]];
    const pb = hold.poses && hold.poses[names[1]];
    if (!pa || !pb) return true;
    const a = TC_HOOKS.find((spec) => spec.id === names[0]);
    const b = TC_HOOKS.find((spec) => spec.id === names[1]);
    return tcPosesMeet(a, b, pa, pb);
  });
  if (left.length !== holds.length) writeHookHolds(left);
}
function tcMeetSoonIndexes() {
  const frame = tcFrameNow();
  if (frame == null) return [];
  const left = tcFramesUntilMeet(frame);
  if (left == null || left <= 0 || left > TC_HOOK_AHEAD) return [];
  const plan = tcMeetPlan(TC_HOOKS);
  return plan ? [plan.i, plan.j] : [];
}
function tcCruiseAngle(spec, frame, idx) {
  const period = 1800; // 45초에 한 바퀴
  const dir = spec.speed != null && spec.speed < 0 ? -1 : 1;
  const phase = spec.phase == null ? idx * 90 : spec.phase;
  return tcTurn(phase + dir * (frame / period) * 360, 360);
}
function tcCruiseCap(spec, peers) {
  let cap = tcMaxReach(spec);
  peers.forEach((other) => {
    if (other === spec) return;
    const dist = Math.hypot(spec.x - other.x, spec.y - other.y);
    const share = tcMaxReach(spec) / (tcMaxReach(spec) + tcMaxReach(other));
    cap = Math.min(cap, Math.max(tcMinReach(spec), (dist - 22) * share));
  });
  return cap;
}
function tcCruiseRadius(spec, peers, frame, idx) {
  const minR = tcMinReach(spec);
  const cap = Math.max(minR, tcCruiseCap(spec, peers));
  const t = spec.kind === "L"
    ? (tcMaxReach(spec) <= minR ? 0 : (tcLuffRadius(spec, frame) - minR) / (tcMaxReach(spec) - minR))
    : 0.5 + 0.5 * Math.sin(frame * 0.007 + idx * 1.7);
  return minR + (cap - minR) * Math.min(1, Math.max(0, t));
}
function tcMeetBlend(frame) {
  const win = tcMeetWindow(frame);
  return win ? win.blend : 0;
}
function tcLerpAngle(from, to, t) {
  return tcTurn(from + (tcTurn(to - from + 180, 360) - 180) * t, 360);
}
// 마스트는 움직이지 않는다. 평소에는 한 바퀴를 돌고 후크만 오간다. 겹침 구간에만 가장 가까운 두 대가 마주 본다.
function tcHookPose(spec, peers, frame) {
  const frozen = tcHeldPose(spec.id);
  if (frozen) return { angle: frozen.angle, radius: frozen.radius };
  const idx = Math.max(0, peers.indexOf(spec));
  const cruise = tcCruiseAngle(spec, frame, idx);
  const radiusAt = (at) => tcCruiseRadius(spec, peers, at, idx);
  let angle = cruise, radius = radiusAt(frame);
  const resume = (readTcLag().resume || {})[spec.id];
  const live = tcClockFrame(frame);
  if (resume && resume.at != null && live != null) {
    const u = (live - resume.at) / TC_MEET_OUT;
    if (u >= 0 && u < 1) {
      const t = tcSmooth(u);
      angle = tcLerpAngle(resume.angle, angle, t);
      radius = resume.radius + (radius - resume.radius) * t;
    }
  }
  const plan = tcMeetPlan(peers);
  const win = tcMeetWindow(frame);
  if (plan && win && (spec === peers[plan.i] || spec === peers[plan.j])) {
    const other = spec === peers[plan.i] ? peers[plan.j] : peers[plan.i];
    const face = tcTurn(Math.atan2(other.y - spec.y, other.x - spec.x) * 180 / Math.PI, 360);
    const dist = Math.hypot(other.x - spec.x, other.y - spec.y);
    const radii = tcMeetRadii(peers[plan.i], peers[plan.j], dist);
    const want = spec === peers[plan.i] ? radii[0] : radii[1];
    const fromLive = win.leaving ? win.end : win.begin;
    const fromShown = tcShownFrame(spec, fromLive);
    angle = tcLerpAngle(tcCruiseAngle(spec, fromShown, idx), face, win.blend);
    const fromRadius = radiusAt(fromShown);
    radius = fromRadius + (want - fromRadius) * win.blend;
  }
  return { angle, radius };
}
function tcHookPoint(spec, frame) {
  const pose = tcHookPose(spec, TC_HOOKS, tcShownFrame(spec, frame));
  const rad = pose.angle * Math.PI / 180;
  return [spec.x + pose.radius * Math.cos(rad), spec.y + pose.radius * Math.sin(rad)];
}
function readHookHolds() {
  try {
    const list = JSON.parse(localStorage.getItem(TC_HOLD_KEY));
    return Array.isArray(list) ? list : [];
  } catch (e) { return []; }
}
function writeHookHolds(list) {
  try { localStorage.setItem(TC_HOLD_KEY, JSON.stringify(list)); } catch (e) { /* 저장을 못 해도 이 화면에서는 동작 */ }
}
function readTcLag() {
  try {
    const map = JSON.parse(localStorage.getItem(TC_LAG_KEY));
    return map && typeof map === "object" ? map : {};
  } catch (e) { return {}; }
}
function writeTcLag(map) {
  try { localStorage.setItem(TC_LAG_KEY, JSON.stringify(map)); } catch (e) { /* 저장을 못 해도 이 화면에서는 동작 */ }
}
function tcHeldPin(id) {
  let pin = null;
  readHookHolds().forEach((hold) => {
    if (!hold.pins || hold.pins[id] == null || !(hold.names || []).includes(id)) return;
    pin = hold.pins[id];
  });
  return pin;
}
function tcHeldPose(id) {
  let pose = null;
  readHookHolds().forEach((hold) => {
    const saved = hold.poses && hold.poses[id];
    if (!saved || saved.angle == null || !(hold.names || []).includes(id)) return;
    pose = saved;
  });
  return pose;
}
function tcShownFrame(spec, frame) {
  const pin = tcHeldPin(spec.id);
  if (pin != null) return pin;
  const lag = Number(readTcLag()[spec.id]) || 0;
  return Math.max(0, frame - lag);
}
function tcStampPins(hold, frame) {
  hold.pins = hold.pins || {};
  let changed = false;
  (hold.names || []).forEach((name) => {
    if (hold.pins[name] != null) return;
    const spec = TC_HOOKS.find((item) => item.id === name);
    if (!spec) return;
    hold.pins[name] = tcShownFrame(spec, frame);
    changed = true;
  });
  if (hold.pinAt == null) { hold.pinAt = frame; changed = true; }
  return changed;
}
function tcHoldOverlap(frame) {
  if (frame == null) return;
  dropMissedHolds();
  const poses = {};
  const pts = TC_HOOKS.map((spec) => {
    const pose = tcHookPose(spec, TC_HOOKS, tcShownFrame(spec, frame));
    poses[spec.id] = { angle: pose.angle, radius: pose.radius };
    const rad = pose.angle * Math.PI / 180;
    return [spec.x + pose.radius * Math.cos(rad), spec.y + pose.radius * Math.sin(rad)];
  });
  let best = { d: Infinity, a: 0, b: 1 };
  for (let i = 0; i < pts.length; i++) {
    for (let j = i + 1; j < pts.length; j++) {
      const d = Math.hypot(pts[i][0] - pts[j][0], pts[i][1] - pts[j][1]);
      if (d < best.d) best = { d, a: i, b: j };
    }
  }
  if (best.d > TC_HOOK_HIT || !tcHooksMeet(TC_HOOKS, best.a, best.b, frame)) return;
  const names = [TC_HOOKS[best.a].id, TC_HOOKS[best.b].id];
  const holds = readHookHolds();
  const hit = holds.filter((hold) => (hold.names || []).some((name) => names.includes(name)));
  if (!hit.length) {
    const state = readTcWatch() || { on: 1, t0: Date.now(), latched: false, seq: 0 };
    if (state.latched) return;
    state.latched = true;
    state.seq = (state.seq || 0) + 1;
    state.names = names;
    const hold = { seq: state.seq, names: names, id: null, pins: {}, poses: {}, pinAt: frame };
    names.forEach((name) => {
      const spec = TC_HOOKS.find((item) => item.id === name);
      if (!spec) return;
      hold.pins[name] = tcShownFrame(spec, frame);
      if (poses[name]) hold.poses[name] = poses[name];
    });
    holds.push(hold);
    writeTcWatch(state);
    writeHookHolds(holds);
    return;
  }
  let changed = false;
  hit.forEach((hold) => { if (tcStampPins(hold, frame)) changed = true; });
  if (changed) writeHookHolds(holds);
}
function tcHookDistance(frame, i, j) {
  const a = tcHookPoint(TC_HOOKS[i], frame);
  const b = tcHookPoint(TC_HOOKS[j], frame);
  return Math.hypot(a[0] - b[0], a[1] - b[1]);
}
function tcFirstHit(frame, i, j) {
  if (tcHookDistance(frame, i, j) <= TC_HOOK_HIT) return 0;
  for (let k = 25; k <= TC_HOOK_INSPECT; k += 25) {
    if (tcHookDistance(frame + k, i, j) <= TC_HOOK_HIT) return k;
  }
  return null;
}
function readTcInspect() {
  try {
    const list = JSON.parse(localStorage.getItem(TC_INSPECT_KEY));
    return Array.isArray(list) ? list : [];
  } catch (e) { return []; }
}
function writeTcInspect(list) {
  try { localStorage.setItem(TC_INSPECT_KEY, JSON.stringify(list)); } catch (e) { /* 저장을 못 해도 이 화면에서는 동작 */ }
}
function latchTcInspect(names) {
  const cur = new Set(readTcInspect());
  names.forEach((name) => cur.add(name));
  const next = [...cur];
  if (next.length !== readTcInspect().length) writeTcInspect(next);
}
// 이 호기만 작업 허가로 푼다. 같이 걸린 다른 호기는 그대로 둔다
function releaseTcCrane(name) {
  writeTcInspect(readTcInspect().filter((n) => n !== name));
  const holds = readHookHolds();
  let pinAt = null;
  let pose = null;
  holds.forEach((hold) => {
    if (!(hold.names || []).includes(name)) return;
    if (hold.pinAt != null) pinAt = hold.pinAt;
    if (hold.poses && hold.poses[name]) pose = hold.poses[name];
  });
  const rest = [];
  holds.forEach((hold) => {
    const names = (hold.names || []).filter((n) => n !== name);
    if (names.length) rest.push(Object.assign({}, hold, { names: names }));
  });
  writeHookHolds(rest);
  const live = tcFrameNow();
  if (live != null && (pinAt != null || pose)) {
    const lags = readTcLag();
    if (pinAt != null) lags[name] = (Number(lags[name]) || 0) + Math.max(0, live - pinAt);
    if (pose) {
      lags.resume = lags.resume || {};
      lags.resume[name] = { at: live, angle: pose.angle, radius: pose.radius };
    }
    writeTcLag(lags);
  }
  if (!rest.length && live != null) {
    const watch = readTcWatch() || { on: 1, t0: Date.now(), latched: false, seq: 0 };
    watch.nextMeet = live + TC_MEET_GAP;
    watch.latched = false;
    writeTcWatch(watch);
  }
  return rest;
}
function tcCardLevel() {
  const stopped = new Set();
  readHookHolds().forEach((hold) => (hold.names || []).forEach((name) => {
    const i = TC_HOOKS.findIndex((spec) => spec.id === name);
    if (i >= 0) stopped.add(i);
  }));
  const inspect = new Set();
  readTcInspect().forEach((name) => {
    const i = TC_HOOKS.findIndex((spec) => spec.id === name);
    if (i >= 0 && !stopped.has(i)) inspect.add(i);
  });
  const frame = tcFrameNow();
  const fresh = [];
  if (frame != null) {
    for (let i = 0; i < TC_HOOKS.length; i++) {
      for (let j = i + 1; j < TC_HOOKS.length; j++) {
        const hit = tcFirstHit(frame, i, j);
        if (hit == null || hit <= TC_HOOK_AHEAD) continue;
        [i, j].forEach((k) => {
          if (stopped.has(k)) return;
          inspect.add(k);
          fresh.push(TC_HOOKS[k].id);
        });
      }
    }
  }
  if (fresh.length) latchTcInspect(fresh);
  return TC_HOOKS.map((_, i) => (stopped.has(i) ? "stop" : inspect.has(i) ? "warn" : "ok"));
}
function tcHoldFor(index) {
  const name = TC_HOOKS[index] && TC_HOOKS[index].id;
  if (!name) return null;
  const holds = readHookHolds().filter((hold) => (hold.names || []).includes(name));
  return holds.length ? holds[holds.length - 1] : null;
}
async function refreshHookHolds() {
  const holds = readHookHolds();
  const pending = holds.filter((hold) => !hold.id);
  const named = holds.filter((hold) => hold.id);
  if (!named.length || !authToken()) return;
  const left = [];
  for (const hold of named) {
    try {
      const ev = await alertFetch("/api/events/" + hold.id);
      if (ev.status !== "DONE") left.push(hold);
    } catch (e) {
      if (e.status !== 404) left.push(hold); // 지워진 이벤트의 작업중지는 푼다
    }
  }
  if (left.length !== named.length) writeHookHolds(pending.concat(left));
}
function tcHookGap(frame) {
  const pts = TC_HOOKS.map((spec) => tcHookPoint(spec, frame));
  let best = { d: Infinity, a: 0, b: 1 };
  for (let i = 0; i < pts.length; i++) {
    for (let j = i + 1; j < pts.length; j++) {
      const d = Math.hypot(pts[i][0] - pts[j][0], pts[i][1] - pts[j][1]);
      if (d < best.d) best = { d, a: i, b: j };
    }
  }
  return best;
}
function hookWarnHtml() {
  return `
    <div class="pop" id="hook-warn" hidden>
      <div class="pop-card" role="alertdialog" aria-modal="true" aria-labelledby="hook-warn-title">
        <div class="pop-head">
          <div>
            <span class="status stop">다가옴</span>
            <h2 id="hook-warn-title">후크 겹침 예정</h2>
            <p id="hook-warn-text">타워크레인 후크가 약 5초 뒤 겹칩니다. 인양을 멈추세요.</p>
          </div>
        </div>
        <div class="row end" style="margin-top:16px">
          <a class="btn" id="hook-warn-event" href="events.html">이벤트 보기</a>
          <button type="button" class="btn primary" id="hook-warn-close">확인</button>
        </div>
      </div>
    </div>`;
}
function showHookWarn(eventId) {
  const pop = document.getElementById("hook-warn");
  if (!pop) return;
  const names = (readTcWatch() || {}).names;
  if (names && names.length === 2) {
    document.getElementById("hook-warn-title").textContent = names[0] + " · " + names[1] + " 후크 겹침 예정";
    document.getElementById("hook-warn-text").textContent = names[0] + " 후크와 " + names[1] + " 후크가 약 5초 뒤 겹칩니다. 인양을 멈추세요.";
  }
  const link = document.getElementById("hook-warn-event");
  link.href = eventId ? `event-detail.html?id=${eventId}` : "events.html";
  link.textContent = eventId ? `EV-${eventId} 보기` : "이벤트 보기";
  pop.hidden = false;
  document.getElementById("hook-warn-close").focus();
}
async function postHookEvent() {
  const token = authToken();
  if (!token) return null;
  try {
    const res = await fetch("/api/events/tc-hook", {
      method: "POST",
      headers: { Authorization: "Bearer " + token, "Content-Type": "application/json" },
    });
    if (!res.ok) return null;
    const body = await res.json();
    if (body.created) loadAlerts();
    return body.created ? body.event_id : null;
  } catch (e) { return null; }
}
function stepTcHooks() {
  const frame = tcFrameNow();
  if (frame == null) return;
  ensureFirstMeet();
  tcHoldOverlap(frame);
  const now = tcHookGap(frame);
  const ahead = tcHookGap(frame + TC_HOOK_AHEAD);
  const state = readTcWatch() || { on: 1, t0: Date.now(), latched: false, seq: 0 };
  if (now.d > TC_HOOK_CLEAR && ahead.d > TC_HOOK_HIT && state.latched) {
    state.latched = false;
    writeTcWatch(state);
    // 작업중지는 후크가 떨어져도 유지한다. 작업 허가가 나와야 풀린다
  }
  if (tcHookSeen == null) tcHookSeen = state.seq || 0;
  else if (state.latched && (state.seq || 0) > tcHookSeen) {
    tcHookSeen = state.seq;
    /* TEMP 작업 중: 다른 창의 후크 겹침 경고창을 띄우지 않는다
    showHookWarn(null);
    */
  }
}

// 순간풍속 15m/s. 한 프레임 25ms × 2400 = 1분마다, 그중 200~519프레임(약 8초)만 강풍.
// TC 패널을 누른 시각을 같이 써서, 다른 화면에서도 그 구간에 들어가면 경고창과 이벤트가 생긴다.
const WIND_CYCLE = 2400;
const WIND_GUST_FROM = 200;
const WIND_GUST_TO = 520;
const WIND_WATCH_KEY = "safety.windWatch";
let windSeen = null;

function readWindWatch() {
  try { return JSON.parse(localStorage.getItem(WIND_WATCH_KEY)) || null; } catch (e) { return null; }
}
function writeWindWatch(state) {
  try { localStorage.setItem(WIND_WATCH_KEY, JSON.stringify(state)); } catch (e) { /* 저장을 못 해도 이 화면에서는 동작 */ }
}
function windWarnHtml() {
  return `
    <div class="pop" id="wind-warn" hidden>
      <div class="pop-card" role="alertdialog" aria-modal="true" aria-labelledby="wind-warn-title">
        <div class="pop-head">
          <div>
            <span class="status info">강풍</span>
            <h2 id="wind-warn-title">순간풍속 15m/s</h2>
            <p id="wind-warn-text">순간풍속 15m/s. 인양을 멈추세요.</p>
          </div>
        </div>
        <div class="row end" style="margin-top:16px">
          <a class="btn" id="wind-warn-event" href="events.html">이벤트 보기</a>
          <button type="button" class="btn primary" id="wind-warn-close">확인</button>
        </div>
      </div>
    </div>`;
}
function showWindWarn(eventId) {
  const pop = document.getElementById("wind-warn");
  if (!pop) return;
  const link = document.getElementById("wind-warn-event");
  link.href = eventId ? `event-detail.html?id=${eventId}` : "events.html";
  link.textContent = eventId ? `EV-${eventId} 보기` : "이벤트 보기";
  pop.hidden = false;
  document.getElementById("wind-warn-close").focus();
}
async function postWindEvent() {
  const token = authToken();
  if (!token) return null;
  try {
    const res = await fetch("/api/events/wind-gust", {
      method: "POST",
      headers: { Authorization: "Bearer " + token, "Content-Type": "application/json" },
    });
    if (!res.ok) return null;
    const body = await res.json();
    if (body.created) loadAlerts();
    return body.created ? body.event_id : null;
  } catch (e) { return null; }
}
function windGustOn(frame) {
  const phase = frame % WIND_CYCLE;
  return phase >= WIND_GUST_FROM && phase < WIND_GUST_TO;
}
function stepWindGust() {
  const frame = tcFrameNow();
  if (frame == null) return;
  const gust = windGustOn(frame);
  const state = readWindWatch() || { latched: false, seq: 0 };
  if (gust && !state.latched) {
    state.latched = true;
    state.seq = (state.seq || 0) + 1;
    writeWindWatch(state);
    windSeen = state.seq;
    /* TEMP 작업 중: 순간풍속 경고창과 그 이벤트 알림을 띄우지 않는다
    showWindWarn(null);
    postWindEvent().then((id) => {
      const pop = document.getElementById("wind-warn");
      if (id && pop && !pop.hidden) showWindWarn(id);
    });
    */
    return;
  }
  if (!gust && state.latched) {
    state.latched = false;
    writeWindWatch(state);
  }
  if (windSeen == null) windSeen = state.seq || 0;
  else if (state.latched && (state.seq || 0) > windSeen) {
    windSeen = state.seq;
    /* TEMP 작업 중: 다른 창의 순간풍속 경고창을 띄우지 않는다
    showWindWarn(null);
    */
  }
}

function wireAlerts() {
  document.body.insertAdjacentHTML("beforeend", alertPopHtml() + hookWarnHtml() + windWarnHtml());
  document.getElementById("hook-warn").addEventListener("click", (e) => {
    if (e.target.id === "hook-warn" || e.target.closest("#hook-warn-close")) document.getElementById("hook-warn").hidden = true;
  });
  document.getElementById("wind-warn").addEventListener("click", (e) => {
    if (e.target.id === "wind-warn" || e.target.closest("#wind-warn-close")) document.getElementById("wind-warn").hidden = true;
  });
  wirePush();
  syncTcServerBoot();
  setInterval(() => { stepTcHooks(); stepWindGust(); }, 200);
  setInterval(() => { refreshHookHolds(); }, 3000);
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
  document.addEventListener("keydown", (e) => {
    if (e.key !== "Escape") return;
    const wind = document.getElementById("wind-warn");
    if (wind && !wind.hidden) { wind.hidden = true; return; }
    const hook = document.getElementById("hook-warn");
    if (hook && !hook.hidden) { hook.hidden = true; return; }
    closeAlerts();
  });
  document.addEventListener("events-changed", () => { loadAlerts(); refreshHookHolds(); });
  window.addEventListener("storage", (e) => {
    if (e.key === EVENTS_CHANGED_KEY) document.dispatchEvent(new Event("events-changed"));
  });
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

// 날짜 칸은 어디를 눌러도 달력이 뜬다 (숫자를 직접 고쳐 쓰는 것도 그대로 된다)
document.addEventListener("click", (e) => {
  const el = e.target.closest && e.target.closest('input[type="date"]');
  if (!el || el.disabled || el.readOnly || !el.showPicker) return;
  try { el.showPicker(); } catch { /* 이미 열려 있거나 브라우저가 막으면 그냥 둔다 */ }
});

// 목록 하단 페이지 번호. 5개씩 묶어 보여 주고, ◀ ▶ 로 앞뒤 묶음의 첫 페이지로 넘어간다
// 버튼마다 data-p 에 페이지 번호가 붙는다 (눌리지 않는 화살표에는 없음)
const PAGER_BLOCK = 5;
function renderPagers(box, page, total, size) {
  const pages = Math.max(1, Math.ceil(total / size));
  const first = Math.floor((page - 1) / PAGER_BLOCK) * PAGER_BLOCK + 1, last = Math.min(first + PAGER_BLOCK - 1, pages);
  const arrow = (label, p) => p ? `<span class="pager" data-p="${p}">${label}</span>` : `<span class="pager off">${label}</span>`;
  box.innerHTML = (pages > PAGER_BLOCK ? arrow("◀", first > 1 && first - PAGER_BLOCK) : "")
    + Array.from({ length: last - first + 1 }, (_, i) =>
      `<span class="pager${first + i === page ? " on" : ""}" data-p="${first + i}">${first + i}</span>`).join("")
    + (pages > PAGER_BLOCK ? arrow("▶", last < pages && last + 1) : "");
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
  const date = now.getFullYear() + "." + pad2(now.getMonth() + 1) + "." + pad2(now.getDate());
  const timeEl = document.getElementById("now-time");
  const dateEl = document.getElementById("now-date");
  if (timeEl) timeEl.textContent = time;
  if (dateEl) dateEl.textContent = date;
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
  document.querySelectorAll("[data-rail]").forEach(wireSideRail);
}

// 좌우 패널 화살표. 기본은 접힘. 이 화면에서 한 번 열어 두면 그 상태를 기억한다
function openSideRail(side) {
  const btn = document.querySelector(`[data-rail="${side}"]`);
  if (!btn) return;
  const hiddenClass = side === "left" ? "left-hidden" : "rail-hidden";
  if (btn.closest(".page").classList.contains(hiddenClass)) btn.click();
}
function wireSideRail(btn) {
  const side = btn.dataset.rail;
  const page = btn.closest(".page");
  const hiddenClass = side === "left" ? "left-hidden" : "rail-hidden";
  const key = `safety.rail.${currentFile()}.${side}`;
  const openMark = "▷";
  const shutMark = "◁";
  const label = "오른쪽 패널";
  function setHidden(hidden, remember) {
    page.classList.toggle(hiddenClass, hidden);
    btn.textContent = hidden ? shutMark : openMark;
    btn.title = hidden ? `${label} 열기` : `${label} 닫기`;
    btn.setAttribute("aria-expanded", hidden ? "false" : "true");
    if (remember) { try { localStorage.setItem(key, hidden ? "1" : "0"); } catch (e) { /* 무시 */ } }
    requestAnimationFrame(() => window.dispatchEvent(new Event("resize")));
    setTimeout(() => window.dispatchEvent(new Event("resize")), 280);
  }
  let hidden = true;
  try { hidden = localStorage.getItem(key) !== "0"; } catch (e) { /* 저장을 못 읽으면 접어 둔다 */ }
  setHidden(hidden, false);
  btn.addEventListener("click", () => setHidden(!page.classList.contains(hiddenClass), true));
}

(function init() {
  const file = currentFile();
  const found = findPage(file);
  // 역할이 모자란 화면은 주소로 열어도 관제화면으로 돌려보낸다 (서버도 저장 · 수정을 따로 막는다)
  const need = found && pageNeed(found.group, found.page);
  if (need && !can(need)) {
    alert(`${found.page[1]} 화면은 ${ROLE_KO[need]} 이상만 볼 수 있습니다.`);
    location.replace("monitor.html");
    return;
  }
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
