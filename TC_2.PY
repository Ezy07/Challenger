import math
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import matplotlib
matplotlib.use("TkAgg")
import matplotlib.pyplot as plt
import matplotlib.animation as animation

# ==========================================
# [한글 깨짐 및 마이너스 깨짐 방지 전역 설정]
# ==========================================
plt.rcParams['font.family'] = 'Malgun Gothic'
plt.rcParams['axes.unicode_minus'] = False

class CraneTType:
    """TC-1: T자형 크레인 (지브 수평 고정, 트롤리 전후 이동)"""
    def __init__(self, name, x, y, jib_length, counter_jib, speed=0.5, phase=0.0, trolley_phase=0.0):
        self.name = name
        self.x = x
        self.y = y
        self.jib_length = jib_length
        self.rear_radius = counter_jib + 1.5
        self.speed = speed
        self.phase = phase
        self.trolley_phase = trolley_phase
        self.max_radius = max(jib_length, self.rear_radius)
        
        self.angle = phase
        self.trolley_dist = jib_length * 0.7

    def update(self, frame):
        self.angle = (self.phase + frame * self.speed) % 360
        self.trolley_dist = self.jib_length * (0.55 + 0.30 * math.sin(frame * 0.008 + self.trolley_phase))

    def get_geometry(self):
        rad = math.radians(self.angle)
        j_x = self.x + self.jib_length * math.cos(rad)
        j_y = self.y + self.jib_length * math.sin(rad)
        c_x = self.x - self.rear_radius * math.cos(rad)
        c_y = self.y - self.rear_radius * math.sin(rad)
        load_x = self.x + self.trolley_dist * math.cos(rad)
        load_y = self.y + self.trolley_dist * math.sin(rad)
        
        # 지브 선을 그리기 위한 전체 좌표 반환 [카운터끝, 마스트, 지브끝]
        xs = [c_x, self.x, j_x]
        ys = [c_y, self.y, j_y]
        return xs, ys, (j_x, j_y), (load_x, load_y), self.max_radius


class CraneLuffingType:
    """TC-2: 러핑 크레인 (지브가 위아래로 기동하여 회전 반경 자체가 가변됨)"""
    def __init__(self, name, x, y, max_jib_length, counter_jib, min_luff_angle=15, max_luff_angle=80, speed=-0.4):
        self.name = name
        self.x = x
        self.y = y
        self.max_jib_length = max_jib_length
        self.rear_radius = counter_jib + 1.5
        self.speed = speed
        self.min_luff = min_luff_angle
        self.max_luff = max_luff_angle
        
        self.angle = 180.0
        self.current_luff_angle = 45.0

    def update(self, frame):
        self.angle = (180 + frame * self.speed) % 360
        luff_range = self.max_luff - self.min_luff
        self.current_luff_angle = self.min_luff + (luff_range / 2) + (luff_range / 2) * math.sin(frame * 0.006)

    def get_geometry(self):
        rad = math.radians(self.angle)
        luff_rad = math.radians(self.current_luff_angle)
        current_horizontal_jib = self.max_jib_length * math.cos(luff_rad)
        
        j_x = self.x + current_horizontal_jib * math.cos(rad)
        j_y = self.y + current_horizontal_jib * math.sin(rad)
        c_x = self.x - self.rear_radius * math.cos(rad)
        c_y = self.y - self.rear_radius * math.sin(rad)
        
        load_x = j_x
        load_y = j_y
        current_max_radius = current_horizontal_jib
        
        xs = [c_x, self.x, j_x]
        ys = [c_y, self.y, j_y]
        return xs, ys, (j_x, j_y), (load_x, load_y), current_max_radius


# ==========================================
# 1. 크레인 4대 현장 배치
#    대시보드 TC 탭과 같은 좌표·속도·간격을 쓴다.
# ==========================================
WARNING_DIST = 16.0
STOP_DIST = 6.0
COLORS = ["#6cb6ff", "#ff9a1f", "#3ddc84", "#c084fc"]


def make_cranes():
    """1·3호기는 T형, 2·4호기는 러핑. 대시보드 팝업과 같은 배치."""
    return [
        CraneTType("TC-1 (T형)", x=-8, y=-8, jib_length=55, counter_jib=15, speed=0.08, phase=300, trolley_phase=0.0),
        CraneLuffingType("TC-2 (러핑)", x=42, y=52, max_jib_length=50, counter_jib=12, speed=-0.05),
        CraneTType("TC-3 (T형)", x=80, y=-8, jib_length=55, counter_jib=14, speed=-0.08, phase=240, trolley_phase=0.9),
        CraneLuffingType("TC-4 (러핑)", x=14, y=90, max_jib_length=46, counter_jib=12, speed=0.042),
    ]


