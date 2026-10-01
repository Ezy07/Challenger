from selenium import webdriver  # 크롬을 파이썬으로 켜서 홈페이지를 여는 도구
from selenium.webdriver.common.by import By  # 칸을 찾을 때 XPath를 쓰겠다고 지정
from selenium.webdriver.support.ui import WebDriverWait  # 칸이 나타날 때까지 기다리기
from selenium.webdriver.support import expected_conditions as EC  # "화면에 보임" 같은 기다림 조건
from selenium.webdriver.chrome.service import Service  # 크롬 드라이버를 실행하는 설정
from selenium.webdriver.chrome.options import Options  # 창 숨기기, 창 크기 같은 옵션

from datetime import datetime  # 지금 날짜와 시각을 가져옴
import ctypes  # 윈도우 콘솔에서 줄 지우기 기능을 켜기 위함
import json  # weather.json 파일을 읽고 쓰기 위함
import os  # 파일 경로를 만들 때 사용
import sys  # 화면에 글자를 바로 출력할 때 사용
import time  # 1초 쉬기, 새로고침 간격 재기


def enable_ansi():
    """Windows 터미널에서 줄 지우기·커서 이동이 되게 한다."""
    if os.name != "nt":  # 윈도우가 아니면
        return  # 따로 켤 것이 없으니 끝
    try:  # 실패해도 프로그램이 멈추지 않게
        handle = ctypes.windll.kernel32.GetStdHandle(-11)  # 화면(콘솔) 손잡이를 가져옴
        mode = ctypes.c_uint32()  # 지금 콘솔 설정을 담을 상자
        if ctypes.windll.kernel32.GetConsoleMode(handle, ctypes.byref(mode)):  # 설정을 읽었으면
            ctypes.windll.kernel32.SetConsoleMode(handle, mode.value | 0x0004)  # 색·커서 이동을 허용
    except Exception:  # 여기서 오류가 나도
        pass  # 그냥 넘어감 (출력만 조금 덜 예쁘게 됨)


_block_shown = False  # 아직 날씨 줄을 한 번도 안 찍었다는 표시


def show_block(lines):
    """이미 찍어 둔 줄을 지우고, 같은 자리에 다시 출력한다."""
    global _block_shown  # 함수 밖의 변수를 바꿔도 되게 함
    if _block_shown:  # 예전에 이미 줄을 찍었다면
        sys.stdout.write(f"\033[{len(lines)}A")  # 그 줄 수만큼 커서를 위로 올림
    for line in lines:  # 출력할 한 줄씩
        sys.stdout.write("\033[2K" + line + "\n")  # 그 줄을 지운 뒤 새 글자를 씀
    sys.stdout.flush()  # 화면에 바로 보이게 밀어 넣음
    _block_shown = True  # 이제부터는 "이미 찍은 적 있음"


enable_ansi()  # 윈도우면 줄 덮어쓰기가 되게 먼저 켬

##### 옵션 설정 #####
chrome_options = Options()  # 크롬 실행 옵션 상자를 만듦
chrome_options.add_argument("--headless")  # 크롬 창을 화면에 띄우지 않음
chrome_options.add_argument("--window-size=1920,1080")  # 창을 크게 해서 아래쪽 칸이 접히지 않게
service = Service()  # 크롬 드라이버를 기본 설정으로 준비
driver = webdriver.Chrome(service=service, options=chrome_options)  # 숨긴 크롬을 실제로 켬

##### 페이지 접속 > 포항(송도) #####
URL = "https://www.weather.go.kr/w/index.do#dong/4711155000/36.02889/129.37784"  # 포항 송도동 날씨 주소

