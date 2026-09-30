"""
market_energy_matching_by_coords.py

market_energy_matching.py의 건물명 문자열 매칭 방식(구 안에서 상권명이 건물명과
유일하게 겹칠 때만 채택)은 안전하지만 좁다 - 277곳 중 33곳뿐. 2026-09-07에
geocode_missing_markets.py로 171개 상권에 위경도를 확보해뒀으니, 이번엔 "건물명이
아니라 좌표 근접"으로 전력사용량을 매칭하는 두 번째 경로를 시도한다.

방법:
  1. 서울 25개구 상가정보 API(storeListInDong)를 스캔한다 - 응답에 lon/lat와
     rdnmCd+bldMnno+bldSlno(전기/가스 데이터와 동일한 도로명주소 코드)가 같이
     들어있다는 걸 이번에 확인했다.
  2. MARKET_COORDS의 각 상권 좌표에서 반경 RADIUS_M(기본 150m) 이내에 있는
     상가 레코드를 찾는다.
  3. 그 안에서 서로 다른 건물(도로명코드+본번+부번 기준)이 "정확히 1개"일 때만
     채택한다 - 여러 건물이 반경 안에 섞이면 어느 게 그 상권 소속인지 알 수
     없으므로 틀린 매칭보다 매칭 안 되는 쪽을 택한다. market_energy_matching.py의
     안전 원칙("구 안 이름 유일")을 "반경 안 건물 유일"로 바꿔 그대로 적용한 것.
  4. market_energy_matching.py(건물명 매칭)로 이미 확보된 상권은 건드리지 않는다
     - 그쪽이 상권명 자체로 특정한 것이라 좌표 근접보다 더 신뢰도가 높다.

★ 좌표 자체가 근사치(수작업 48곳 + OSM 지오코딩 123곳, 지오코딩 쪽은 "이 이름으로
  등록된 가장 가까운 지점")라 이 방식은 이미 근사인 좌표에 또 반경으로 근사를
  더하는 이중 근사 매칭이다. 반경을 넓히면 매칭 수는 늘지만 오매칭 위험도 같이
  커진다 - 150m는 큰 상권 부지 하나 정도 크기로 잡은 보수적인 값. 결과는 병합
  전에 반드시 좌표-주소 대조로 육안 검증할 것(이전에 이름 매칭에서 "화곡중앙시장"
  ="신월중앙시장" 같은 오매칭이 실제로 나온 적 있음).

★ 2026-09-23: 1차 시도(반경 안 건물 유일)는 138곳 중 1곳만 성공했다 - 시장은
  애초에 건물이 몰려 있는 곳이라 "반경 안 유일"이 거의 안 나오기 때문. 그래서
  match_by_radius_and_name()을 추가했다: 반경 안에 건물이 여러 개 있어도 그중
  건물명이 상권 코어명과 겹치는 게 "정확히 1개"면 채택한다. 좌표(근접)와
  이름(부분일치) 두 신호를 AND로 요구하므로, 반경 조건 자체는 완화됐지만
  어느 한쪽 신호만 보는 것보다 오히려 더 안전하다(둘 다 맞아야 통과).

돌리는 법:
  python market_energy_matching_by_coords.py
  (25개구 전수 스캔이라 몇 분 걸림)
  출력: 매칭 성공 상권 목록 + risk_grade_model.py MARKET_ENERGY_TREND에
        추가할 수 있는 코드 스니펫 (그대로 붙여넣지 말고 검증 후 반영)
"""
import math
import os
import time

import requests
from dotenv import load_dotenv

from energy_vacancy_indicator import load_energy_usage
from market_energy_matching import core_name
from risk_grade_model import MARKET_ENERGY_TREND
from safety_map import MARKET_COORDS
from seoul_districts import SEOUL_GU_CODES

load_dotenv()

SERVICE_KEY_SANGGA = os.environ.get("SANGGA_API_KEY", "")
SANGGA_BASE = "https://apis.data.go.kr/B553077/api/open/sdsc2"

NUM_ROWS_PER_PAGE = 1000
REQUEST_TIMEOUT = 20
MAX_RETRY = 2
RADIUS_M = 150  # 상권 좌표 기준 반경 - 큰 상권 부지 하나 정도 크기로 보수적으로 잡음


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
    """구 전체 상가업소를 totalCount까지 빠짐없이 페이지네이션 스캔 (market_energy_matching.py와 동일)."""
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


def haversine_m(lat1, lon1, lat2, lon2) -> float:
    r = 6371000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def match_by_radius(gu_stores: dict) -> dict:
    """
    gu_stores: {구명: [store, ...]}
    반환: {상권명: (road_key, 거리(m), 후보건물수, gu)} - 반경 안에 건물이 유일할 때만
    """
    already_matched = set(MARKET_ENERGY_TREND.keys())
    matched = {}
    for market, (lat, lng, gu) in MARKET_COORDS.items():
        if market in already_matched:
            continue  # 이름 매칭으로 이미 확보된 건 안 건드림 - 그쪽이 더 정밀
        if gu not in gu_stores:
            continue
        candidates = {}  # key -> 최소거리
        for s in gu_stores[gu]:
            s_lat, s_lon = s.get("lat"), s.get("lon")
            if s_lat is None or s_lon is None:
                continue
            rd, bb, bu = s.get("rdnmCd"), s.get("bldMnno"), s.get("bldSlno")
            if not rd or bb in (None, ""):
                continue
            try:
                dist = haversine_m(lat, lng, float(s_lat), float(s_lon))
            except (TypeError, ValueError):
                continue
            if dist > RADIUS_M:
                continue
            key = (rd, int(bb), int(bu) if bu not in (None, "") else 0)
            if key not in candidates or dist < candidates[key]:
                candidates[key] = dist
        if len(candidates) == 1:
            key, dist = list(candidates.items())[0]
            matched[market] = (key, round(dist, 1), 1, gu)
    return matched