def closest_pair(tips):
    """지브 끝단 사이가 가장 가까운 두 호기를 고른다."""
    best = None
    for i in range(len(tips)):
        for j in range(i + 1, len(tips)):
            dist = math.dist(tips[i], tips[j])
            if best is None or dist < best[0]:
                best = (dist, i, j)
    return best


def risk_text(distance, left, right):
    """TC_2 원래 기준. 6m 이하는 정지, 16m 이하는 주의."""
    if distance <= STOP_DIST:
        return (
            "#FFD2D2",
            f" [현장 위험 상태] STOP {left}·{right} 충돌 위험 임계점 도달\n"
            " [자동 시스템 인터록] 해당 크레인 구동부 비상 정지(STOP)",
        )
    if distance <= WARNING_DIST:
        return (
            "#FFE6CC",
            f" [현장 위험 상태] WARN {left}·{right} 상호 근접 감지\n"
            " [자동 시스템 인터록] 선회 속도 50% 감속 가동",
        )
    return (
        "#E6F4EA",
        " [현장 위험 상태] OK 안전 거리 유지 중 (특이사항 없음)\n"
        " [자동 시스템 인터록] 상호 간섭 없음 (정상 속도 운행 허용)",
    )


def main():
    cranes = make_cranes()
    fig, ax = plt.subplots(figsize=(9, 9))
    ax.set_aspect("equal")
    ax.grid(True, linestyle="--", alpha=0.5)
    ax.set_xlim(-70, 150)
    ax.set_ylim(-70, 150)

    lines, loads, circles = [], [], []
    for crane, color in zip(cranes, COLORS):
        ax.plot(crane.x, crane.y, "o", color=color, markersize=7)
        line, = ax.plot([], [], color=color, linewidth=4, label=crane.name)
        load, = ax.plot([], [], "o", color=color, markersize=7)
        radius = crane.max_radius if hasattr(crane, "max_radius") else crane.max_jib_length
        circle = plt.Circle((crane.x, crane.y), radius, color=color, fill=False, linestyle=":", alpha=0.35)
        ax.add_patch(circle)
        lines.append(line)
        loads.append(load)
        circles.append(circle)

    jib_dist_line, = ax.plot([], [], color="red", linestyle="--", linewidth=2, label="최근접 지브 간격")
    dist_text = ax.text(0, 0, "", fontsize=10, fontweight="bold", color="darkred",
                        bbox=dict(boxstyle="round,pad=0.3", facecolor="white", alpha=0.9, edgecolor="red"))
    ax.legend(loc="upper right", fontsize=9)
    status_box = ax.text(-85, -72, "", fontsize=10, fontweight="bold",
                         bbox=dict(facecolor="white", alpha=0.9, edgecolor="gray"))

    def animate(frame):
        geos = []
        tips = []
        for crane in cranes:
            crane.update(frame)
            xs, ys, tip, load, radius = crane.get_geometry()
            geos.append((xs, ys, tip, load, radius))
            tips.append(tip)

        distance, i, j = closest_pair(tips)
        for idx, circle in enumerate(circles):
            circle.set_radius(geos[idx][4])
            lines[idx].set_data(geos[idx][0], geos[idx][1])
            loads[idx].set_data([geos[idx][3][0]], [geos[idx][3][1]])

        tip_a, tip_b = tips[i], tips[j]
        jib_dist_line.set_data([tip_a[0], tip_b[0]], [tip_a[1], tip_b[1]])
        dist_text.set_position(((tip_a[0] + tip_b[0]) / 2, (tip_a[1] + tip_b[1]) / 2))
        dist_text.set_text(f"{distance:.1f} m")

        ax.set_title("타워크레인 4대 지브 간 실시간 충돌 방지\nT형 2대 · 러핑 2대", fontsize=12, fontweight="bold", pad=15)
        lines_txt = []
        for crane in cranes:
            if isinstance(crane, CraneTType):
                lines_txt.append(f" ▶ {crane.name} 선회 {crane.angle:5.1f}° | 트롤리 {crane.trolley_dist:4.1f}m")
            else:
                lines_txt.append(f" ▶ {crane.name} 선회 {crane.angle:5.1f}° | 지브각 {crane.current_luff_angle:4.1f}°")
        box_color, risk = risk_text(distance, cranes[i].name, cranes[j].name)
        msg = f" [최근접 지브 간격] {distance:6.2f} m\n" + "\n".join(lines_txt) + "\n" + risk
        status_box.set_text(msg)
        bbox = status_box.get_bbox_patch()
        if bbox is not None:
            bbox.set_facecolor(box_color)
        return (*lines, *loads, jib_dist_line, dist_text, *circles, status_box)

    animation.FuncAnimation(fig, animate, frames=1000, interval=25, blit=False, cache_frame_data=False, repeat=True)
    plt.show()


if __name__ == "__main__":
    main()