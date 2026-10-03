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
};
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

// 조직 목록 → { id: "OO건설 · 안전팀" }
function orgNames(orgs) {
  const byId = Object.fromEntries(orgs.map((o) => [o.id, o]));
  return Object.fromEntries(orgs.map((o) => [o.id, o.parent_id ? `${byId[o.parent_id].name} · ${o.name}` : o.name]));
}
