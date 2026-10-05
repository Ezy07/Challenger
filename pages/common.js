/* 모든 화면이 함께 쓰는 스크립트
   - 화면 목록(MENU)을 한 곳에 모아 두고, 상단 메뉴 · 제목 칸 · 하위 화면 탭을 여기서 그린다
   - 화면을 추가하려면 MENU 에 [파일 이름, 화면 이름, 설명] 한 줄만 넣으면 된다
   - 아직 데이터베이스가 없으므로 저장 · 삭제 버튼은 안내 문구(toast)만 띄운다 */

const MENU = [
  { no: "1", name: "실시간 관제", pages: [
    ["monitor.html", "멀티뷰", "CCTV 4대를 한 화면에서 보고, 탐지 결과와 경보를 실시간으로 확인"],
    ["monitor-camera.html", "단일 카메라 확대", "카메라 한 대를 크게 보면서 위험구역 · 탐지 박스 · 최근 이벤트 확인"],
    ["monitor-alerts.html", "실시간 알림 패널", "새로 생긴 이벤트가 위에서부터 쌓이는 알림 목록과 경고음 설정"],
  ] },
  { no: "2", name: "이벤트 로그", pages: [
    ["events.html", "이벤트 목록", "날짜 · 구역 · 종류 · 심각도로 지난 이벤트를 찾는 화면"],
    ["event-snapshot.html", "스냅샷 미리보기", "목록에서 고른 이벤트의 탐지 순간 이미지를 바로 확인"],
    ["event-export.html", "내보내기", "조건에 맞는 이벤트를 CSV · 엑셀 파일로 내려받기"],
  ] },
  { no: "3", name: "이벤트 상세", pages: [
    ["event-detail.html", "이벤트 상세", "이벤트 하나의 스냅샷 · 앞뒤 영상 · 탐지된 객체 정보"],
    ["timeline.html", "타임라인", "하루 동안 생긴 이벤트를 카메라별 시간 축 위에 표시"],
    ["event-handle.html", "처리 기록", "이벤트를 확인 완료 · 오탐 · 조치 필요로 처리하고 메모 남기기"],
  ] },
  { no: "4", name: "통계", pages: [
    ["stats.html", "요약", "오늘 · 이번 주 발생 건수와 종류별 비율"],
    ["stats-trend.html", "추이 차트", "일별 · 시간대별로 이벤트가 늘거나 줄었는지 확인"],
    ["stats-heatmap.html", "히트맵", "현장 도면 위에 이벤트가 몰리는 구역을 색으로 표시"],
    ["stats-report.html", "리포트", "기간을 골라 요약 보고서(PDF)를 만들기"],
  ] },
  { no: "5", name: "위험구역", pages: [
    ["roi-draw.html", "구역 그리기", "카메라 화면 위를 클릭해 위험구역 다각형을 그리기"],
    ["roi-list.html", "구역 목록", "만든 위험구역 전체를 보고 켜고 끄기"],
    ["roi-rules.html", "구역별 규칙", "구역마다 침범 · 체류 시간 · 장비 근접 · 대상 클래스 정하기"],
  ] },
  { no: "8", name: "장비 현황", pages: [
    ["equipment.html", "장비 목록", "현장에 있는 크레인 · 펌프카 · 믹서트럭 · 굴착기와 현재 상태"],
    ["equipment-detail.html", "장비 상세", "장비 한 대의 탐지 기록 · 가동 시간 · 관련 이벤트"],
  ] },
  { no: "6", name: "카메라 관리", settings: true, pages: [
    ["cameras.html", "카메라 목록", "등록된 카메라와 연결 상태(온라인 / 오프라인)"],
    ["camera-edit.html", "등록 · 수정", "RTSP 주소 · 이름 · 설치 위치를 입력해 카메라 등록"],
    ["camera-map.html", "배치도", "현장 도면 위에 카메라 위치와 보는 방향 표시"],
  ] },
  { no: "7", name: "알림 규칙", settings: true, pages: [
    ["alert-threshold.html", "판정 기준", "클래스별 confidence 기준과 같은 알림을 다시 울리기까지의 쿨다운"],
    ["alert-severity.html", "심각도 기준", "낮음 · 중간 · 높음을 나누는 조건과 각각의 알림 방법"],
    ["alert-targets.html", "알림 대상", "누가 어떤 수단(화면 · 문자 · 메신저)으로 알림을 받을지"],
  ] },
  { no: "9", name: "모델 / 라벨링", settings: true, pages: [
    ["model-labeling.html", "라벨링 도구", "SAM2 라벨링 도구(sam2_label.py)로 학습 데이터 만들기"],
    ["model-dataset.html", "데이터셋 현황", "클래스별 라벨 수와 영상별 저장 장수"],
    ["model-versions.html", "모델 버전", "학습한 모델의 성능(mAP)을 비교하고 현장에 적용할 모델 고르기"],
  ] },
  { no: "10", name: "사용자 / 권한", settings: true, pages: [
    ["login.html", "로그인", "아이디 · 비밀번호로 관제 시스템에 들어가기"],
    ["users.html", "사용자 목록", "사용자 추가 · 삭제와 역할(관리자 / 관제 요원) 지정"],
    ["user-activity.html", "활동 기록", "누가 언제 어떤 이벤트를 처리했는지"],
  ] },
];

