"""db/schema.sql 을 읽어 ERD 그림을 만든다.

    python tools/erd.py            # docs/erd-v3.html + docs/erd-v3.png
    python tools/erd.py --html     # HTML 만 (PNG 는 Microsoft Edge 로 찍음)

테이블 · 컬럼 · 외래키는 schema.sql 에서 그대로 읽는다. 아래 GROUPS(묶음 · 설명)와
CHANGED(이전 차수에서 바뀐 곳 표시)만 손으로 고치면 된다. 표시용 패키지 없이 표준 라이브러리만 쓴다
(PNG 아래 여백 자르기만 Pillow 가 있으면 한다).
"""

import argparse
import html
import re
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCHEMA = ROOT / "db" / "schema.sql"
OUT = ROOT / "docs" / "erd-v3"
VERSION = "3차"

# (제목, 부제, 색, [(테이블, 설명), ...]) · 화면 배치 순서
GROUPS = [
    ("회원 · 조직", "로그인하는 사람", "blue", [
        ("organization", "조직 · 부서"),
        ("users", "회원"),
    ]),
    ("구역 · 카메라 · ROI", "현장 CAM · TC CAM", "green", [
        ("work_zone", "작업구역"),
        ("site_plan", "현장 도면 (한 장)"),
        ("camera", "카메라"),
        ("roi", "카메라 화면 위 감지 영역"),
    ]),
    ("이벤트", "AI 감지 → 알림 → 처리", "red", [
        ("event", "감지 이벤트"),
        ("event_action", "처리 기록"),
        ("event_snapshot", "스냅샷"),
    ]),
    ("감지 규칙", "기본값 + ROI별 덮어쓰기", "purple", [
        ("detection_type", "감지 유형"),
        ("alert_rule", "유형별 기본값"),
        ("release_check_item", "경보 해제 항목"),
        ("roi_rule", "ROI별 덮어쓰기"),
    ]),
    ("작업자 · 교육", "현장작업자 (로그인 X)", "teal", [
        ("worker", "현장작업자"),
        ("education", "안전교육 목록"),
        ("worker_education", "교육 이수 이력"),
    ]),
    ("작업 · 장비", "안전관리자가 매일 관리", "slate", [
        ("work", "작업"),
        ("work_assignment", "작업 ↔ 작업자"),
        ("equipment", "중장비 (현재 상태)"),
        ("equipment_daily_log", "일일 수동 기록"),
    ]),
]

# 2차 ERD(docs/erd-v2.png)에서 바뀐 곳. 테이블 이름만 쓰면 새 테이블
CHANGED = {
    "education": None,
    "worker_education": None,
    "site_plan": None,
    "camera": {"plan_x", "plan_y", "plan_dir", "plan_color"},
    "users": {"status", "failed_login_count", "locked_until"},
    "worker": {"start_date", "special_reasons", "special_memo", "special_since", "special_by", "is_active"},
    "equipment": {"equip_type", "reg_no", "spec", "company", "status"},
    "alert_rule": {"is_active"},
    "work": {"start_date", "end_date", "description"},
    "equipment_daily_log": {"status", "inspected_at"},
}
CHANGE_NOTES = [
    ("education · worker_education", "새 테이블: 안전교육 목록과 작업자별 이수 이력"),
    ("site_plan · camera", "새 테이블: 현장 도면 한 장 (구역 표시 · 카메라 배치도 배경), 카메라 도면 위 위치 · 방향 · 화각 색"),
    ("worker", "특별관리 사유 여러 개(JSON) · 메모 · 지정일 · 지정한 사람, 현장 투입일"),
    ("users", "DELETED 상태 추가 (처리 기록 때문에 행은 남김), 5번 틀리면 15분 잠금(locked_until)"),
    ("equipment", "등록번호 · 제원 · 소속 회사, 레미콘 · 덤프 유형, 상태 OUT → BROKEN(고장)"),
    ("work", "work_date → start_date · end_date (여러 날 작업), 작업 내용"),
    ("alert_rule", "is_active: 끄면 그 유형은 이벤트를 만들지 않음"),
    ("equipment_daily_log", "운전 전 점검 시각(inspected_at)"),
]
FLOW = [
    ("TC CAM이 감지", "camera (view_page = 2)"),
    ("규칙 적용 · 이벤트 생성", "roi_rule → alert_rule → event"),
    ("관제화면 알림 · 크레인 표시", "camera.equipment_id"),
    ("항목별 작업 허가", "release_check_item → event_action(PERMIT)"),
    ("모두 허가되면 해제", "event_action(RESOLVE) · status = DONE"),
]


