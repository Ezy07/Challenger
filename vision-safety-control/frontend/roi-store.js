/* ROI 그리기 · ROI 목록이 같이 쓰는 감지 구역 데이터 (api.js 다음에 넣는다)
   - 서버: /api/roi-zones (storage/roi-zones.json). 한 줄 = 카메라 · 구역 번호 · 그 모양이 시작되는 프레임
   - 화면 안: 영상 파일별 구역 목록 books = { "파일.mp4": [{ uid, no, kind, enabled, schedule, keys: [{ frame, pts, time }] }] }
   - 카메라는 DB(/api/cameras) 기준. 카메라의 stream_url 이 "videos/파일" 이면 그 파일 위에 그린다
   - 카메라 · 영상 파일을 못 찾은 줄도 지우지 않도록 "cam:카메라이름" 열쇠로 들고 있다가 그대로 다시 저장한다 */

const ROI_KINDS = {
  danger: { label: "위험구역", color: "#ff5d5d" },
  control: { label: "통제구역", color: "#ff9a1f" },
  manage: { label: "관리구역", color: "#6cb6ff" },
  safe: { label: "안전구역", color: "#3ddc84" },
};
const ROI_ORPHAN = "cam:"; // 영상 파일이 없는 줄의 books 열쇠 앞머리

const roiFileOf = (cam) => (cam && cam.stream_url && cam.stream_url.startsWith("videos/") ? cam.stream_url.slice(7) : "");

// books 열쇠(영상 파일) → 카메라. 같은 파일을 여러 카메라가 쓰면 번호가 작은 카메라
function roiCamOf(cams, key) {
  if (key.startsWith(ROI_ORPHAN)) return cams.find((c) => c.name === key.slice(ROI_ORPHAN.length)) || null;
  return cams.find((c) => roiFileOf(c) === key) || null;
}

// 구역 uid = 카메라 번호 × 1000 + 구역 번호. 두 화면이 같은 구역을 같은 uid 로 가리킨다 (?uid=)
function roiUid(cam, no, key) {
  if (cam) return cam.id * 1000 + no;
  let h = 0;
  for (const ch of key) h = (h * 31 + ch.charCodeAt(0)) % 1000;
  return 900000 + h * 1000 + no;
}

async function loadRoiBooks(cams) {
  const rows = await api("/api/roi-zones");
  const books = {};
  rows.forEach((r) => {
    const cam = cams.find((c) => c.name === r.camera);
    const kind = Object.keys(ROI_KINDS).find((k) => ROI_KINDS[k].label === r.kind);
    if (!kind) return;
    const key = (cam && roiFileOf(cam)) || r.file || ROI_ORPHAN + r.camera;
    const list = books[key] || (books[key] = []);
    let roi = list.find((x) => x.no === r.no);
    if (!roi) {
      roi = { uid: roiUid(cam, r.no, key), no: r.no, kind, enabled: r.enabled !== false, listed: true, keys: [] };
      if (r.schedule) roi.schedule = r.schedule;
      list.push(roi);
    }
    roi.keys.push({ frame: r.frame - 1, pts: r.points, time: r.time });
  });
  Object.values(books).forEach((list) => list.forEach((roi) => roi.keys.sort((a, b) => a.frame - b.frame)));
  return books;
}

function roiRows(books, cams) {
  const rows = [];
  Object.keys(books).forEach((key) => {
    const cam = roiCamOf(cams, key);
    const orphan = key.startsWith(ROI_ORPHAN);
    (books[key] || []).forEach((roi) => {
      const kind = ROI_KINDS[roi.kind];
      if (!kind) return;
      (roi.keys || []).forEach((k) => {
        if (!k.pts || k.pts.length < 3) return;
        const row = {
          camera: cam ? cam.name : orphan ? key.slice(ROI_ORPHAN.length) : key,
          cameraName: cam ? [cam.work_zone_name, cam.location_desc].filter(Boolean).join(" · ") || cam.name : null,
          file: orphan ? null : key,
          no: roi.no,
          kind: kind.label,
          frame: k.frame + 1,
          time: k.time ?? null,
          points: k.pts,
          enabled: roi.enabled !== false,
        };
        if (roi.schedule) row.schedule = roi.schedule;
        rows.push(row);
      });
    });
  });
  return rows;
}

function saveRoiBooks(books, cams) {
  return api("/api/roi-zones", { method: "PUT", body: roiRows(books, cams) });
}
