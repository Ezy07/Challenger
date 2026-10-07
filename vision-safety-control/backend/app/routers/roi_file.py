"""구역 그리기 화면에서 저장한 ROI를 frontend/roi-zones.json 으로 남긴다."""

import json

from fastapi import APIRouter, HTTPException, Request, status

from ..config import settings

router = APIRouter(prefix="/api/roi-zones", tags=["ROI 파일"])

FILE = settings.frontend_dir / "roi-zones.json"
MAX_BYTES = 2_000_000
LOCAL_HOSTS = {"127.0.0.1", "::1", "testclient"}


def check_zones(data) -> None:
    if not isinstance(data, list):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "구역 목록이어야 합니다.")
    for item in data:
        if not isinstance(item, dict):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "구역 항목 형식이 아닙니다.")
        if not isinstance(item.get("camera"), str) or not item["camera"].strip():
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "카메라 이름이 없습니다.")
        if not isinstance(item.get("no"), int) or item["no"] < 1:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "구역 번호는 1 이상의 정수여야 합니다.")
        if not isinstance(item.get("kind"), str) or not item["kind"].strip():
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "구역 종류가 없습니다.")
        points = item.get("points")
        if not isinstance(points, list) or len(points) < 3 or any(
            not isinstance(p, list) or len(p) != 2 or not all(isinstance(n, (int, float)) for n in p)
            for p in points
        ):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "ROI 좌표는 점 3개 이상이어야 합니다.")


@router.put("")
async def save_roi_file(request: Request):
    host = request.client.host if request.client else ""
    if host not in LOCAL_HOSTS:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "이 컴퓨터에서만 구역 파일을 저장할 수 있습니다.")
    raw = await request.body()
    if len(raw) > MAX_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "구역 파일이 너무 큽니다.")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "JSON 형식이 아닙니다.")
    check_zones(data)
    FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"ok": True, "file": FILE.name, "count": len(data)}