# ---------------------------------------------------------------- schema.sql 읽기
def parse(sql: str) -> dict[str, dict]:
    tables = {}
    for name, body in re.findall(r"CREATE TABLE (\w+) \((.*?)\n\) ENGINE", sql, re.S):
        cols, pk, uq, fk = [], [], set(), {}
        for raw in body.splitlines():
            line, _, comment = raw.strip().partition("--")
            line = line.strip().rstrip(",")
            if not line:
                continue
            if m := re.match(r"PRIMARY KEY \((.+?)\)", line):
                pk = [c.strip() for c in m[1].split(",")]
            elif m := re.match(r"UNIQUE KEY \w+ \((.+?)\)", line):
                cs = [c.strip() for c in m[1].split(",")]
                if len(cs) == 1:
                    uq.add(cs[0])
            elif m := re.match(r"CONSTRAINT \w+\s+FOREIGN KEY \((\w+)\)\s+REFERENCES (\w+)", line):
                fk[m[1]] = m[2]
            elif line.startswith(("KEY ", "CONSTRAINT ")):
                continue
            else:
                col, rest = line.split(None, 1)
                cols.append({"name": col, "type": short_type(rest), "enum": enum_values(rest),
                             "null": " NOT NULL" not in f" {rest}", "note": comment.strip()})
        tables[name] = {"cols": cols, "pk": pk, "uq": uq, "fk": fk}
    return tables


def short_type(rest: str) -> str:
    t = re.match(r"(ENUM|\w+(?:\(\d+(?:,\d+)?\))?)", rest)[1]
    return {"TINYINT(1)": "BOOL"}.get(t, t)


def enum_values(rest: str) -> list[str]:
    m = re.match(r"ENUM\((.*?)\)", rest)
    return re.findall(r"'(\w+)'", m[1]) if m else []


# ---------------------------------------------------------------- HTML
COLORS = {  # 묶음 배경 · 테두리 · 제목
    "blue": ("#eef1fb", "#c9d2f0", "#3d55b8"),
    "green": ("#eaf5ee", "#bfdcc9", "#24804a"),
    "red": ("#fbeee9", "#efc6b8", "#c2421b"),
    "purple": ("#f3eef9", "#d5c6ea", "#7041a8"),
    "teal": ("#e8f4f5", "#b8dadd", "#1d7680"),
    "slate": ("#edf1f5", "#c8d2dc", "#3f5468"),
}


def render(tables: dict[str, dict]) -> str:
    group_of = {t: color for _, _, color, items in GROUPS for t, _ in items}
    missing = set(tables) - set(group_of)
    if missing:
        sys.exit(f"GROUPS 에 없는 테이블: {', '.join(sorted(missing))} (tools/erd.py 의 GROUPS 에 넣어 주세요)")
    e = html.escape

    def table_html(name: str, label: str) -> str:
        t = tables[name]
        changed = CHANGED.get(name, set())
        is_new = name in CHANGED and changed is None
        rows = []
        for c in t["cols"]:
            keys = []
            if c["name"] in t["pk"]:
                keys.append('<i class="k pk">PK</i>')
            if c["name"] in t["fk"]:
                keys.append('<i class="k fk">FK</i>')
            if c["name"] in t["uq"]:
                keys.append('<i class="k uq">UQ</i>')
            note = " · ".join(c["enum"]) if c["enum"] else ""
            if c["note"]:
                note = f"{note} — {c['note']}" if note else c["note"]
            ref = t["fk"].get(c["name"])
            ref_html = f'<b class="ref {group_of[ref]}">→ {e(ref)}</b>' if ref else ""
            mark = '<i class="v">' + VERSION + "</i>" if (changed and c["name"] in changed) else ""
            rows.append(
                f'<div class="row{" hi" if mark else ""}"><span class="n">{"".join(keys)}<code>{e(c["name"])}</code>'
                f'<em>{e(c["type"])}{"" if not c["null"] else " · NULL"}</em>{ref_html}{mark}</span>'
                f'<span class="note">{e(note)}</span></div>')
        badge = f'<i class="v">{VERSION} 새 테이블</i>' if is_new else ""
        return (f'<section class="tbl{" new" if is_new else ""}" id="t-{name}"><header><code>{e(name)}</code>{badge}'
                f'<span>{e(label)}</span></header>{"".join(rows)}</section>')

    groups = []
    for title, sub, color, items in GROUPS:
        groups.append(f'<div class="grp {color}"><h2>{e(title)} <small>{e(sub)}</small></h2>'
                      f'<div class="tbls">{"".join(table_html(t, label) for t, label in items)}</div></div>')

    changes = "".join(f"<li><b>{e(t)}</b>: {e(d)}</li>" for t, d in CHANGE_NOTES)
    flow = '<span class="arr">→</span>'.join(
        f'<div class="step{" key" if i == 3 else ""}"><b><i>{i + 1}</i> {e(a)}</b><code>{e(b)}</code></div>'
        for i, (a, b) in enumerate(FLOW))
    n_fk = sum(len(t["fk"]) for t in tables.values())
    css = "".join(f".{k}{{--bg:{bg};--bd:{bd};--fg:{fg}}}" for k, (bg, bd, fg) in COLORS.items())

    return f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><title>ERD {VERSION}</title>
