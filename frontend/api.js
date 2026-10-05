/* 백엔드 API 를 부르는 도우미
   - 로그인하면 받은 토큰과 사용자 정보를 localStorage(safety.auth)에 저장하고, 요청마다 붙인다
   - 토큰이 없거나 만료되어 401 이 오면 로그인 화면으로 보낸다 (다시 로그인하면 원래 화면으로 돌아옴)
   - common.js 보다 먼저 넣어야 상단 바에 로그인한 사람 이름이 보인다 */

const AUTH_KEY = "safety.auth";

function getAuth() {
  try { return JSON.parse(localStorage.getItem(AUTH_KEY)); } catch (e) { return null; }
}
function setAuth(auth) {
  try { localStorage.setItem(AUTH_KEY, JSON.stringify(auth)); } catch (e) { /* 저장 못 하면 화면마다 다시 로그인 */ }
}
function clearAuth() {
  try { localStorage.removeItem(AUTH_KEY); } catch (e) { /* 무시 */ }
}

let redirecting = false;

function goLogin() {
  redirecting = true;
  const here = location.pathname.split("/").pop() + location.search;
  location.href = "login.html?next=" + encodeURIComponent(here);
}

// 로그인이 필요한 화면 맨 위에서 부른다
function requireLogin() {
  if (!getAuth()) goLogin();
}

// FastAPI 오류 응답(detail)을 사람이 읽을 문장으로
function errorText(detail, status) {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail) && detail.length) return "입력값을 확인하세요: " + detail.map((d) => d.loc.slice(-1)[0]).join(", ");
  return `요청을 처리하지 못했습니다. (${status})`;
}

/* api("/api/events", { query: { status: ["NEW", "ACK"] } })
   api("/api/auth/login", { method: "POST", body: {...} }) */
async function api(path, { method = "GET", body, query } = {}) {
  if (redirecting) return new Promise(() => {}); // 로그인 화면으로 가는 중이면 요청하지 않고 기다리기만
  const url = new URL(path, location.origin);
  Object.entries(query || {}).forEach(([k, v]) => {
    if (v === undefined || v === null || v === "") return;
    (Array.isArray(v) ? v : [v]).forEach((one) => url.searchParams.append(k, one));
  });
  const headers = {};
  const auth = getAuth();
  if (auth) headers.Authorization = "Bearer " + auth.access_token;
  if (body !== undefined) headers["Content-Type"] = "application/json";

  const res = await fetch(url, { method, headers, body: body === undefined ? undefined : JSON.stringify(body) });
  if (res.status === 401 && auth) {
    clearAuth();
    goLogin();
    throw new Error("로그인이 만료되었습니다.");
  }
  const data = res.status === 204 ? null : await res.json().catch(() => null);
  if (!res.ok) throw new Error(errorText(data && data.detail, res.status));
  return data;
}

/* ---------------------------------------------------------------- 화면 표시 도우미 */

