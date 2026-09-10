"""
market_energy_matching.py

alt_vacancy_indicator.py의 TARGET_MARKETS(2026-09-07 기준 277개 노후 대형상가/
전통시장, 그중 safety_map.py의 MARKET_COORDS에 좌표가 있는 171곳)를 상가정보
API 건물명과 안전하게 매칭해서 전력사용량 추세를 구한다. risk_grade_model.py의
MARKET_ENERGY_TREND에 넣을 수 있는 형태로 출력.

★ 2026-09-01: 8개구(강남·마포·광진·종로·중구·영등포·성동·강북)만 스캔해서
  4/48곳만 매칭 성공(risk_grade_model.py에 하드코딩됨).
★ 2026-09-02: 나머지 44곳이 있는 10개구(용산·동대문·관악·성북·도봉·노원·
  강서·동작·송파·중랑)로 확장. 어제와 같은 "안전 매칭" 원칙을 그대로 적용.
★ 2026-09-07: TARGET_MARKETS가 48 -> 277개로 커지면서 MARKET_COORDS도 48 ->
  171개로 늘어남 - 기존에 스캔했던 18개구 안에도 그때는 없던 신규 매칭 대상이
  생겼을 수 있어서, "이미 스캔한 구는 건너뛴다"는 제약을 없애고 서울 25개구
  전체를 매번 새로 스캔하도록 바꿈. 매칭 로직 자체(구 단위 제한 + 유일 매칭만)는
  그대로라 재매칭해도 안전하다 - API 호출이 좀 더 들 뿐이다.

안전 매칭 원칙(중요 - 이걸 안 지키면 "평화시장/청평화시장/동평화시장" 같은
서로 다른 상권이 섞이는 사고가 남):
  1. 상권이 속한 구(MARKET_COORDS) 안에서만 건물명을 찾는다
  2. 상권명 첫 괄호 앞부분을 "코어명"으로 쓰고, 길이 3자 미만이면 매칭 시도 안 함
  3. 코어명을 포함(or 코어명에 포함)하는 길이 3자 이상 건물명이 "정확히 1개
     주소(도로명코드,본번,부번)"일 때만 채택. 여러 주소가 나오면 그냥 제외한다
     (틀린 매칭보다 매칭 안 되는 게 낫다).

돌리는 법:
  python market_energy_matching.py
  (25개구 전수 스캔이라 몇 분 걸림)
  출력: 매칭 성공 상권 목록 + risk_grade_model.py MARKET_ENERGY_TREND에
        붙여넣을 수 있는 코드 스니펫
"""
import os
import re
import time

import requests
from dotenv import load_dotenv

from energy_vacancy_indicator import load_energy_usage
from risk_grade_model import MARKET_ENERGY_TREND
from safety_map import MARKET_COORDS
from seoul_districts import SEOUL_GU_CODES

load_dotenv()

SERVICE_KEY_SANGGA = os.environ.get("SANGGA_API_KEY", "")
SANGGA_BASE = "https://apis.data.go.kr/B553077/api/open/sdsc2"

# 서울 25개구 전체 스캔 (2026-09-07, 위 ★ 참고 - "이미 스캔한 구 제외" 방식을
# 없애고 매번 전체를 다시 스캔)
NEW_GU_CODES = SEOUL_GU_CODES

NUM_ROWS_PER_PAGE = 1000
REQUEST_TIMEOUT = 20
MAX_RETRY = 2


def safe_get(url, params):
    for attempt in range(MAX_RETRY + 1):
        try:
            return requests.get(url, params=params, timeout=REQUEST_TIMEOUT)
        except requests.exceptions.RequestException:
            if attempt < MAX_RETRY:
                time.sleep(1)
                continue
            return None


def scan_gu_stores(signgu_cd: str) -> list:
    """구 전체 상가업소를 totalCount까지 빠짐없이 페이지네이션 스캔."""
    url = f"{SANGGA_BASE}/storeListInDong"
    items = []
    page = 1
    total_count = None
    while True:
        params = {"serviceKey": SERVICE_KEY_SANGGA, "divId": "signguCd", "key": signgu_cd,
                   "numOfRows": NUM_ROWS_PER_PAGE, "pageNo": page, "type": "json"}
        resp = safe_get(url, params)
        if resp is None:
            break
        try:
            body = resp.json().get("body", {})
        except Exception:
            break
        if total_count is None:
            total_count = body.get("totalCount", 0)
        page_items = body.get("items", [])
        if not page_items:
            break
        items.extend(page_items)
        if len(items) >= total_count or len(page_items) < NUM_ROWS_PER_PAGE:
            break
        page += 1
        time.sleep(0.15)
    return items