<style>
{css}
*{{box-sizing:border-box;margin:0}}
body{{width:1920px;background:#f6f5f2;color:#1d232b;font:14px/1.45 "Malgun Gothic","Noto Sans KR",sans-serif;padding:44px 48px 48px}}
code{{font-family:Consolas,"Malgun Gothic",monospace}}
.top{{display:flex;justify-content:space-between;align-items:flex-end;margin-bottom:28px}}
h1{{font-size:38px;letter-spacing:-1px}}
.top p{{color:#5b6570;font-size:16px;margin-top:6px}}
.legend{{display:flex;gap:18px;align-items:center;color:#4a535d;font-size:14px}}
i{{font-style:normal}}
.k{{display:inline-block;font:700 10px/1 Consolas,monospace;padding:3px 4px;border-radius:3px;margin-right:4px;border:1px solid}}
.pk{{color:#a3540a;border-color:#e2b277;background:#fff6e8}}
.fk{{color:#2f55b5;border-color:#a9bce9;background:#eef3ff}}
.uq{{color:#5d6670;border-color:#c5cbd2;background:#f4f6f8}}
.v{{display:inline-block;font:700 10px/1 "Malgun Gothic",sans-serif;padding:3px 5px;border-radius:3px;background:#e8562a;color:#fff;margin-left:6px}}
.grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:20px;align-items:start}}
.grp{{background:var(--bg);border:1.5px solid var(--bd);border-radius:14px;padding:16px 14px 14px}}
.grp h2{{color:var(--fg);font-size:19px;margin:0 4px 12px}}
.grp h2 small{{color:#4a535d;font-size:13px;font-weight:400;margin-left:6px}}
.tbls{{display:grid;gap:12px}}
.wide{{grid-column:span 2}}
.wide .tbls{{grid-template-columns:1fr 1fr;align-items:start}}
.tbl{{background:#fff;border:1px solid #dcdfe3;border-radius:9px;overflow:hidden}}
.tbl.new{{border:2px solid #e8562a}}
.tbl header{{display:flex;align-items:center;gap:4px;padding:8px 12px;background:color-mix(in srgb,var(--bg) 70%,#fff);border-bottom:1px solid #e3e6ea}}
.tbl header code{{font-weight:700;font-size:15px}}
.tbl header span{{margin-left:auto;color:#5b6570;font-size:12.5px}}
.row{{display:flex;justify-content:space-between;gap:10px;padding:3px 12px;border-top:1px solid #f1f2f4}}
.row:first-of-type{{border-top:0}}
.row.hi{{background:#fff3ec}}
.n{{white-space:nowrap;display:flex;align-items:center}}
.n code{{font-size:13px}}
.n em{{font-style:normal;color:#8a939c;font-size:11px;margin-left:6px}}
.note{{color:#5b6570;font-size:11.5px;text-align:right;padding-top:1px;overflow-wrap:anywhere}}
.ref{{font:700 11px/1 "Malgun Gothic",sans-serif;color:var(--fg);background:var(--bg);border:1px solid var(--bd);border-radius:10px;padding:3px 7px;margin-left:6px}}
.side{{display:grid;gap:16px}}
.box{{background:#fff;border:1.5px solid #dcdfe3;border-radius:14px;padding:16px 18px}}
.box h3{{font-size:16px;margin-bottom:8px}}
.box.chg{{border-color:#efb9a4}}
.box.chg h3{{color:#c2421b}}
.box ol,.box ul{{padding-left:18px;color:#3b434c;font-size:13px;display:grid;gap:5px}}
.box p{{color:#4a535d;font-size:13px;margin-top:4px}}
.flow{{margin-top:22px;background:#fff;border:1.5px solid #dcdfe3;border-radius:14px;padding:16px 20px}}
.flow h3{{font-size:17px;margin-bottom:12px}}
.flow h3 small{{color:#5b6570;font-weight:400;font-size:13px;margin-left:8px}}
.steps{{display:flex;align-items:center;gap:10px}}
.step{{flex:1;background:#f7f8fa;border:1px solid #e1e4e8;border-radius:9px;padding:9px 12px}}
.step.key{{background:#fff3ec;border-color:#efb9a4}}
.step b{{display:block;font-size:14px}}
.step b i{{color:#c2421b;margin-right:4px}}
.step code{{color:#5b6570;font-size:12px}}
.arr{{color:#8a939c;font-size:20px}}
.foot{{margin-top:14px;color:#8a939c;font-size:12px;text-align:right}}
</style></head><body>
<div class="top">
  <div><h1>비전AI 안전관제 · 데이터 구조 (ERD {VERSION})</h1>
  <p>테이블 {len(tables)}개 · 외래키 {n_fk}개 · <code>db/schema.sql</code> 의 모든 컬럼 표시</p></div>
  <div class="legend"><span><i class="k pk">PK</i>기본키</span><span><i class="k fk">FK</i>외래키</span>
  <span><i class="k uq">UQ</i>중복 불가</span><span><b class="ref slate">→ 테이블</b> 가리키는 테이블 (색 = 그 묶음)</span>
  <span><i class="v">{VERSION}</i> 2차에서 바뀐 곳</span><span style="color:#8a939c">· NULL = 비워도 됨</span></div>
</div>
<div class="grid">
  {groups[0]}{groups[1]}{groups[2]}{groups[3]}
  {groups[4]}
  <div class="wide">{groups[5]}</div>
  <div class="side">
    <div class="box chg"><h3>2차에서 바뀐 점</h3><ol>{changes}</ol></div>
    <div class="box"><h3>읽는 법</h3>
      <p><b class="ref red">→ camera</b> 처럼 FK 옆에 가리키는 테이블이 붙어 있습니다. 가리키는 쪽이 N, 가리켜지는 쪽이 1 입니다. 예: 카메라 1대에 이벤트 여러 건.</p>
      <p>TC 경보는 event → camera → equipment 로 따라가 어느 크레인인지 찾습니다.</p></div>
  </div>
</div>
<div class="flow"><h3>경보 하나가 처리되는 흐름 <small>예: TC 3호기 인양물 직하부 작업자</small></h3><div class="steps">{flow}</div></div>
<div class="foot">tools/erd.py 가 db/schema.sql 에서 만든 그림 · {date.today():%Y-%m-%d}</div>
</body></html>
"""


# ---------------------------------------------------------------- PNG
def find_edge() -> str | None:
    for p in (r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
              r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
              r"C:\Program Files\Google\Chrome\Application\chrome.exe"):
        if Path(p).is_file():
            return p
    return shutil.which("msedge") or shutil.which("google-chrome") or shutil.which("chromium")


def screenshot(html_path: Path, png_path: Path) -> None:
    browser = find_edge()
    if not browser:
        sys.exit("Edge / Chrome 을 찾지 못했습니다. HTML 을 브라우저로 열어 캡처하세요: " + str(html_path))
    subprocess.run([browser, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--force-device-scale-factor=1",
                    "--window-size=1920,4000", f"--screenshot={png_path}", html_path.as_uri()],
                   check=True, capture_output=True, timeout=60)
    try:
        from PIL import Image
    except ImportError:
        print("Pillow 가 없어 아래 여백을 자르지 않았습니다 (pip install pillow)")
        return
    img = Image.open(png_path).convert("RGB")
    bg = img.getpixel((5, img.height - 5))
    bottom = next(y for y in range(img.height - 1, 0, -1)
                  if any(img.getpixel((x, y)) != bg for x in range(0, img.width, 4)))
    img.crop((0, 0, img.width, min(img.height, bottom + 48))).save(png_path, optimize=True)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--html", action="store_true", help="PNG 는 만들지 않음")
    args = ap.parse_args()
    tables = parse(SCHEMA.read_text(encoding="utf-8"))
    html_path = OUT.with_suffix(".html")
    html_path.write_text(render(tables), encoding="utf-8")
    print("만듦:", html_path.relative_to(ROOT))
    if not args.html:
        png = OUT.with_suffix(".png")
        screenshot(html_path, png)
        print("만듦:", png.relative_to(ROOT))


if __name__ == "__main__":
    main()
