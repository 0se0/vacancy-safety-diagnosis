"""
공실 자동탐지 알고리즘 PoC

아래 building_registry / biz_registry는 진짜 API 응답 아니고 로직 검증하려고
접 만든 샘플 데이터. 실서비스 가면 여기에
  - 국토교통부 건축HUB 건축물대장정보 API (전체 상가 호수)
  - 소상공인시장진흥공단 상가정보 API (영업중인 상가)
실제 응답이 들어가고, 아래 매칭 로직은 그대로 재사용하면 됨

핵심 아이디어:
  건축물대장에 있는 (주소,층,호) - 상가정보에 있는 (주소,층,호)
  = 건물엔 있는데 영업중으로 등록 안 된 호수 -> 공실로 추정

이 PoC로 확인하고 싶었던 것:
  1. 주소 표기가 기관마다 다름 (도로명 축약, 층수 표기, 지하/B1 등등)
     -> 정규화 안 하면 매칭이 거의 안 됨을 재현해봄
  2. 정규화 함수 적용하면 정상적으로 매칭되는지 확인
  3. 두 목록 차집합으로 공실 후보 뽑아내는 전체 파이프라인 한번 돌려봄
"""

import re
import os
from dataclasses import dataclass

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
HTML_DIR = os.path.join(os.path.dirname(os.path.dirname(BASE_DIR)), "html")


# 1. 샘플 데이터 (실제 API 응답을 흉내낸 가상 데이터 — 표기 불일치를 의도적으로 포함)
# 건축물대장: "이 건물엔 이런 호수들이 존재한다" (전체 목록, 영업 여부와 무관)
building_registry = [
    {"raw_addr": "서울특별시 종로구 종로3가 15-2번지", "floor": "1층", "unit": "101호"},
    {"raw_addr": "서울특별시 종로구 종로3가 15-2번지", "floor": "1층", "unit": "102호"},
    {"raw_addr": "서울특별시 종로구 종로3가 15-2번지", "floor": "2층", "unit": "201호"},
    {"raw_addr": "서울 중구 을지로 120",                "floor": "지하1층", "unit": "B101호"},
    {"raw_addr": "서울 중구 을지로 120",                "floor": "2층",   "unit": "203호"},
    {"raw_addr": "서울 마포구 어울마당로 65",            "floor": "1층",   "unit": "B동 1호"},
]

# 상가정보: "이 호수엔 지금 영업 중인 사업자가 있다" (영업 중 목록만)
biz_registry = [
    {"raw_addr": "종로구 종로3가 15-2",   "floor": "1F",  "unit": "101",  "biz_name": "종로커피"},
    {"raw_addr": "중구 을지로 120번지",   "floor": "B1",  "unit": "101",  "biz_name": "을지분식"},
    {"raw_addr": "마포구 어울마당로 65",  "floor": "1",   "unit": "B동1호", "biz_name": "홍대꽃집"},
]


# 2. 주소 정규화 — 서로 다른 표기 체계를 하나의 key로 통일
def normalize_addr(raw: str) -> str:
    s = raw
    s = re.sub(r"^서울특별시\s*", "", s)
    s = re.sub(r"^서울\s*", "", s)
    s = re.sub(r"번지$", "", s)   # 말미 "번지"만 제거 (지번 숫자는 그대로 둠)
    s = re.sub(r"\s+", "", s)     # 공백 제거
    s = s.replace("-", "")        # 지번 하이픈 빼기 ("15-2" -> "152", 이렇게 해야 양쪽 표기가 같은 형태로 맞춰짐)
    return s


def normalize_floor(raw: str) -> str:
    s = raw.strip()
    s = s.replace("층", "").replace("F", "").replace("f", "")
    if "지하" in s or s.upper().startswith("B"):
        num = re.sub(r"[^0-9]", "", s) or "1"
        return f"B{num}"
    return re.sub(r"[^0-9]", "", s)


def normalize_unit(raw: str) -> str:
    s = raw.strip()
    s = re.sub(r"\s+", "", s)          # 내부 공백 제거 ("B동 1호" -> "B동1호")
    s = s.replace("호", "")
    s = re.sub(r"^[Bb](?=\d)", "", s)  # 'B101' -> '101' (층에서 이미 지하 처리했으니까 숫자 앞 B는 중복이라 뺌)
    return s.strip()


def make_key(addr: str, floor: str, unit: str) -> str:
    return f"{normalize_addr(addr)}|{normalize_floor(floor)}|{normalize_unit(unit)}"


