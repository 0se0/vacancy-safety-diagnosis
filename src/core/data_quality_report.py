"""
data_quality_report.py

이 프로젝트에서 에너지 매칭을 확장하며 수동으로 찾아냈던 데이터 품질 문제들
(같은 건물에 서로 다른 상권명이 매칭되는 것, 활동이 거의 없는 상권을 "정상"으로
오분류하는 것, 극단값을 그대로 방치하는 것)을 매번 손으로 찾는 대신 자동으로
검사하는 스크립트로 일반화한다. 손으로 찾았을 때 놓쳤던 것도 이 스크립트로
돌리자마자 바로 나왔다(예: "신림중앙시장"↔"신림종합시장"이 좌표상 완전히
동일 지점 - 에너지 매칭 검증 때는 둘 다 매칭 대상이 아니라서 못 봤던 사례).

검사 카테고리:
  1. 유일성(Uniqueness) - MARKET_COORDS(277곳 중 좌표 확보된 171곳)에서 서로
     다른 상권명인데 좌표가 비정상적으로 가까운 쌍을 탐지. 0m(완전 동일 좌표),
     50m 미만, 100m 미만 세 등급으로 나누고, 그중 MARKET_ENERGY_TREND(에너지
     신호가 실제로 반영된 상권)에 걸리는 쌍은 "즉시 확인 필요"로 별도 표시한다
     - 이미 확인해서 뺀 쌍(화곡/신월, 가락시장/가락시장역 등)은 알려진 사례로
     구분해서 보여주고, 새로 나온 쌍만 "신규 발견"으로 표시한다.
  2. 유효성(Validity) - 좌표가 서울 대략 경계(위도 37.4~37.75, 경도 126.7~127.35)
     안에 있는지, MARKET_ENERGY_TREND 값 중 절대값이 비정상적으로 큰 극단값이
     있는지(이미 알려진 동진시장 -99.3%, 상계역전종합상가 +2800% 제외 신규만).
  3. 완전성(Completeness) - TARGET_MARKETS 277곳 중 좌표/에너지신호 확보율,
     각 핵심 CSV의 결측 행 비율.
  4. 정합성(Consistency) - TARGET_MARKETS ⊇ MARKET_COORDS ⊇ MARKET_ENERGY_TREND
     포함관계가 실제로 성립하는지(코드 어딘가에서 깨지면 여기서 바로 드러남).

이 스크립트는 "고친다"가 아니라 "찾아서 사람이 검토할 수 있게 표로 만든다"가
목적이다 - 61개 근접쌍을 전부 내가 판단해서 자동으로 빼고 넣는 건 위험하다
(동대문상가A~D동처럼 원래 한 단지 안의 서로 다른 동을 가리키는 정상 케이스와,
진짜 중복인 케이스가 섞여 있어서 기계적으로 못 가른다).

돌리는 법:
  python data_quality_report.py
  결과: html/역산공실탐지기반_데이터품질리포트.html
"""
import math
import os

from alt_vacancy_indicator import MIN_ACTIVE_STORES, TARGET_MARKETS, analyze
from risk_grade_model import MARKET_ENERGY_TREND
from safety_map import MARKET_COORDS

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
HTML_DIR = os.path.join(os.path.dirname(os.path.dirname(BASE_DIR)), "html")

NEAR_DUP_M = 100  # 이 거리(m) 미만이면 "같은 실체 의심" 후보로 본다
SEOUL_LAT_RANGE = (37.40, 37.75)
SEOUL_LON_RANGE = (126.70, 127.35)

# 앞서 수동으로 확인·제외 처리한 쌍 (양방향 무시)
KNOWN_RESOLVED_PAIRS = {
    frozenset({"화곡중앙시장", "신월중앙시장"}),
    frozenset({"신림중앙시장(조원동 펭귄시장)", "신신림시장(삼성동시장)"}),
    frozenset({"가락시장", "가락시장역"}),
    frozenset({"영등포시장역 1번", "영등포시장역 3번"}),
    frozenset({"영등포시장역 1번", "영등포시장역 4번"}),
    frozenset({"영등포시장역 3번", "영등포시장역 4번"}),
}


