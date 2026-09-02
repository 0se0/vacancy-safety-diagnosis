"""
energy_vacancy_indicator.py

전기/가스 에너지 사용량으로 건물 활성도를 보는 지표.

예전에 cvs2/전기에너지, cvs2/가스에너지 데이터로 시도했다가 "주소 체계가 달라서
안 된다"고 포기했던 걸 다시 파봤더니, 이 데이터의 nadres_rd_cd(도로명코드)
+nadres_bbno(본번)+nadres_buno(부번)이 상가정보 API 응답의 rdnmCd+bldMnno+bldSlno와
완전히 동일한 표준 도로명주소 코드 포맷이라 직접 조인 가능함을 확인함(스파이크 완료,
서울 표본 20,000행 중 132건 조인 성공).

당초엔 alt_vacancy_indicator.py의 48개 상권 점포수 순증감률과 비교하려 했으나,
"상권코드"(서울시 상권분석서비스)와 상가정보 API 주소를 이어줄 상권 경계 폴리곤
데이터가 없어 상권 단위 매칭이 불가능함을 확인. 대신 verification_scan.py와 동일한
상가정보 API로 건물별 "실제 영업 중 점포수"를 직접 스캔해서, 그 건물의 전기/가스
사용량과 건물 단위로 1:1 대조한다 (상권 근사 없이 정확, 표본도 48 -> 수천 건물).

주의: 상가정보 API는 "현재 영업 중인 사업체"만 반환하므로, 완전히 공실인 건물은
이 스캔 결과에 아예 나타나지 않는다. 따라서 이 스크립트가 증명하는 것은
"점포 밀도가 높을수록 에너지 사용량도 높다"는 상관관계이며 — 이게 성립해야만
반대로 "에너지 사용량이 낮은 건물은 공실일 가능성이 높다"는 역산 논리도
타당해진다. 완전공실 건물 자체를 찾으려면 건축물대장 전체 목록 대비 상가정보
스캔 결과의 차집합을 봐야 하며, 이는 향후 과제로 남긴다.

돌리는 법:
  1. .env에 SANGGA_API_KEY 필요 (verification_scan.py와 동일 키)
  2. cvs2/전기에너지, cvs2/가스에너지 폴더에 월별 CSV 있어야 함 (연구자 로컬 전용,
     .gitignore에 걸려있어 커밋 안 됨)
  3. python energy_vacancy_indicator.py 실행 (8개구 스캔 + 24개월 x 2종 에너지
     파일 처리라 몇 분 걸림)
  4. 결과: html/역산공실탐지기반_에너지지표.html
"""
import json
import os
import time
from collections import defaultdict

import pandas as pd
import requests
from dotenv import load_dotenv
from scipy import stats

load_dotenv()

SERVICE_KEY_SANGGA = os.environ.get("SANGGA_API_KEY", "")
SANGGA_BASE = "https://apis.data.go.kr/B553077/api/open/sdsc2"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CVS2_DIR = os.path.join(BASE_DIR, "cvs2")
HTML_DIR = os.path.join(BASE_DIR, "html")

# verification_scan.py의 SCAN_SIGUNGU_CODES와 동일한 8개구 (표본 확대판)
SCAN_SIGUNGU_CODES = {
    "11680": "강남구", "11440": "마포구", "11215": "광진구", "11110": "종로구",
    "11140": "중구", "11560": "영등포구", "11200": "성동구", "11305": "강북구",
}
NUM_ROWS_PER_PAGE = 1000
MAX_PAGES_PER_GU = 5  # 구당 최대 5,000건 (8개구 총 최대 40,000건) - API 쿼터 안전마진
REQUEST_TIMEOUT = 20
MAX_RETRY = 2

ENERGY_SOURCES = [
    ("elec", "전기에너지", "전기에너지현황_", "kWh"),
    ("gas", "가스에너지", "가스에너지현황_", "㎥"),
]
ENERGY_COLS = ["crtr_ym", "signgu_cd", "nadres_rd_cd", "nadres_bbno", "nadres_buno", "use_qy"]


def safe_get(url, params):
    for attempt in range(MAX_RETRY + 1):
        try:
            return requests.get(url, params=params, timeout=REQUEST_TIMEOUT)
        except requests.exceptions.RequestException:
            if attempt < MAX_RETRY:
                time.sleep(1)
                continue
            return None