def core_name(market_name: str) -> str:
    core = re.split(r"[(]", market_name)[0].strip()
    core = re.sub(r"[A-D]동$", "", core)
    return core


def match_markets(gu_stores: dict) -> dict:
    """
    gu_stores: {구명: [store, ...]}
    반환: {상권명: (road_key, bldNm, gu)} - 구 안에서 유일하게 매칭되는 것만
    """
    matched = {}
    for market, (lat, lng, gu) in MARKET_COORDS.items():
        if gu not in gu_stores:
            continue  # 이번에 스캔한 구가 아님(어제 이미 처리했거나 대상 외)
        core = core_name(market)
        if len(core) < 3:
            continue
        candidates = {}
        for s in gu_stores[gu]:
            nm = (s.get("bldNm") or "").strip()
            if len(nm) < 3:
                continue
            if core in nm or nm in core:
                rd, bb, bu = s.get("rdnmCd"), s.get("bldMnno"), s.get("bldSlno")
                if not rd or bb in (None, ""):
                    continue
                key = (rd, int(bb), int(bu) if bu not in (None, "") else 0)
                candidates.setdefault(key, nm)
        if len(candidates) == 1:
            key, nm = list(candidates.items())[0]
            matched[market] = (key, nm, gu)
    return matched


if __name__ == "__main__":
    print(f"=== 1단계: 대상 {len(NEW_GU_CODES)}개구 전수 스캔 ===")
    gu_stores = {}
    for cd, gu in NEW_GU_CODES.items():
        print(f"  {gu}({cd}) 스캔 중...")
        stores = scan_gu_stores(cd)
        gu_stores[gu] = stores
        print(f"    -> {len(stores):,}건 조회")

    print(f"\n=== 2단계: {len(MARKET_COORDS)}개 상권과 안전 매칭 (구 단위 제한 + 유일 매칭만) ===")
    matched = match_markets(gu_stores)
    print(f"매칭 성공: {len(matched)}곳 (기존 MARKET_ENERGY_TREND에 이미 있던 것 포함,"
          f" 재확인된 매칭도 그대로 재출력됨)")
    for m, (key, nm, gu) in matched.items():
        print(f"  {m:45s} -> {nm} ({gu}) key={key}")

    print("\n=== 3단계: 에너지 사용량 조인 + 추세 계산 ===")
    usage = load_energy_usage(signgu_codes=NEW_GU_CODES.keys())

    trend_results = {}
    for m, (key, nm, gu) in matched.items():
        u = usage.get(key)
        if u is None or not u["elec"]:
            print(f"  ⚠️ {m}: 에너지 데이터 없음, 스킵")
            continue
        elec = u["elec"]
        months_sorted = sorted(elec.keys())
        if len(months_sorted) < 4:
            print(f"  ⚠️ {m}: 월 데이터 부족({len(months_sorted)}개월), 스킵")
            continue
        half = len(months_sorted) // 2
        early = [elec[x] for x in months_sorted[:half]]
        recent = [elec[x] for x in months_sorted[half:]]
        early_avg, recent_avg = sum(early) / len(early), sum(recent) / len(recent)
        if early_avg == 0:
            continue
        trend = round((recent_avg - early_avg) / early_avg * 100, 1)
        trend_results[m] = trend
        print(f"  {m}: 전반기={early_avg:.0f} 후반기={recent_avg:.0f} 추세={trend:+.1f}%")

    new_only = {m: t for m, t in trend_results.items() if m not in MARKET_ENERGY_TREND}
    print(f"\n이번 실행 에너지 추세 계산: {len(trend_results)}곳")
    print(f"그중 risk_grade_model.py의 MARKET_ENERGY_TREND에 아직 없는 신규: {len(new_only)}곳")
    print(f"반영하면 총 {len(MARKET_ENERGY_TREND) + len(new_only)}곳")
    print("\n=== risk_grade_model.py의 MARKET_ENERGY_TREND에 추가할 코드(신규만) ===")
    for m, t in new_only.items():
        print(f'    "{m}": {t},')