##### 기본 값 추출 칸 #####
# 아래 긴 글자는 개발자 도구에서 복사한 XPath. 홈페이지에서 그 칸의 위치
PLACE = '//*[@id="index-bookmarks"]/div[1]/a/i'  # 지역 이름 (경상북도 포항시남구 송도동)
TMP = '//*[@id="current-weather"]/div[2]/ul[1]/li[1]/span[4]'  # 지금 온도
FEEL = '//*[@id="current-weather"]/div[2]/ul[1]/li[1]/span[5]'  # 체감온도
HUM = '//*[@id="current-weather"]/div[2]/ul[2]/li[1]/span[2]'  # 습도
WIND = '//*[@id="current-weather"]/div[2]/ul[2]/li[2]/span[2]'  # 바람
RAIN = '//*[@id="current-weather"]/div[2]/ul[2]/li[3]/span[2]'  # 강수량
NEWS = '//*[@id="current-weather"]/div[4]'  # 기상 특보 글
# 대기질: 바깥 span[1]은 감싼 칸. 숫자는 그 안쪽 span
AIR = '//*[@id="current-weather"]/div[5]/ul'  # 대기질 목록의 시작점
PM25 = AIR + '/li[1]/strong/span[1]/span[1]'  # 초미세먼지 숫자
PM10 = AIR + '/li[2]/strong/span[1]/span[1]'  # 미세먼지 숫자
O3 = AIR + '/li[3]/strong/span[1]/span[1]'  # 오존 숫자
PM25_STATUS = AIR + '/li[1]/strong/span[2]'  # 초미세먼지 등급 (좋음)
PM10_STATUS = AIR + '/li[2]/strong/span[2]'  # 미세먼지 등급
O3_STATUS = AIR + '/li[3]/strong/span[2]'  # 오존 등급

# 따로 더 뽑아올 값
SUMRISE = '//*[@id="current-weather"]/div[3]/ul/li[1]/span[2]'  # 일출 시각
SUMSET = '//*[@id="current-weather"]/div[3]/ul/li[2]/span[2]'  # 일몰 시각

SKY = '//*[@id="current-weather"]//span[contains(@class,"wic")]'  # 현재 날씨 아이콘 (글자가 없을 수 있음)
SKY_3H = '//*[@id="digital-forecast"]/div[1]/div[5]/div[2]/div[1]/div[1]/div/div[2]/ul[1]/li[2]/span[2]'  # 예보 맨 앞 열의 날씨 (못 찾을 때 씀)
SKY_HOUR = '//*[@id="digital-forecast"]//span[contains(@class,"wic")]'  # 예보표에서 날씨 아이콘을 아무거나 찾을 때
PERIODS = [f"{h:02d}시" for h in range(24)]  # 00시, 01시, …, 23시 (1시간마다)
SKY_NAME = {  # 아이콘 클래스 코드 → 한글 날씨
    "DB01": "맑음", "NB01": "맑음",  # 낮/밤 맑음
    "DB02": "구름조금", "NB02": "구름조금",  # 낮/밤 구름조금
    "DB03": "구름많음", "NB03": "구름많음",  # 낮/밤 구름많음
    "DB04": "흐림", "NB04": "흐림",  # 낮/밤 흐림
    "DB05": "비",  # 비
    "DB06": "눈",  # 눈
    "DB07": "비 또는 눈", "NB07": "비 또는 눈",  # 진눈깨비
    "DB08": "소나기", "NB08": "소나기",  # 소나기
    "DB09": "빗방울",  # 약한 비
    "DB10": "빗방울/눈날림",  # 비와 눈이 섞임
    "DB11": "눈날림", "NB11": "눈날림",  # 눈날림
}

REFRESH_SEC = 60  # 60초마다 홈페이지를 새로고침
SAVE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "weather.json")  # 이 파일과 같은 폴더의 json
_last_saved = None  # 직전에 파일에 저장한 내용. 같으면 다시 쓰지 않음

driver.get(URL)  # 위에서 정한 주소로 이동


def read_text(xpath):
    """지금 화면에 있는 그 칸의 글자를 읽는다."""
    el = WebDriverWait(driver, 30).until(  # 최대 30초 동안
        EC.visibility_of_element_located((By.XPATH, xpath))  # 그 XPath 칸이 화면에 보이기를 기다림
    )
    return el.text.replace(" ", "").replace("\n", "")  # 글자를 읽고 공백·줄바꿈을 없앰


def read_keep_space(xpath):
    """지역·특보처럼 띄어쓰기를 남긴다. 줄바꿈만 한 칸으로 바꾼다."""
    el = WebDriverWait(driver, 30).until(  # 최대 30초 동안
        EC.visibility_of_element_located((By.XPATH, xpath))  # 그 칸이 보이기를 기다림
    )
    return (el.text or "").replace("\n", " ").strip()  # 줄바꿈은 띄어쓰기로, 앞뒤 빈칸만 제거