# 3. 매칭 파이프라인
def detect_vacancies(building_list, biz_list):
    biz_keys = {make_key(b["raw_addr"], b["floor"], b["unit"]) for b in biz_list}

    matched, vacant = [], []
    for unit in building_list:
        key = make_key(unit["raw_addr"], unit["floor"], unit["unit"])
        if key in biz_keys:
            matched.append(unit)
        else:
            vacant.append(unit)
    return matched, vacant, biz_keys


def run_without_normalization():
    """정규화 없이 원문 그대로 비교하면 매칭이 거의 실패함을 보여준다."""
    biz_keys_raw = {f"{b['raw_addr']}|{b['floor']}|{b['unit']}" for b in biz_registry}
    matched = 0
    for unit in building_registry:
        raw_key = f"{unit['raw_addr']}|{unit['floor']}|{unit['unit']}"
        if raw_key in biz_keys_raw:
            matched += 1
    return matched


if __name__ == "__main__":
    print("=" * 60)
    print("[0] 정규화 없이 원문 그대로 매칭 시도")
    print("=" * 60)
    raw_matched = run_without_normalization()
    print(f"전체 {len(building_registry)}개 호수 중 원문 매칭 성공: {raw_matched}개")
    print("→ 기관별 주소·층·호수 표기 방식이 달라 정규화 없이는 매칭이 거의 불가능함을 확인.\n")

    print("=" * 60)
    print("[1] 정규화 적용 후 매칭")
    print("=" * 60)
    matched, vacant, biz_keys = detect_vacancies(building_registry, biz_registry)

    print(f"건축물대장 전체 호수: {len(building_registry)}개")
    print(f"상가정보 영업중 호수: {len(biz_registry)}개")
    print(f"매칭(영업중으로 확인): {len(matched)}개")
    print(f"공실 추정: {len(vacant)}개\n")

    print("--- 영업중으로 매칭된 호수 ---")
    for m in matched:
        print(f"  {m['raw_addr']} {m['floor']} {m['unit']}  (key={make_key(m['raw_addr'], m['floor'], m['unit'])})")

    print("\n--- 공실 추정 호수 ---")
    for v in vacant:
        print(f"  🏠 {v['raw_addr']} {v['floor']} {v['unit']}  (key={make_key(v['raw_addr'], v['floor'], v['unit'])})")

    # HTML(위 결과로 역산공실탐지기반_공실탐지_PoC.html 뽑음)
    matched_keys = {make_key(m["raw_addr"], m["floor"], m["unit"]) for m in matched}

    rows_html = ""
    for u in building_registry:
        key = make_key(u["raw_addr"], u["floor"], u["unit"])
        is_matched = key in matched_keys
        status = "매칭(영업중)" if is_matched else "공실추정"
        cls = "status-matched" if is_matched else "status-vacant"
        rows_html += f"""<tr><td>{u['raw_addr']}</td><td>{u['floor']}</td><td>{u['unit']}</td><td style="color:#898781;font-size:11px;">{key}</td><td class="{cls}">{status}</td></tr>"""

    biz_rows_html = ""
    for b in biz_registry:
        biz_rows_html += f"""<tr><td>{b['raw_addr']}</td><td>{b['floor']}</td><td>{b['unit']}</td><td>{b['biz_name']}</td></tr>"""

    html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>역산공실탐지기반 — 공실 자동탐지 알고리즘 PoC</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #f8f8f7; color: #0b0b0b; padding: 2rem; }}
  h1 {{ font-size: 18px; font-weight: 500; margin-bottom: 4px; }}
  .subtitle {{ font-size: 12px; color: #898781; margin-bottom: 1.5rem; }}
  .caveat {{ background: #fff7ed; border-left: 3px solid #f59e0b; padding: 0.75rem 1rem; font-size: 12px; color: #52514e; margin-bottom: 1.5rem; line-height: 1.6; }}
  .kpi-grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 1.5rem; }}
  .kpi-card {{ background: #f1f0eb; border-radius: 8px; padding: 1rem; text-align: center; }}
  .kpi-label {{ font-size: 12px; color: #898781; margin-bottom: 6px; }}
  .kpi-value {{ font-size: 24px; font-weight: 500; }}
  .kpi-sub {{ font-size: 11px; color: #898781; margin-top: 4px; }}
  .red {{ color: #e34948; }} .green {{ color: #3b6d11; }} .gray {{ color: #52514e; }}
  .chart-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-bottom: 1.5rem; }}
  .chart-box {{ background: #fff; border-radius: 12px; border: 0.5px solid rgba(11,11,11,0.1); padding: 1.25rem; }}
  .chart-title {{ font-size: 13px; font-weight: 500; color: #52514e; margin-bottom: 12px; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 12px; }}
  th {{ text-align: left; color: #898781; font-weight: 500; padding: 6px 8px; border-bottom: 1px solid #e8e7e2; }}
  td {{ padding: 6px 8px; border-bottom: 1px solid #f1f0eb; }}
  .status-matched {{ color: #2a78d6; font-weight: 600; }}
  .status-vacant {{ color: #e34948; font-weight: 600; }}
  .note {{ font-size: 11px; color: #898781; margin-top: 1.5rem; line-height: 1.6; }}
  .flow {{ display: flex; align-items: center; gap: 8px; font-size: 12px; color: #52514e; margin: 1rem 0; flex-wrap: wrap; }}
  .flow-box {{ background: #f1f0eb; border-radius: 6px; padding: 8px 12px; }}
  .flow-arrow {{ color: #898781; }}
</style>
</head>
<body>
<h1>역산공실탐지기반 — 공실 자동탐지 알고리즘 PoC (Proof of Concept)</h1>
<div class="subtitle">주소·층·호수 정규화 + 건축물대장×상가정보 교차매칭(차집합) 로직 검증</div>

<div class="caveat">
⚠️ <b>샘플 데이터:</b> 아래 건축물대장·상가정보 데이터는 실제 공공 API 응답이 아니라, 두 기관의 실제 표기 방식
차이(도로명 축약, 층수 표기, "지하"/"B1" 등)를 가져와 알고리즘 로직만을 검증하기 위해 직접 작성한 샘플 데이터다.
실제 서비스 단계에서는 이 자리에 국토교통부 건축HUB API, 소상공인시장진흥공단 상가정보 API의 실 데이터가 들어가고,
아래와 동일한 정규화·매칭 로직이 그대로 재사용된다.
</div>

<div class="flow">
  <div class="flow-box">건축물대장<br><b>{len(building_registry)}개 호수</b> (전체)</div>
  <div class="flow-arrow">−</div>
  <div class="flow-box">상가정보<br><b>{len(biz_registry)}개 호수</b> (영업중)</div>
  <div class="flow-arrow">=</div>
  <div class="flow-box" style="background:#fef2f2;color:#e34948;">공실 추정<br><b>{len(vacant)}개 호수</b></div>
</div>

<div class="kpi-grid">
  <div class="kpi-card">
    <div class="kpi-label">정규화 전 매칭</div>
    <div class="kpi-value red">{raw_matched}/{len(building_registry)}</div>
    <div class="kpi-sub">기관별 표기 차이로 매칭 실패</div>
  </div>
  <div class="kpi-card">
    <div class="kpi-label">정규화 후 매칭</div>
    <div class="kpi-value green">{len(matched)}/{len(building_registry)}</div>
    <div class="kpi-sub">영업중으로 정상 확인</div>
  </div>
  <div class="kpi-card">
    <div class="kpi-label">공실 추정</div>
    <div class="kpi-value gray">{len(vacant)}개</div>
    <div class="kpi-sub">건축물대장에만 존재</div>
  </div>
  <div class="kpi-card">
    <div class="kpi-label">단계</div>
    <div class="kpi-value gray">PoC</div>
    <div class="kpi-sub">로직 검증 완료 · 실데이터 적용 예정</div>
  </div>
</div>

<div class="chart-grid">
  <div class="chart-box">
    <div class="chart-title">건축물대장 전체 호수 vs 매칭 결과</div>
    <table>
      <thead><tr><th>주소</th><th>층</th><th>호</th><th>정규화 key</th><th>상태</th></tr></thead>
      <tbody>{rows_html}</tbody>
    </table>
  </div>
  <div class="chart-box">
    <div class="chart-title">상가정보 (영업중 목록)</div>
    <table>
      <thead><tr><th>주소</th><th>층</th><th>호</th><th>사업자</th></tr></thead>
      <tbody>{biz_rows_html}</tbody>
    </table>
  </div>
</div>

<div class="note">
※ 방법론: (1) 건축물대장·상가정보 각 레코드의 주소·층·호수 표기를 정규화 함수로 통일된 key로 변환
(예: "15-2번지"→"152", "지하1층"→"B1", "101호"→"101") (2) 상가정보 key 집합과 건축물대장 key를 비교해
집합 차(건축물대장 − 상가정보)를 공실 추정 결과로 산출. 정규화 없이는 표기 차이로 매칭률이 0%에 가까웠으나
정규화 적용 후 정상 매칭됨을 확인. 실제 서비스에서는 이 로직에 건축HUB API·상가정보 API의 실데이터를 연결한다.
</div>
</body>
</html>"""

    output_path = os.path.join(HTML_DIR, "역산공실탐지기반_공실탐지_PoC.html")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"\nHTML 생성 완료: {output_path}")