def scan_stores(signgu_cd: str) -> list:
    """구 전체 상가업소를 페이지네이션으로 스캔 (verification_scan.py의 fetch_stores 확대판)."""
    url = f"{SANGGA_BASE}/storeListInDong"
    items = []
    for page in range(1, MAX_PAGES_PER_GU + 1):
        params = {"serviceKey": SERVICE_KEY_SANGGA, "divId": "signguCd", "key": signgu_cd,
                   "numOfRows": NUM_ROWS_PER_PAGE, "pageNo": page, "type": "json"}
        resp = safe_get(url, params)
        if resp is None:
            break
        try:
            body = resp.json().get("body", {})
        except Exception:
            break
        page_items = body.get("items", [])
        if not page_items:
            break
        items.extend(page_items)
        if len(page_items) < NUM_ROWS_PER_PAGE:
            break  # 마지막 페이지
        time.sleep(0.2)
    return items


def collect_buildings() -> dict:
    """
    8개구 전체 스캔해서 건물별(도로명코드,본번,부번) -> 실제 영업중 점포수로 집계.
    반환: {(rd_cd, bbno, buno): {'store_count': int, 'gu': str, 'addr': str, 'bld_nm': str}}
    """
    buildings = defaultdict(lambda: {"store_count": 0, "gu": "", "addr": "", "bld_nm": ""})
    for signgu_cd, gu_name in SCAN_SIGUNGU_CODES.items():
        print(f"  {gu_name}({signgu_cd}) 스캔 중...")
        stores = scan_stores(signgu_cd)
        print(f"    -> {len(stores)}건 조회")
        for s in stores:
            rd_cd = s.get("rdnmCd")
            bbno = s.get("bldMnno")
            if not rd_cd or bbno in (None, ""):
                continue
            buno = s.get("bldSlno")
            buno = buno if buno not in (None, "") else 0
            try:
                key = (str(rd_cd), int(bbno), int(buno))
            except (TypeError, ValueError):
                continue
            b = buildings[key]
            b["store_count"] += 1
            b["gu"] = gu_name
            b["addr"] = s.get("rdnmAdr", "") or b["addr"]
            b["bld_nm"] = s.get("bldNm", "") or b["bld_nm"]
    return dict(buildings)


def load_energy_usage(signgu_codes=None) -> dict:
    """
    cvs2/전기에너지, cvs2/가스에너지 24개월치를 대상 구로 필터링해서
    건물별(도로명코드,본번,부번) -> {'elec': {월: 사용량}, 'gas': {월: 사용량}}로 집계.
    signgu_codes를 안 주면 기본 8개구(SCAN_SIGUNGU_CODES) 기준(기존 호출부 호환).
    market_energy_matching.py처럼 다른 구를 볼 때는 signgu_codes로 넘겨서 재사용.
    """
    target_signgu = set(signgu_codes) if signgu_codes is not None else set(SCAN_SIGUNGU_CODES.keys())
    usage = defaultdict(lambda: {"elec": {}, "gas": {}})

    for fuel, folder, prefix, unit in ENERGY_SOURCES:
        folder_path = os.path.join(CVS2_DIR, folder)
        if not os.path.isdir(folder_path):
            print(f"  ⚠️ {folder_path} 없음, {fuel} 스킵")
            continue
        files = sorted(f for f in os.listdir(folder_path) if f.startswith(prefix) and f.endswith(".csv"))
        for i, fname in enumerate(files, 1):
            path = os.path.join(folder_path, fname)
            df = pd.read_csv(path, usecols=ENERGY_COLS, dtype=str)
            df = df[df["signgu_cd"].isin(target_signgu)].copy()
            if df.empty:
                continue
            df["nadres_bbno"] = pd.to_numeric(df["nadres_bbno"], errors="coerce")
            df["nadres_buno"] = pd.to_numeric(df["nadres_buno"], errors="coerce").fillna(0)
            df["use_qy"] = pd.to_numeric(df["use_qy"], errors="coerce")
            df = df.dropna(subset=["nadres_rd_cd", "nadres_bbno", "use_qy"])
            if df.empty:
                continue
            month = df["crtr_ym"].iloc[0]
            grouped = df.groupby(["nadres_rd_cd", "nadres_bbno", "nadres_buno"])["use_qy"].sum()
            for (rd_cd, bbno, buno), qy in grouped.items():
                key = (str(rd_cd), int(bbno), int(buno))
                usage[key][fuel][month] = float(qy)
            print(f"  [{fuel}] {i}/{len(files)} {fname} -> {len(target_signgu)}개구 {len(grouped)}건 건물 집계")
    return dict(usage)