// 서버에서 온 글자를 HTML 에 넣을 때는 꼭 esc() 를 거친다
const esc = (t) => String(t ?? "").replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`);

// [색 class, 한글] — common.css 의 .status ok/warn/stop/info/mute 와 짝
const LABEL = {
  role: { ADMIN: ["", "관리자"], MANAGER: ["info", "안전관리자"], VIEWER: ["mute", "조회 전용"] },
  userStatus: { PENDING: ["warn", "대기"], ACTIVE: ["ok", "활성"], REJECTED: ["stop", "반려"], LOCKED: ["stop", "잠금"], DELETED: ["mute", "삭제"] },
  severity: { HIGH: ["stop", "높음"], MEDIUM: ["warn", "중간"], LOW: ["ok", "낮음"] },
  eventStatus: { NEW: ["stop", "미처리"], ACK: ["warn", "확인중"], DONE: ["ok", "처리완료"], FALSE: ["mute", "오탐"] },
  workStatus: { IN_PROGRESS: ["ok", "진행중"], STOPPED: ["stop", "작업중지"], PLANNED: ["mute", "예정"], DONE: ["info", "완료"] },
  equipStatus: { RUNNING: ["ok", "가동"], IDLE: ["mute", "대기"], MAINTENANCE: ["warn", "점검"], BROKEN: ["stop", "고장"] },
  equipType: { TC: ["", "타워크레인"], PUMP_CAR: ["", "펌프카"], MIXER_TRUCK: ["", "믹서트럭"], DUMP_TRUCK: ["", "덤프트럭"],
    EXCAVATOR: ["", "굴착기"], CRANE: ["", "이동식 크레인"], FORKLIFT: ["", "지게차"], ETC: ["", "기타"] },
  specialReason: { ELDERLY: ["", "고령"], HYPERTENSION: ["", "고혈압"], NEW: ["", "신규 투입"], ETC: ["", "기타"] },
};
const EQUIP_ICON = { TC: "🏗", PUMP_CAR: "🚒", MIXER_TRUCK: "🚛", DUMP_TRUCK: "🚚", EXCAVATOR: "🚜", CRANE: "🏗", FORKLIFT: "🛻", ETC: "⚙" };
const labelOf = (kind, value) => (LABEL[kind][value] || ["", value])[1];

// 오늘 날짜 "2026-10-04" (브라우저 시간대 기준)
const todayStr = () => new Date(Date.now() - new Date().getTimezoneOffset() * 60000).toISOString().slice(0, 10);
// "2026-10-04" → "10.04"
const md = (d) => (d ? d.slice(5).replace("-", ".") : "");
// 작업 기간 "09.22 ~ 10.15" (하루짜리는 "10.04")
const period = (w) => (w.end_date && w.end_date !== w.start_date ? `${md(w.start_date)} ~ ${md(w.end_date)}` : md(w.start_date));
// 특별관리 표시 (지금 유효한 사유가 있을 때만)
const spTags = (w) => (w.special_tags.length ? w.special_tags.map((t) => `<span class="sp">${esc(t)}</span>`).join(" ") : '<span class="muted">-</span>');
function badge(kind, value) {
  const [cls, text] = LABEL[kind][value] || ["mute", value];
  return kind === "role" && value === "ADMIN"
    ? `<span class="role">${text}</span>`
    : `<span class="status ${cls}">${text}</span>`;
}

// "2026-10-03T14:32:10.123" → "2026.10.03 14:32:10" (서버 시각을 그대로 보여 줌)
function fmtTime(iso, { date = true, time = true } = {}) {
  if (!iso) return "-";
  const [d, t = ""] = iso.split("T");
  return [date ? d.replaceAll("-", ".") : "", time ? t.slice(0, 8) : ""].filter(Boolean).join(" ");
}

// 카메라 stream_url 이 영상 파일(videos/...)이면 브라우저 주소 (/videos/...), 아니면 null
const videoSrc = (streamUrl) => (streamUrl && streamUrl.startsWith("videos/") ? "/" + encodeURI(streamUrl) : null);

// 조직 목록 → { id: "OO건설 · 공사팀 · 양중" } (회사부터 전체 경로)
function orgNames(orgs) {
  const byId = Object.fromEntries(orgs.map((o) => [o.id, o]));
  const path = (o) => (o.parent_id && byId[o.parent_id] ? `${path(byId[o.parent_id])} · ${o.name}` : o.name);
  return Object.fromEntries(orgs.map((o) => [o.id, path(o)]));
}

// /api/users/staff 결과 → 담당자 선택 칸
function staffOptions(staff, selected) {
  return '<option value="">담당자 없음</option>' + staff
    .map((u) => `<option value="${u.id}"${u.id === selected ? " selected" : ""}>${esc(u.name)} ${esc(u.position || "")}</option>`).join("");
}

/* 로그인이 필요한 파일 내려받기 (토큰을 붙여 받은 뒤 브라우저 저장 창으로) */
async function apiDownload(path, query) {
  const url = new URL(path, location.origin);
  Object.entries(query || {}).forEach(([k, v]) => {
    if (v === undefined || v === null || v === "") return;
    (Array.isArray(v) ? v : [v]).forEach((one) => url.searchParams.append(k, one));
  });
  const auth = getAuth();
  const res = await fetch(url, { headers: auth ? { Authorization: "Bearer " + auth.access_token } : {} });
  if (!res.ok) {
    const data = await res.json().catch(() => null);
    throw new Error(errorText(data && data.detail, res.status));
  }
  const name = (/filename="([^"]+)"/.exec(res.headers.get("Content-Disposition") || "") || [])[1] || "download";
  const link = Object.assign(document.createElement("a"), { href: URL.createObjectURL(await res.blob()), download: name });
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(link.href), 1000);
  return name;
}

/* 차트 툴팁: data-tip-value · data-tip-label 이 있는 표시(막대 · 점)에 마우스를 올리거나 키보드로 고르면 값을 보여 준다.
   값이 먼저(굵게), 이름이 뒤. 글자는 textContent 로만 넣는다 */
function attachTips(root) {
  let tip = document.querySelector(".viz-tip");
  if (!tip) {
    tip = document.createElement("div");
    tip.className = "viz-tip";
    tip.setAttribute("role", "tooltip");
    tip.innerHTML = "<b></b><span></span>";
    document.body.appendChild(tip);
  }
  const show = (el, x, y) => {
    tip.querySelector("b").textContent = el.dataset.tipValue;
    tip.querySelector("span").textContent = el.dataset.tipLabel;
    tip.hidden = false;
    const w = tip.offsetWidth, h = tip.offsetHeight;
    tip.style.left = Math.min(window.innerWidth - w - 8, Math.max(8, x - w / 2)) + "px";
    tip.style.top = Math.max(8, y - h - 12) + "px";
  };
  const hide = () => { tip.hidden = true; };
  hide();
  root.addEventListener("pointermove", (e) => {
    const el = e.target.closest("[data-tip-value]");
    if (el && root.contains(el)) show(el, e.clientX, e.clientY); else hide();
  });
  root.addEventListener("pointerleave", hide);
  root.addEventListener("focusin", (e) => {
    const el = e.target.closest("[data-tip-value]");
    if (!el) return;
    const r = el.getBoundingClientRect();
    show(el, r.left + r.width / 2, r.top);
  });
  root.addEventListener("focusout", hide);
}