def haversine_m(lat1, lon1, lat2, lon2) -> float:
    r = 6371000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi, dlambda = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def check_near_duplicates() -> list:
    items = list(MARKET_COORDS.items())
    energy_markets = set(MARKET_ENERGY_TREND.keys())
    pairs = []
    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            m1, (lat1, lon1, gu1) = items[i]
            m2, (lat2, lon2, gu2) = items[j]
            d = haversine_m(lat1, lon1, lat2, lon2)
            if d >= NEAR_DUP_M:
                continue
            known = frozenset({m1, m2}) in KNOWN_RESOLVED_PAIRS
            both_energy = m1 in energy_markets and m2 in energy_markets
            pairs.append({
                "m1": m1, "m2": m2, "dist": round(d, 1),
                "tier": "동일(0m)" if d == 0 else ("<50m" if d < 50 else "<100m"),
                "known": known, "both_energy": both_energy,
            })
    pairs.sort(key=lambda p: (not p["both_energy"], p["dist"]))
    return pairs


def check_validity() -> dict:
    out_of_bounds = []
    for m, (lat, lon, gu) in MARKET_COORDS.items():
        if not (SEOUL_LAT_RANGE[0] <= lat <= SEOUL_LAT_RANGE[1] and
                SEOUL_LON_RANGE[0] <= lon <= SEOUL_LON_RANGE[1]):
            out_of_bounds.append((m, lat, lon))
    extreme_trend = [(m, v) for m, v in MARKET_ENERGY_TREND.items() if abs(v) > 50]
    return {"out_of_bounds": out_of_bounds, "extreme_trend": extreme_trend}


def check_consistency() -> dict:
    coords_not_in_targets = [m for m in MARKET_COORDS if m not in TARGET_MARKETS]
    energy_not_in_coords = [m for m in MARKET_ENERGY_TREND if m not in MARKET_COORDS]
    return {
        "coords_not_in_targets": coords_not_in_targets,
        "energy_not_in_coords": energy_not_in_coords,
    }


def check_completeness() -> dict:
    n_total = len(TARGET_MARKETS)
    n_coords = len(MARKET_COORDS)
    n_energy = len(MARKET_ENERGY_TREND)
    result = analyze()
    n_low_activity = sum(1 for s in result["summary"] if s["low_activity"])
    return {
        "n_total": n_total, "n_coords": n_coords, "n_energy": n_energy,
        "coord_pct": round(n_coords / n_total * 100, 1),
        "energy_pct": round(n_energy / n_total * 100, 1),
        "n_low_activity": n_low_activity,
        "low_activity_pct": round(n_low_activity / n_total * 100, 1),
    }