const EXTRA = {
  "index.html": ["0", "페이지 지도", "전체 화면 목록. 이름을 누르면 그 화면으로 이동", "이 폴더 안내"],
  "settings.html": ["C-2", "설정 홈", "카메라 · 알림 규칙 · 모델 · 사용자 설정으로 들어가는 입구", "설정"],
};

const ALERT_COUNT = 2; // 미처리 이벤트 수 (예시)

function currentFile() {
  return decodeURIComponent(location.pathname.split("/").pop()) || "index.html";
}

function findPage(file) {
  for (const group of MENU) {
    const i = group.pages.findIndex((p) => p[0] === file);
    if (i >= 0) return { group, index: i, page: group.pages[i] };
  }
  return null;
}

function renderGnb(file, found) {
  const inSettings = file === "settings.html" || (found && found.group.settings);
  const links = MENU.filter((g) => !g.settings).map((g) => {
    const on = found && found.group === g ? " on" : "";
    return `<a class="${on}" href="${g.pages[0][0]}"><small>${g.no}</small>${g.name}</a>`;
  }).join("") + `<a class="${inSettings ? "on" : ""}" href="settings.html"><small>⚙</small>설정</a>`;
  document.body.insertAdjacentHTML("afterbegin", `
    <nav class="gnb">
      <a class="brand" href="monitor.html"><i>▲</i>안전관제</a>
      <div class="gnb-menu">${links}</div>
      <div class="gnb-side">
        <a class="gnb-btn" href="monitor-alerts.html" title="실시간 알림">🔔 알림 <span class="badge">${ALERT_COUNT}</span></a>
        <a class="gnb-btn" href="index.html" title="전체 화면 목록">🗺 페이지 지도</a>
        <a class="gnb-user" href="user-activity.html"><b>최동현 과장</b><br>관리자</a>
        <a class="gnb-btn" href="login.html">로그아웃</a>
      </div>
    </nav>`);
}

function tabsHtml(found) {
  if (!found) return "";
  return found.group.pages.map((p, i) =>
    `<a class="tab${i === found.index ? " on" : ""}" href="${p[0]}"><b>${found.group.no}-${i + 1}</b>${p[1]}</a>`
  ).join("");
}

function renderHead(file, found) {
  const head = document.querySelector("header.head");
  if (head && !head.children.length) {
    let no, groupName, title, text;
    if (found) {
      no = `${found.group.no}-${found.index + 1}`;
      groupName = found.group.name;
      [, title, text] = found.page;
    } else {
      const extra = EXTRA[file] || ["", document.title, "", ""];
      [no, title, text, groupName] = extra;
    }
    head.innerHTML = `
      <div class="where"><i class="dot"></i><b>${no}</b>${groupName}</div>
      <div class="title"><h1>${title}</h1><p>${text}</p></div>
      <div class="tabs">${tabsHtml(found)}</div>`;
  }
  // monitor.html 처럼 제목 칸을 직접 만든 화면은 탭 자리만 채운다
  document.querySelectorAll("[data-tabs]").forEach((el) => { el.innerHTML = tabsHtml(found); el.classList.add("tabs"); });
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
}

(function init() {
  const file = currentFile();
  const found = findPage(file);
  if (!document.body.hasAttribute("data-no-gnb")) renderGnb(file, found);
  renderHead(file, found);
  wireCommon();
  tickClock();
  setInterval(tickClock, 1000);
})();