def join_and_score(buildings: dict, usage: dict) -> dict:
    """
    건물 키로 점포수 스캔 결과와 에너지 사용량을 조인.
    반환: {'matched': [...], 'match_rate': float, 'correlation': {...}}
    """
    matched = []
    for key, b in buildings.items():
        u = usage.get(key)
        if u is None:
            continue
        elec_months = u["elec"]
        gas_months = u["gas"]
        if not elec_months and not gas_months:
            continue

        elec_avg = round(sum(elec_months.values()) / len(elec_months), 1) if elec_months else None
        gas_avg = round(sum(gas_months.values()) / len(gas_months), 1) if gas_months else None

        elec_trend_pct = None
        if len(elec_months) >= 4:
            months_sorted = sorted(elec_months.keys())
            half = len(months_sorted) // 2
            early = [elec_months[m] for m in months_sorted[:half]]
            recent = [elec_months[m] for m in months_sorted[half:]]
            early_avg, recent_avg = sum(early) / len(early), sum(recent) / len(recent)
            if early_avg:
                elec_trend_pct = round((recent_avg - early_avg) / early_avg * 100, 1)

        matched.append({
            "rd_cd": key[0], "bbno": key[1], "buno": key[2],
            "gu": b["gu"], "addr": b["addr"], "bld_nm": b["bld_nm"],
            "store_count": b["store_count"],
            "elec_avg": elec_avg, "gas_avg": gas_avg, "elec_trend_pct": elec_trend_pct,
            "elec_months": len(elec_months), "gas_months": len(gas_months),
        })

    matched.sort(key=lambda m: m["store_count"], reverse=True)

    total_buildings = len(buildings)
    match_rate = round(len(matched) / total_buildings * 100, 1) if total_buildings else 0.0

    correlation = {}
    elec_pairs = [(m["store_count"], m["elec_avg"]) for m in matched if m["elec_avg"] is not None]
    if len(elec_pairs) >= 5:
        xs, ys = zip(*elec_pairs)
        pearson_r, pearson_p = stats.pearsonr(xs, ys)
        spearman_r, spearman_p = stats.spearmanr(xs, ys)
        correlation = {
            "n": len(elec_pairs),
            "pearson_r": round(pearson_r, 3), "pearson_p": pearson_p,
            "spearman_r": round(spearman_r, 3), "spearman_p": spearman_p,
        }

    return {
        "matched": matched,
        "total_buildings": total_buildings,
        "total_energy_buildings": len(usage),
        "match_rate": match_rate,
        "correlation": correlation,
    }


def _scatter_svg(pairs: list, width: int = 560, height: int = 340) -> str:
    """점포수(x) vs 전기사용량(y) 산점도. 사용량은 로그축(값 폭이 넓어서)."""
    import math
    pts = [(x, y) for x, y in pairs if y and y > 0]
    if len(pts) < 5:
        return ""
    xs = [p[0] for p in pts]
    ys = [math.log10(p[1]) for p in pts]
    xmin, xmax = min(xs), max(xs)
    ymin, ymax = min(ys), max(ys)
    xr = (xmax - xmin) or 1
    yr = (ymax - ymin) or 1
    pad = 40
    circles = []
    for x, y in zip(xs, ys):
        cx = pad + (x - xmin) / xr * (width - 2 * pad)
        cy = height - pad - (y - ymin) / yr * (height - 2 * pad)
        circles.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="3" fill="#2a78d6" opacity="0.55"/>')
    return (
        f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}">'
        f'<line x1="{pad}" y1="{height-pad}" x2="{width-pad}" y2="{height-pad}" stroke="#e1e0d9"/>'
        f'<line x1="{pad}" y1="{pad}" x2="{pad}" y2="{height-pad}" stroke="#e1e0d9"/>'
        f'<text x="{width/2}" y="{height-8}" font-size="11" fill="#898781" text-anchor="middle">건물 내 실제 영업중 점포수</text>'
        f'<text x="14" y="{height/2}" font-size="11" fill="#898781" text-anchor="middle" '
        f'transform="rotate(-90 14 {height/2})">월평균 전력사용량 (log10 kWh)</text>'
        + "".join(circles) +
        '</svg>'
    )