def read_air(xpath):
    """대기질 칸. 숨겨져 있어도 textContent로 읽고, 글자가 생길 때까지 기다린다."""

    def _filled(_driver):
        els = _driver.find_elements(By.XPATH, xpath)  # 그 칸이 몇 개인지 찾음
        if not els:  # 아직 칸이 없으면
            return False  # 더 기다리라는 뜻
        raw = els[0].get_attribute("textContent") or ""  # 숨겨져 있어도 안쪽 글자를 가져옴
        text = raw.replace(" ", "").replace("\n", "").split("범례")[0]  # 공백 제거 후 "범례" 앞만 남김
        for extra in ("초미세먼지", "미세먼지", "오존"):  # 링크에 붙은 이름들
            text = text.split(extra)[0]  # "좋음초미세먼지" → "좋음"
        return text if text else False  # 글자가 있으면 그 값, 없으면 계속 기다림

    return WebDriverWait(driver, 15).until(_filled)  # 15초 안에 글자가 채워지기를 기다림


def ensure_1hour_tab():
    """예보표를 '1시간 간격'으로 맞춘다. 이미 켜져 있으면 그대로 둔다."""
    btns = driver.find_elements(By.XPATH, '//*[@id="digital-forecast"]//button[contains(.,"1시간")]')  # 1시간 버튼 찾기
    if not btns:  # 버튼이 아직 없으면
        return  # 다음에 다시 시도
    cls = btns[0].get_attribute("class") or ""  # 버튼의 클래스 이름
    if "on" in cls.split():  # 이미 선택된 상태면
        return  # 그대로 둠
    driver.execute_script("arguments[0].click();", btns[0])  # 아니면 버튼을 눌러 1시간 간격으로 바꿈


def current_period():
    """지금 시각의 시. 9시 38분이면 09시."""
    hour = datetime.now().hour  # 분만 버리고 시만 씀
    return f"{hour:02d}시"  # "09시"처럼 두 자리로 만듦


def empty_day(day):
    """날짜와 빈 1시간 칸(00시~23시)을 만든다."""
    data: dict = {"날짜": day}  # 날짜 칸부터 만듦 (값은 글자 또는 딕셔너리)
    for period in PERIODS:  # 00시부터 23시까지
        data[period] = {}  # 아직 값이 없는 빈 칸
    return data  # 완성된 하루 뼈대를 돌려줌


def sky_from_el(el):
    """한 칸에서 날씨 글자 또는 아이콘 코드를 꺼낸다."""
    title = (el.get_attribute("title") or el.text or "").replace(" ", "").replace("\n", "")  # title 또는 보이는 글자
    if title:  # 글자가 있으면
        return title  # 그대로 사용 (맑음)
    cls = el.get_attribute("class") or ""  # 글자가 없으면 클래스 이름을 봄
    for part in cls.split():  # "wic DB01 large"를 단어로 나눔
        if part in SKY_NAME:  # DB01 같은 코드가 표에 있으면
            return SKY_NAME[part]  # 한글 날씨로 바꿈
    return ""  # 아무것도 못 찾으면 빈 글자