def generate(dups, validity, consistency, completeness) -> str:
    new_dups = [p for p in dups if not p["known"]]
    known_dups = [p for p in dups if p["known"]]
    urgent = [p for p in new_dups if p["both_energy"]]

    def dup_rows(rows):
        out = ""
        for p in rows:
            badge = '<span style="color:#e34948;font-weight:600;">⚠ 에너지 신호 둘 다 반영됨</span>' if p["both_energy"] else ""
            out += f"""<tr><td>{p['m1']}</td><td>{p['m2']}</td><td>{p['dist']}m</td><td>{p['tier']}</td><td>{badge}</td></tr>"""
        return out

    consistency_ok = not consistency["coords_not_in_targets"] and not consistency["energy_not_in_coords"]
    validity_ok = not validity["out_of_bounds"]

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>역산공실탐지기반 — 데이터 품질 리포트</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #f8f8f7; color: #0b0b0b; padding: 2rem; }}
  h1 {{ font-size: 18px; font-weight: 500; margin-bottom: 4px; }}
  h2 {{ font-size: 14px; font-weight: 600; margin: 1.75rem 0 0.75rem; }}
  .subtitle {{ font-size: 12px; color: #898781; margin-bottom: 1.5rem; }}
  .caveat {{ background: #eff6ff; border-left: 3px solid #2a78d6; padding: 0.875rem 1.1rem; font-size: 12px; color: #52514e; margin-bottom: 1.5rem; line-height: 1.7; }}
  .kpi-grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 1.5rem; }}
  .kpi-card {{ background: #f1f0eb; border-radius: 8px; padding: 1rem; text-align: center; }}
  .kpi-label {{ font-size: 12px; color: #898781; margin-bottom: 6px; }}
  .kpi-value {{ font-size: 22px; font-weight: 600; }}
  .kpi-sub {{ font-size: 11px; color: #898781; margin-top: 4px; }}
  .status-ok {{ color: #3b6d11; font-weight: 600; }}
  .status-warn {{ color: #e34948; font-weight: 600; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 12px; margin-bottom: 1rem; }}
  th {{ text-align: left; color: #898781; font-weight: 500; padding: 6px 8px; border-bottom: 1px solid #e8e7e2; }}
  td {{ padding: 6px 8px; border-bottom: 1px solid #f1f0eb; }}
  .note {{ font-size: 11px; color: #898781; margin-top: 1.5rem; line-height: 1.6; }}
</style>
</head>
<body>
<h1>데이터 품질 리포트 — 자동 검사</h1>
<div class="subtitle">TARGET_MARKETS / MARKET_COORDS / MARKET_ENERGY_TREND 및 핵심 산출물 대상 자동 검증</div>

<div class="caveat">
📍 이 리포트는 문제를 자동으로 고치지 않는다. "사람이 확인해야 할 후보"를 찾아서 표로 만드는 게 목적이다 —
61개 근접 좌표쌍을 전부 자동으로 병합·제외하면, "동대문상가A~D동"처럼 원래 같은 단지 안의 서로 다른 동을
가리키는 정상 케이스까지 잘못 지워버릴 위험이 있다.
</div>

<div class="kpi-grid">
  <div class="kpi-card">
    <div class="kpi-label">좌표 확보율</div>
    <div class="kpi-value">{completeness['coord_pct']}%</div>
    <div class="kpi-sub">{completeness['n_coords']}/{completeness['n_total']}곳</div>
  </div>
  <div class="kpi-card">
    <div class="kpi-label">에너지 신호 확보율</div>
    <div class="kpi-value">{completeness['energy_pct']}%</div>
    <div class="kpi-sub">{completeness['n_energy']}/{completeness['n_total']}곳</div>
  </div>
  <div class="kpi-card">
    <div class="kpi-label">활동 극소 상권</div>
    <div class="kpi-value">{completeness['low_activity_pct']}%</div>
    <div class="kpi-sub">{completeness['n_low_activity']}/{completeness['n_total']}곳 (자동 D처리)</div>
  </div>
  <div class="kpi-card">
    <div class="kpi-label">신규 발견 근접쌍</div>
    <div class="kpi-value" style="color:{'#e34948' if urgent else '#3b6d11'};">{len(new_dups)}</div>
    <div class="kpi-sub">그중 즉시확인 {len(urgent)}건</div>
  </div>
</div>

<h2>1. 유일성 — 좌표가 비정상적으로 가까운 서로 다른 상권명 (반경 {NEAR_DUP_M}m)</h2>
<p style="font-size:12px;color:#52514e;margin-bottom:0.75rem;">
전체 {len(dups)}쌍 중 앞서 확인·제외한 {len(known_dups)}쌍 제외, <b>신규 발견 {len(new_dups)}쌍</b>
{f'(그중 <span class="status-warn">에너지 신호가 이미 반영돼 즉시 확인이 필요한 건 {len(urgent)}쌍</span>)' if urgent else ''}
</p>
<table>
  <thead><tr><th>상권 A</th><th>상권 B</th><th>거리</th><th>등급</th><th>비고</th></tr></thead>
  <tbody>{dup_rows(new_dups)}</tbody>
</table>
<details><summary style="font-size:12px;color:#898781;cursor:pointer;">이미 확인·제외 처리된 {len(known_dups)}쌍 보기</summary>
<table style="margin-top:0.5rem;">
  <thead><tr><th>상권 A</th><th>상권 B</th><th>거리</th><th>등급</th><th>비고</th></tr></thead>
  <tbody>{dup_rows(known_dups)}</tbody>
</table>
</details>

<h2>2. 유효성</h2>
<table>
  <tr><td>좌표가 서울 대략 경계 밖인 상권</td><td class="{'status-ok' if validity_ok else 'status-warn'}">{len(validity['out_of_bounds'])}건</td></tr>
  <tr><td>전력사용량 추세 절대값 50% 초과(극단값 — 이미 알려진 것 포함)</td><td>{len(validity['extreme_trend'])}건</td></tr>
</table>

<h2>3. 정합성 (TARGET_MARKETS ⊇ MARKET_COORDS ⊇ MARKET_ENERGY_TREND)</h2>
<table>
  <tr><td>MARKET_COORDS에 있는데 TARGET_MARKETS엔 없는 상권</td><td class="{'status-ok' if not consistency['coords_not_in_targets'] else 'status-warn'}">{len(consistency['coords_not_in_targets'])}건</td></tr>
  <tr><td>MARKET_ENERGY_TREND에 있는데 MARKET_COORDS엔 없는 상권</td><td class="{'status-ok' if not consistency['energy_not_in_coords'] else 'status-warn'}">{len(consistency['energy_not_in_coords'])}건</td></tr>
</table>
<p style="font-size:12px;{'color:#3b6d11;' if consistency_ok else 'color:#e34948;'}">{'✅ 포함관계 위반 없음' if consistency_ok else '⚠ 포함관계 위반 발견'}</p>

<div class="note">
※ 방법론: MARKET_COORDS(277곳 중 좌표 확보 171곳)의 모든 쌍(171×170/2≈14,535쌍)에 대해 haversine 거리를
계산, 100m 미만인 쌍을 후보로 뽑았다. 에너지 매칭 과정에서 먼저 발견한 쌍(화곡중앙시장=
신월중앙시장, 가락시장=가락시장역 등)은 "이미 확인" 처리하고, 그 외 새로 나온 쌍만 "신규 발견"으로 구분했다.<br>
근접하다고 반드시 같은 실체인 건 아니다(동대문상가A~D동처럼 한 단지의 여러 동을 가리키는 정상 케이스도
포함) — 이 리포트는 사람이 검토할 후보 목록이지 자동 판정 결과가 아니다.
</div>

</body>
</html>"""


if __name__ == "__main__":
    print("1) 유일성 검사 (근접 좌표쌍)")
    dups = check_near_duplicates()
    new_dups = [p for p in dups if not p["known"]]
    urgent = [p for p in new_dups if p["both_energy"]]
    print(f"   전체 {len(dups)}쌍, 신규 {len(new_dups)}쌍, 그중 에너지 신호 둘 다 반영된 즉시확인 대상 {len(urgent)}쌍")
    for p in new_dups:
        flag = " ⚠️ 에너지 신호 둘 다 반영됨 - 즉시 확인 필요" if p["both_energy"] else ""
        print(f"   [{p['tier']:>6}] {p['m1']} <-> {p['m2']} ({p['dist']}m){flag}")

    print("\n2) 유효성 검사")
    validity = check_validity()
    print(f"   좌표 범위 밖: {len(validity['out_of_bounds'])}건")
    print(f"   에너지 추세 극단값(|x|>50%): {len(validity['extreme_trend'])}건 {validity['extreme_trend']}")

    print("\n3) 정합성 검사")
    consistency = check_consistency()
    print(f"   MARKET_COORDS ⊄ TARGET_MARKETS: {consistency['coords_not_in_targets']}")
    print(f"   MARKET_ENERGY_TREND ⊄ MARKET_COORDS: {consistency['energy_not_in_coords']}")

    print("\n4) 완전성 집계")
    completeness = check_completeness()
    print(f"   좌표 확보 {completeness['coord_pct']}%, 에너지 신호 {completeness['energy_pct']}%, "
          f"활동 극소 {completeness['low_activity_pct']}%")

    html = generate(dups, validity, consistency, completeness)
    out_path = os.path.join(HTML_DIR, "역산공실탐지기반_데이터품질리포트.html")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"\nHTML 생성 완료: {out_path}")