def generate(result: dict) -> str:
    matched = result["matched"]
    corr = result["correlation"]
    n = len(matched)

    scatter_pairs = [(m["store_count"], m["elec_avg"]) for m in matched if m["elec_avg"] is not None]
    scatter_svg = _scatter_svg(scatter_pairs)

    rows_html = ""
    for m in matched[:150]:
        elec_str = f"{m['elec_avg']:,.0f} kWh" if m["elec_avg"] is not None else "-"
        gas_str = f"{m['gas_avg']:,.0f} ㎥" if m["gas_avg"] is not None else "-"
        trend_str = f"{m['elec_trend_pct']:+.1f}%" if m["elec_trend_pct"] is not None else "-"
        trend_class = "risk-high" if (m["elec_trend_pct"] is not None and m["elec_trend_pct"] <= -20) else ""
        rows_html += f"""<tr>
            <td>{m['gu']}</td>
            <td>{m['bld_nm'] or m['addr']}</td>
            <td>{m['store_count']}</td>
            <td>{elec_str}</td>
            <td>{gas_str}</td>
            <td class="{trend_class}">{trend_str}</td>
        </tr>"""

    corr_html = ""
    if corr:
        corr_html = f"""
        <div class="kpi-card">
          <div class="kpi-label">점포수 ↔ 전력사용량 상관계수 (Pearson)</div>
          <div class="kpi-value gray">{corr['pearson_r']}</div>
          <div class="kpi-sub">p={corr['pearson_p']:.2e}, n={corr['n']}</div>
        </div>
        <div class="kpi-card">
          <div class="kpi-label">점포수 ↔ 전력사용량 상관계수 (Spearman)</div>
          <div class="kpi-value gray">{corr['spearman_r']}</div>
          <div class="kpi-sub">p={corr['spearman_p']:.2e}, n={corr['n']}</div>
        </div>"""

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>역산공실탐지기반 — 에너지 지표: 전기/가스 사용량 기반 건물 활성도 검증</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #f8f8f7; color: #0b0b0b; padding: 2rem; }}
  h1 {{ font-size: 18px; font-weight: 500; margin-bottom: 4px; }}
  .subtitle {{ font-size: 12px; color: #898781; margin-bottom: 1.5rem; }}
  .caveat {{ background: #eff6ff; border-left: 3px solid #2a78d6; padding: 0.875rem 1.1rem; font-size: 12px; color: #52514e; margin-bottom: 1.5rem; line-height: 1.7; }}
  .kpi-grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 1.5rem; }}
  .kpi-card {{ background: #f1f0eb; border-radius: 8px; padding: 1rem; text-align: center; }}
  .kpi-label {{ font-size: 12px; color: #898781; margin-bottom: 6px; }}
  .kpi-value {{ font-size: 24px; font-weight: 500; }}
  .kpi-sub {{ font-size: 11px; color: #898781; margin-top: 4px; }}
  .red {{ color: #e34948; }} .gray {{ color: #52514e; }}
  .chart-box {{ background: #fff; border-radius: 12px; border: 0.5px solid rgba(11,11,11,0.1); padding: 1.25rem; margin-bottom: 1.5rem; }}
  .chart-title {{ font-size: 13px; font-weight: 500; color: #52514e; margin-bottom: 12px; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 12px; }}
  th {{ text-align: left; color: #898781; font-weight: 500; padding: 6px 8px; border-bottom: 1px solid #e8e7e2; }}
  td {{ padding: 6px 8px; border-bottom: 1px solid #f1f0eb; }}
  .risk-high {{ color: #e34948; font-weight: 600; }}
  .note {{ font-size: 11px; color: #898781; margin-top: 1.5rem; line-height: 1.6; }}
</style>
</head>
<body>
<h1>역산공실탐지기반 — 에너지 지표: 전기/가스 사용량 기반 건물 활성도 검증</h1>
<div class="subtitle">상가정보 API 8개구 실측 스캔 × 전기/가스 사용량(2024.01~2025.12) 건물 단위 직접 조인</div>

<div class="caveat">
📍 <b>이 지표의 배경:</b> 전기/가스 데이터의 도로명코드(nadres_rd_cd)+본번+부번이 상가정보 API 응답의 rdnmCd+bldMnno+bldSlno와
동일한 표준 도로명주소 코드 포맷임을 확인해, 별도 매핑 테이블 없이 건물 단위로 직접 조인했다.<br>
상가정보 API는 "현재 영업 중인 사업체"만 반환하므로 완전공실 건물은 이 스캔에 아예 잡히지 않는다 — 그래서 이 리포트가
증명하는 것은 "점포 밀도와 에너지 사용량이 실제로 비례하는가"이며, 이 상관관계가 유의미해야만 반대로
"에너지 사용량이 비정상적으로 낮은 건물 = 공실 후보"라는 역산 논리가 성립한다.
</div>

<div class="kpi-grid">
  <div class="kpi-card">
    <div class="kpi-label">스캔 건물 수 (8개구)</div>
    <div class="kpi-value gray">{result['total_buildings']:,}</div>
    <div class="kpi-sub">상가정보 API 실측</div>
  </div>
  <div class="kpi-card">
    <div class="kpi-label">에너지 매칭 성공</div>
    <div class="kpi-value gray">{n:,}건</div>
    <div class="kpi-sub">매칭률 {result['match_rate']}%</div>
  </div>
  {corr_html}
</div>

<div class="chart-box">
  <div class="chart-title">점포수 vs 월평균 전력사용량 (건물 단위, n={len(scatter_pairs)})</div>
  {scatter_svg or '<div class="note">표본 부족으로 산점도를 그릴 수 없습니다.</div>'}
</div>

<div class="chart-box">
  <div class="chart-title">매칭 건물 상세 (점포수 많은 순, 상위 {min(150, n)}건)</div>
  <table>
    <thead><tr><th>구</th><th>건물명/주소</th><th>실제영업중 점포수</th><th>월평균 전력사용량</th><th>월평균 가스사용량</th><th>전력사용량 추세(전반기→후반기)</th></tr></thead>
    <tbody>{rows_html}</tbody>
  </table>
</div>

<div class="note">
※ 방법론: verification_scan.py와 동일한 소상공인 상가정보 API(storeListInDong)로 8개구를 구당 최대 5,000건까지
페이지네이션 스캔해 (도로명코드,본번,부번) 단위로 실제 영업중 점포수를 집계. 같은 키로 전기/가스 에너지 사용량
(2024.01~2025.12, 월별)을 조인해 건물별 월평균 사용량과 전반기 대비 후반기 사용량 추세(%)를 계산.<br>
상관계수는 scipy.stats의 Pearson(선형)·Spearman(순위) 상관을 모두 산출. 전력사용량 추세가 -20% 이하로 급감한
건물은 표에서 빨간색으로 표시(공실/폐업 전환 후보).
</div>

</body>
</html>"""


if __name__ == "__main__":
    print("=== 1단계: 상가정보 API 8개구 스캔 (건물별 실제영업중 점포수) ===")
    buildings = collect_buildings()
    print(f"\n총 {len(buildings):,}개 건물 식별 완료\n")

    print("=== 2단계: 전기/가스 에너지 사용량 로드 (8개구 필터링) ===")
    usage = load_energy_usage()
    print(f"\n에너지 데이터 매칭 가능 건물 {len(usage):,}건\n")

    print("=== 3단계: 조인 및 상관관계 분석 ===")
    result = join_and_score(buildings, usage)
    print(f"매칭 성공: {len(result['matched']):,}건 (매칭률 {result['match_rate']}%)")
    if result["correlation"]:
        c = result["correlation"]
        print(f"점포수↔전력사용량 상관계수: Pearson r={c['pearson_r']} (p={c['pearson_p']:.2e}), "
              f"Spearman r={c['spearman_r']} (p={c['spearman_p']:.2e}), n={c['n']}")
    else:
        print("⚠️ 상관관계 계산에 필요한 표본(5건)이 부족합니다.")

    html = generate(result)
    output_path = os.path.join(HTML_DIR, "역산공실탐지기반_에너지지표.html")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"\nHTML 생성 완료: {output_path}")
