"""
market_energy_matching.py

safety_map.py의 TARGET_MARKETS(48개 노후 대형상가/전통시장)를 상가정보 API
건물명과 안전하게 매칭해서 전력사용량 추세를 구한다. risk_grade_model.py의
MARKET_ENERGY_TREND에 넣을 수 있는 형태로 출력.

★ 2026-09-01: 8개구(강남·마포·광진·종로·중구·영등포·성동·강북)만 스캔해서
  4/48곳만 매칭 성공(risk_grade_model.py에 하드코딩됨).
★ 2026-09-02: 나머지 44곳이 있는 10개구(용산·동대문·관악·성북·도봉·노원·
  강서·동작·송파·중랑)로 확장. 어제와 같은 "안전 매칭" 원칙을 그대로 적용.

안전 매칭 원칙(중요 - 이걸 안 지키면 "평화시장/청평화시장/동평화시장" 같은
서로 다른 상권이 섞이는 사고가 남):
  1. 상권이 속한 구(MARKET_COORDS) 안에서만 건물명을 찾는다
  2. 상권명 첫 괄호 앞부분을 "코어명"으로 쓰고, 길이 3자 미만이면 매칭 시도 안 함
  3. 코어명을 포함(or 코어명에 포함)하는 길이 3자 이상 건물명이 "정확히 1개
     주소(도로명코드,본번,부번)"일 때만 채택. 여러 주소가 나오면 그냥 제외한다
     (틀린 매칭보다 매칭 안 되는 게 낫다).

돌리는 법:
  python market_energy_matching.py
  (신규 10개구 전수 스캔이라 몇 분 걸림)
  출력: 매칭 성공 상권 목록 + risk_grade_model.py MARKET_ENERGY_TREND에
        붙여넣을 수 있는 코드 스니펫
"""
import os
import re
import time

import requests
from dotenv import load_dotenv

from energy_vacancy_indicator import load_energy_usage
from safety_map import MARKET_COORDS

load_dotenv()

SERVICE_KEY_SANGGA = os.environ.get("SANGGA_API_KEY", "")
SANGGA_BASE = "https://apis.data.go.kr/B553077/api/open/sdsc2"

# 2026-09-01에 이미 스캔한 8개구(risk_grade_model.py에 결과 반영됨) - 중복 스캔 안 함
ALREADY_SCANNED_GU = {"강남구", "마포구", "광진구", "종로구", "중구", "영등포구", "성동구", "강북구"}

# 이번에 새로 스캔할 10개구 (48개 상권 중 나머지가 위치한 구)
NEW_GU_CODES = {
    "11170": "용산구", "11230": "동대문구", "11620": "관악구", "11290": "성북구",
    "11320": "도봉구", "11350": "노원구", "11500": "강서구", "11590": "동작구",
    "11710": "송파구", "11260": "중랑구",
}

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
    print(f"=== 1단계: 신규 {len(NEW_GU_CODES)}개구 전수 스캔 ===")
    gu_stores = {}
    for cd, gu in NEW_GU_CODES.items():
        print(f"  {gu}({cd}) 스캔 중...")
        stores = scan_gu_stores(cd)
        gu_stores[gu] = stores
        print(f"    -> {len(stores):,}건 조회")

    print("\n=== 2단계: 48개 상권과 안전 매칭 (구 단위 제한 + 유일 매칭만) ===")
    matched = match_markets(gu_stores)
    print(f"신규 매칭 성공: {len(matched)}곳")
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

    print(f"\n최종 신규 에너지 매칭: {len(trend_results)}곳 (기존 4곳과 합치면 {len(trend_results) + 4}곳)")
    print("\n=== risk_grade_model.py의 MARKET_ENERGY_TREND에 추가할 코드 ===")
    for m, t in trend_results.items():
        print(f'    "{m}": {t},')