def match_by_radius_and_name(gu_stores: dict, already_matched: set) -> dict:
    """
    match_by_radius()의 완화판: 반경 RADIUS_M 안에 건물이 여러 개 있어도, 그중
    건물명이 상권 코어명과 겹치는 게 "정확히 1개"면 채택한다. 시장은 원래
    반경 안에 건물이 여럿이라 "반경 안 유일"이 거의 안 나온다는 게 1차 시도에서
    확인됐다(138곳 중 1곳) - 좌표(근접)와 이름(부분일치)이라는 두 신호를 AND로
    겹치면, 반경 조건은 완화하면서도 어느 신호 하나만 볼 때보다 오히려 더
    안전하다(둘 다 맞아야 채택되므로).
    반환: {상권명: (road_key, 거리(m), 반경 안 전체 후보 건물 수, gu)}
    """
    matched = {}
    for market, (lat, lng, gu) in MARKET_COORDS.items():
        if market in already_matched:
            continue
        if gu not in gu_stores:
            continue
        core = core_name(market)
        if len(core) < 3:
            continue
        all_in_radius = set()
        name_candidates = {}  # key -> (거리, 건물명)
        for s in gu_stores[gu]:
            s_lat, s_lon = s.get("lat"), s.get("lon")
            if s_lat is None or s_lon is None:
                continue
            rd, bb, bu = s.get("rdnmCd"), s.get("bldMnno"), s.get("bldSlno")
            if not rd or bb in (None, ""):
                continue
            try:
                dist = haversine_m(lat, lng, float(s_lat), float(s_lon))
            except (TypeError, ValueError):
                continue
            if dist > RADIUS_M:
                continue
            key = (rd, int(bb), int(bu) if bu not in (None, "") else 0)
            all_in_radius.add(key)
            nm = (s.get("bldNm") or "").strip()
            if len(nm) >= 3 and (core in nm or nm in core):
                if key not in name_candidates or dist < name_candidates[key][0]:
                    name_candidates[key] = (dist, nm)
        if len(name_candidates) == 1:
            key, (dist, nm) = list(name_candidates.items())[0]
            matched[market] = (key, round(dist, 1), len(all_in_radius), gu, nm)
    return matched


if __name__ == "__main__":
    print(f"=== 1단계: 서울 25개구 전수 스캔 (반경 {RADIUS_M}m 매칭용) ===")
    gu_stores = {}
    for cd, gu in SEOUL_GU_CODES.items():
        print(f"  {gu}({cd}) 스캔 중...")
        stores = scan_gu_stores(cd)
        gu_stores[gu] = stores
        print(f"    -> {len(stores):,}건 조회")

    print(f"\n=== 2단계: 좌표 반경 {RADIUS_M}m 매칭 (반경 안 건물 유일할 때만) ===")
    matched = match_by_radius(gu_stores)
    print(f"매칭 성공: {len(matched)}곳 (이미 이름매칭으로 확보된 {len(MARKET_ENERGY_TREND)}곳은 스캔 안 함)")
    for m, (key, dist, n_cand, gu) in matched.items():
        print(f"  {m:40s} -> key={key} 거리={dist}m ({gu})")

    print(f"\n=== 2-2단계: 반경 {RADIUS_M}m + 건물명 일치 결합 매칭 (반경 안 여러 건물 허용) ===")
    already = set(MARKET_ENERGY_TREND.keys()) | set(matched.keys())
    matched_by_name = match_by_radius_and_name(gu_stores, already)
    print(f"매칭 성공: {len(matched_by_name)}곳")
    for m, (key, dist, n_total, gu, nm) in matched_by_name.items():
        print(f"  {m:40s} -> {nm} key={key} 거리={dist}m (반경 안 전체 {n_total}개 중 이름일치 1개, {gu})")
        matched[m] = (key, dist, n_total, gu)

    print("\n=== 3단계: 에너지 사용량 조인 + 추세 계산 ===")
    usage = load_energy_usage(signgu_codes=SEOUL_GU_CODES.keys())

    trend_results = {}
    for m, (key, dist, n_cand, gu) in matched.items():
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
        trend_results[m] = (trend, matched[m][1])  # (추세%, 매칭거리m)
        print(f"  {m}: 전반기={early_avg:.0f} 후반기={recent_avg:.0f} 추세={trend:+.1f}% (거리 {matched[m][1]}m)")

    print(f"\n좌표 반경 매칭으로 확보한 에너지 추세: {len(trend_results)}곳")
    print(f"기존 이름매칭 {len(MARKET_ENERGY_TREND)}곳과 합치면 최대 {len(MARKET_ENERGY_TREND) + len(trend_results)}곳")
    print("\n=== risk_grade_model.py의 MARKET_ENERGY_TREND에 추가할 후보 코드 (검증 후 반영) ===")
    for m, (t, dist) in trend_results.items():
        print(f'    "{m}": {t},  # 좌표매칭, 거리 {dist}m')
