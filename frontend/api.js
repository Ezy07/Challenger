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

function goLogin() {
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