def read_sky():
    """지금 시각의 1시간 칸 날씨를 읽는다. 9시 38분이면 09시 예보."""
    ensure_1hour_tab()  # 예보표가 1시간 간격인지 확인
    period = current_period()  # 지금 써야 할 칸 이름 (9시면 "09시")
    hour = int(period.replace("시", ""))  # "12시"에서 숫자 12만 꺼냄
    today = datetime.now().strftime("%Y-%m-%d")  # 오늘 날짜 2026-09-30
    slot_xp = (  # 오늘 + 그 시각(12:00) 열의 날씨 아이콘
        f'//*[@id="digital-forecast"]//ul[contains(@class,"item")'
        f' and @data-date="{today}" and @data-time="{hour:02d}:00"]'
        f'//span[contains(@class,"wic")]'
    )
    els = driver.find_elements(By.XPATH, slot_xp)  # 그 열을 찾음
    if els:  # 찾았으면
        name = sky_from_el(els[0])  # 첫 번째 칸에서 날씨를 읽음
        if name:  # 글자가 있으면
            return name  # 그 날씨를 사용
    els = driver.find_elements(By.XPATH, SKY_3H)  # 없으면 예보 맨 앞 열을 시도
    if els:  # 맨 앞 열이 있으면
        name = sky_from_el(els[0])  # 거기서 읽음
        if name:  # 글자가 있으면
            return name  # 사용
    el = WebDriverWait(driver, 15).until(  # 그래도 없으면 현재 날씨 아이콘을 15초 기다림
        EC.presence_of_element_located((By.XPATH, SKY))  # 페이지에 있기만 하면 됨 (안 보여도)
    )
    name = sky_from_el(el)  # 아이콘에서 날씨를 꺼냄
    if name:  # 있으면
        return name  # 사용
    return read_text(SKY_HOUR)  # 마지막 수단: 예보표의 아무 날씨 글자


def sky_icon(name):
    """날씨 글자에 맞는 이모지. '비 또는 눈'처럼 긴 말부터 본다."""
    if "비 또는 눈" in name or "빗방울/눈날림" in name:  # 비와 눈이 같이 오면
        return "🌨️"  # 진눈깨비 아이콘
    if "눈" in name:  # 눈, 눈날림
        return "🌨️"  # 눈 아이콘
    if "비" in name or "소나기" in name or "빗방울" in name:  # 비 계열
        return "☔"  # 비 아이콘
    if "구름" in name:  # 구름조금, 구름많음
        return "⛅"  # 구름 아이콘
    if "흐림" in name:  # 흐림
        return "☁️"  # 흐린 구름
    if "맑음" in name:  # 맑음
        return "☀️"  # 해
    return "None"  # 아직 모르면 글자로 None


def load_weather_file():
    """이미 있는 weather.json을 읽는다. 없거나 예전 형식이면 빈 칸으로 시작한다."""
    empty = empty_day("")  # 날짜 없는 빈 하루
    if not os.path.exists(SAVE_PATH):  # 파일이 아직 없으면
        return empty  # 빈 내용으로 시작
    try:  # 파일이 깨져 있을 수도 있음
        with open(SAVE_PATH, encoding="utf-8") as f:  # 한글이 깨지지 않게 읽음
            data = json.load(f)  # json을 파이썬 딕셔너리로 바꿈
    except Exception:  # 읽기 실패하면
        return empty  # 빈 내용으로 시작
    if not isinstance(data, dict) or "01시" not in data:  # 3시간 칸만 있는 예전 파일이면
        return empty  # 새로 시작
    return data  # 정상적인 파일이면 그대로 사용


def save_weather():
    """1시간 칸 중 지금 시각만 덮어쓴다. 다른 시간은 그대로 둔다."""
    global _last_saved  # 직전 저장 내용을 함수 밖에서 기억
    values = (sky, temp, feel, hum, wind, rain)  # 저장에 필요한 값들
    if any(v in ("--", "", None) for v in values):  # 하나라도 아직 비어 있으면
        return  # 이번엔 저장하지 않음

    today = datetime.now().strftime("%Y-%m-%d")  # 오늘 날짜
    period = current_period()  # 지금 덮어쓸 칸 (9시면 "09시")
    slot = {  # 그 칸에 넣을 날씨 한 덩어리
        "날씨": sky,  # 하늘 상태
        "온도": temp,  # 기온
        "체감온도": feel,  # 체감
        "습도": hum,  # 습도
        "풍속": wind,  # 바람
        "강수": rain,  # 비/눈 양
    }

    data: dict = load_weather_file()  # 기존 파일을 읽음
    if data.get("날짜") != today:  # 파일 날짜가 오늘이 아니면
        data = empty_day(today)  # 어제 값을 버리고 오늘 뼈대를 만듦
    data["날짜"] = today  # 오늘 날짜를 적음
    data[period] = slot  # 해당 1시간 칸만 새 값으로 바꿈

    if data == _last_saved:  # 직전과 내용이 같으면
        return  # 파일을 또 쓰지 않음
    with open(SAVE_PATH, "w", encoding="utf-8") as f:  # 파일을 쓰기 모드로 염
        json.dump(data, f, ensure_ascii=False, indent=2)  # 한글 그대로, 들여쓰기 2칸으로 저장
    _last_saved = data  # 방금 저장한 내용을 기억


last_refresh = time.time()  # 마지막으로 새로고침한 시각 (시작 시점)
# 아직 홈페이지를 읽기 전. "--"는 "값 없음" 표시
place = "--"  # 지역 이름
temp = "--"  # 온도
feel = "--"  # 체감온도
hum = "--"  # 습도
wind = "--"  # 풍속
rain = "--"  # 강수
news = "--"  # 특보
pm25 = "--"  # 초미세먼지
pm10 = "--"  # 미세먼지
o3 = "--"  # 오존
pm25_status = "--"  # 초미세 등급
pm10_status = "--"  # 미세 등급
o3_status = "--"  # 오존 등급
sumrise = "--"  # 일출
sumset = "--"  # 일몰
sky = "--"  # 날씨

print("실시간 감시 시작. 끝내려면 Ctrl+C")  # 시작 안내
try:  # Ctrl+C로 끝낼 수 있게
    while True:  # 사용자가 멈출 때까지 반복
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")  # 화면에 쓸 지금 시각

        if time.time() - last_refresh >= REFRESH_SEC:  # 60초가 지났으면
            driver.refresh()  # 홈페이지를 새로고침
            last_refresh = time.time()  # 새로고침한 시각을 기록

        try:  # 칸을 못 찾으면(새로고침 중) 여기서 멈추지 않음
            temp = read_text(TMP).replace("℃", "°C")  # 온도. ℃와 )가 겹치지 않게 °C로 바꿈
            feel = read_text(FEEL).replace("℃", "°C")  # 체감온도도 같은 이유로 °C
            hum = read_text(HUM)  # 습도
            wind = read_text(WIND)  # 풍속
            rain = read_text(RAIN)  # 강수
            place = read_keep_space(PLACE)  # 지역. 띄어쓰기 유지
            news = read_keep_space(NEWS)  # 특보. 띄어쓰기 유지
            pm25 = read_air(PM25)  # 초미세먼지 숫자
            pm10 = read_air(PM10)  # 미세먼지 숫자
            o3 = read_air(O3)  # 오존 숫자
            pm25_status = read_air(PM25_STATUS)  # 초미세 등급
            pm10_status = read_air(PM10_STATUS)  # 미세 등급
            o3_status = read_air(O3_STATUS)  # 오존 등급
            sumrise = read_text(SUMRISE)  # 일출
            sumset = read_text(SUMSET)  # 일몰
            sky = read_sky()  # 1시간 예보 기준 날씨
            save_weather()  # 값이 바뀌었으면 json에 저장
        except Exception:  # 읽는 도중 오류가 나면
            pass  # 직전 값을 유지하고 다음 초에 다시 시도

        gap = "  "  # 아이콘과 글자 사이 빈칸
        show_block([  # 아래 줄들을 같은 자리에 다시 그림
            f"{'=' * 6} {now}  {place} {'=' * 6}",  # 시각과 지역
            f"{sky_icon(sky)}{gap}날씨:{sky}",  # 날씨 아이콘과 글자
            f"🌡️{gap}온도:{temp}{gap}{feel}  💧{gap}습도:{hum}",  # 온도, 체감, 습도
            f"💨{gap}풍속:{wind}  🌧️{gap}강수:{rain}",  # 바람, 강수
            f"🌫️{gap}초미세:{pm25}㎍/m³-{pm25_status}  미세:{pm10}㎍/m³-{pm10_status}  오존:{o3}ppm-{o3_status}",  # 대기질
            f"⚠️{gap}특보:{news}",  # 특보
            f"🌅{gap}일출:{sumrise}  🌇{gap}일몰:{sumset}",  # 일출, 일몰
        ])
        time.sleep(1)  # 1초 쉬고 다시 위부터
except KeyboardInterrupt:  # Ctrl+C를 누르면
    print("\n종료")  # 끝났다고 알림
    quit()  # 프로그램 종료
