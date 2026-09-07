"""
의심건물 스크리닝 리포트 (2단계) v2.0 - 불법 증축·무단 용도변경 의심 건물 우선순위화

v1.0(격차·배율 50:50)에 이어, enrich_building_age.py로 실측 확보한
건축HUB 표제부의 '사용승인일'(건물연식)을 세 번째 지표로 결합한 버전.

의심도 판단 기준 세 가지:
  - 격차(gap)  = 실제영업중수 - 등록전유부수 → 절대적 규모(관리 사각지대 크기)
  - 배율(ratio)= 실제영업중수 / 등록전유부수 → 상대적 심각도(등록 대비 몇 배나 쪼개졌는지)
  - 연식(age)  = 사용승인일 기준 건물 나이   → 노후도(오래된 건물일수록 위험이 누적됐을 가능성)

가중치는 격차 40% + 배율 30% + 연식 30%로 결합한다(v1.0의 50:50에서, 노후도를
세 번째 독립 신호로 추가). 세 지표 모두 risk_grade_model.py와 동일하게
표본 내 min-max 정규화(0~100) 후 결합한다.

★ enrich_building_age.py가 만든 verification_log_with_age.csv가 있어야
  연식 결합이 가능함. 없으면 v1.0(격차+배율 50:50)으로 자동 대체 실행.
★ 전체 스캔 건물 수·집합건축물 수 등 표본 통계는 원본 verification_log.csv
  기준 그대로 유지 (verification_log_with_age.csv는 불일치 건물만 담긴
  서브셋이라 KPI 집계에는 쓰지 않음).

필요한 파일:
  cvs/verification_log.csv           (필수, verification_scan.py 원본 로그)
  cvs/verification_log_with_age.csv  (있으면 v2.0 연식 가중 적용, 없으면 v1.0으로 대체)
"""

import pandas as pd
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def normalize(s: pd.Series) -> pd.Series:
    if s.max() == s.min():
        return pd.Series([50.0] * len(s), index=s.index)
    return (s - s.min()) / (s.max() - s.min()) * 100


def analyze():
    """
    verification_log.csv를 읽어 집합건축물 중 불일치(등록<실제) 건을 추리고,
    verification_log_with_age.csv가 있으면 건물연식을 병합해 v2.0 점수를,
    없으면 v1.0(격차+배율 50:50) 점수를 산출.
    """
    path = os.path.join(BASE_DIR, "cvs", "verification_log.csv")
    df = pd.read_csv(path, encoding="utf-8-sig")

    mismatched = df[df["비고"] == "불일치(등록<실제)"].copy()
    mismatched["등록전유부수"] = mismatched["등록전유부수"].astype(int)
    mismatched["실제영업중수"] = mismatched["실제영업중수"].astype(int)

    mismatched["격차"] = mismatched["실제영업중수"] - mismatched["등록전유부수"]
    mismatched["배율"] = (mismatched["실제영업중수"] / mismatched["등록전유부수"]).round(1)

    mismatched["격차점수"] = normalize(mismatched["격차"])
    mismatched["배율점수"] = normalize(mismatched["배율"])

    # 건물명 없는 행은 "자치구명" 같은 걸로 대체하지 않고 명시적으로 표기
    mismatched["건물명_표시"] = mismatched["건물명"].apply(
        lambda x: str(x).strip() if pd.notna(x) and str(x).strip() else "(건물명 미상)"
    )

    # 규모구분: 실제영업중수가 크면(=이미 유명한 대형 복합상가일 가능성) "대형(재점검)",
    # 작으면 "중소(신규확인)" — 점수·순위엔 영향 없는 해석용 라벨
    SCALE_THRESHOLD = 100

    def scale_label(actual):
        return "대형(재점검)" if actual >= SCALE_THRESHOLD else "중소(신규확인)"

    mismatched["규모구분"] = mismatched["실제영업중수"].apply(scale_label)

    age_path = os.path.join(BASE_DIR, "cvs", "verification_log_with_age.csv")
    has_age = os.path.exists(age_path)

    if has_age:
        age_df = pd.read_csv(age_path, encoding="utf-8-sig")
        age_df = age_df[["시군구", "상가명", "지번주소", "사용승인일", "건물연식"]].copy()
        mismatched = mismatched.merge(age_df, on=["시군구", "상가명", "지번주소"], how="left")

        n_age_missing = mismatched["건물연식"].isna().sum()
        if n_age_missing > 0:
            print(f"⚠️ {n_age_missing}건은 연식 데이터 병합 실패 — 해당 건은 연식점수 중립값(50점) 처리")
        mismatched["연식점수"] = normalize(mismatched["건물연식"].fillna(mismatched["건물연식"].median()))

        # 노후여부 라벨: 본문 배경(국토부 기준 30년)과 동일한 임계값 사용
        def age_label(age):
            if pd.isna(age):
                return "연식미상"
            return "노후(30년+)" if age >= 30 else "비노후"

        mismatched["노후여부"] = mismatched["건물연식"].apply(age_label)

        mismatched["의심도점수"] = (
            0.4 * mismatched["격차점수"] + 0.3 * mismatched["배율점수"] + 0.3 * mismatched["연식점수"]
        ).round(1)
        version = "v2.0 (격차 40% + 배율 30% + 건물연식 30%)"
    else:
        print("ℹ️ verification_log_with_age.csv가 없어 v1.0(격차+배율 50:50)으로 실행합니다.")
        print("   (enrich_building_age.py를 먼저 실행하면 건물연식이 반영된 v2.0으로 계산됩니다.)")
        mismatched["건물연식"] = None
        mismatched["노후여부"] = "연식미상"
        mismatched["의심도점수"] = (0.5 * mismatched["격차점수"] + 0.5 * mismatched["배율점수"]).round(1)
        version = "v1.0 (격차 50% + 배율 50%)"

    mismatched = mismatched.sort_values("의심도점수", ascending=False).reset_index(drop=True)

    n_total_scanned = len(df)
    n_collective = len(df[df["건물유형"] == "집합"])
    n_mismatched = len(mismatched)

    return {
        "n_total_scanned": n_total_scanned,
        "n_collective": n_collective,
        "n_mismatched": n_mismatched,
        "mismatch_rate": round(n_mismatched / n_collective * 100, 1) if n_collective else 0,
        "ranked": mismatched,
        "has_age": has_age,
        "version": version,
    }


if __name__ == "__main__":
    result = analyze()
    print(f"전체 스캔 {result['n_total_scanned']}개 / 집합건축물 {result['n_collective']}개 / "
          f"불일치 {result['n_mismatched']}개 ({result['mismatch_rate']}%)")
    print(f"산출 방식: {result['version']}")
    print()
    print("=== 의심도 점수 상위 15건 ===")
    top15 = result["ranked"].head(15)
    for _, r in top15.iterrows():
        age_txt = f"{int(r['건물연식'])}년" if pd.notna(r["건물연식"]) else "연식미상"
        print(f"[{r['의심도점수']:5.1f}점] {r['시군구']:5s} {r['건물명_표시']:15s} 연식 {age_txt:>7s} "
              f"[{r['규모구분']}/{r['노후여부']}] "
              f"등록 {r['등록전유부수']:3d} → 실제 {r['실제영업중수']:4d} "
              f"(격차 +{r['격차']}, {r['배율']}배)")


# HTML (analyze() 결과로 역산공실탐지기반_의심건물스크리닝.html 뽑음)
import json


def generate(result: dict) -> str:
    ranked = result["ranked"]
    top30 = ranked.head(30)

    rows_html = ""
    for i, r in top30.iterrows():
        rank = i + 1
        age_cell = f"{int(r['건물연식'])}년" if pd.notna(r["건물연식"]) else "-"
        scale_color = "#898781" if r["규모구분"] == "대형(재점검)" else "#2a78d6"
        age_color = "#e34948" if r["노후여부"] == "노후(30년+)" else "#898781"
        rows_html += f"""<tr>
            <td>{rank}</td>
            <td>{r['시군구']}</td>
            <td>{r['상가명']}</td>
            <td>{r['건물명_표시']}</td>
            <td>{age_cell}</td>
            <td>{r['등록전유부수']}</td>
            <td>{r['실제영업중수']}</td>
            <td style="color:#e34948;font-weight:600;">+{r['격차']}</td>
            <td style="color:#e34948;font-weight:600;">{r['배율']}배</td>
            <td><span class="score-badge">{r['의심도점수']}</span></td>
            <td style="color:{scale_color};font-weight:600;">{r['규모구분']}</td>
            <td style="color:{age_color};font-weight:600;">{r['노후여부']}</td>
        </tr>"""

    bar_labels = json.dumps([f"{r['시군구']} {r['건물명_표시']}" for _, r in top30.head(15).iterrows()], ensure_ascii=False)
    bar_values = json.dumps([r["의심도점수"] for _, r in top30.head(15).iterrows()])

    age_note = (
        "건물연식(사용승인일 기준)을 세 번째 지표로 결합했다(격차 40% + 배율 30% + 연식 30%). "
        "연식 데이터가 없는 건에는 표본 중앙값을 중립적으로 대입했다."
        if result["has_age"] else
        "건물연식 데이터는 아직 결합되지 않은 v1.0 결과다(격차 50% + 배율 50%)."
    )

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>역산공실탐지기반 — 의심건물 스크리닝 리포트 (2단계)</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #f8f8f7; color: #0b0b0b; padding: 2rem; }}
  h1 {{ font-size: 18px; font-weight: 500; margin-bottom: 4px; }}
  .subtitle {{ font-size: 12px; color: #898781; margin-bottom: 1.5rem; }}
  .scope {{ background: #eff6ff; border-left: 3px solid #2a78d6; padding: 0.875rem 1.1rem; font-size: 12px; color: #52514e; margin-bottom: 1.5rem; line-height: 1.7; }}
  .kpi-grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 1.5rem; }}
  .kpi-card {{ background: #f1f0eb; border-radius: 8px; padding: 1rem; text-align: center; }}
  .kpi-label {{ font-size: 12px; color: #898781; margin-bottom: 6px; }}
  .kpi-value {{ font-size: 24px; font-weight: 600; }}
  .chart-box {{ background: #fff; border-radius: 12px; border: 0.5px solid rgba(11,11,11,0.1); padding: 1.25rem; margin-bottom: 1.5rem; }}
  .chart-title {{ font-size: 13px; font-weight: 500; color: #52514e; margin-bottom: 12px; }}
  .chart-wrap {{ position: relative; height: 380px; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 12px; }}
  th {{ text-align: left; color: #898781; font-weight: 500; padding: 6px 8px; border-bottom: 1px solid #e8e7e2; }}
  td {{ padding: 6px 8px; border-bottom: 1px solid #f1f0eb; }}
  .score-badge {{ display: inline-block; background: #fef2f2; color: #e34948; font-weight: 700; padding: 2px 10px; border-radius: 20px; }}
  .note {{ font-size: 11px; color: #898781; margin-top: 1.5rem; line-height: 1.6; }}
</style>
</head>
<body>
<h1>역산공실탐지기반 — 의심건물 스크리닝 리포트 (2단계) — {result['version']}</h1>
<div class="subtitle">등록전유부수 대비 실제영업중수 격차·배율·건물연식 기반 우선 확인 대상 우선순위 — verification_log.csv({result['n_total_scanned']}개 건물 실측) 재활용</div>

<div class="scope" style="font-size: 13px !important; line-height: 1.6 !important;">
📍 <b>이 리포트의 특징:<br></b> "등록전유부수 &lt; 실제영업중수" 불일치는 그 자체로 불법 증축·무단 용도변경을 확정하는 증거가 아니라,<br>
<b>건축안전센터·국토안전관리원 등이 현장에서 확인해봐야 할 우선순위를 데이터로 제시</b>하는 것이다.<br> 최종 판단은 관할 행정기관의
현장 확인을 거쳐야 한다.<br> 본 리포트는 1단계(안전등급 진단)에서 이미 수집한 실측 데이터를 재사용해 산출했으며, 별도의
추가 데이터 수집 없이 즉시 생성 가능하다.
</div>

<div class="kpi-grid">
  <div class="kpi-card">
    <div class="kpi-label">전체 스캔 건물</div>
    <div class="kpi-value" style="color:#52514e;">{result['n_total_scanned']}개</div>
  </div>
  <div class="kpi-card">
    <div class="kpi-label">집합건축물</div>
    <div class="kpi-value" style="color:#2a78d6;">{result['n_collective']}개</div>
  </div>
  <div class="kpi-card">
    <div class="kpi-label">등록-실제 불일치</div>
    <div class="kpi-value" style="color:#e34948;">{result['n_mismatched']}개</div>
  </div>
  <div class="kpi-card">
    <div class="kpi-label">불일치 비율</div>
    <div class="kpi-value" style="color:#e34948;">{result['mismatch_rate']}%</div>
  </div>
</div>

<div class="chart-box">
  <div class="chart-title">의심도 점수 상위 15건 (격차·배율·연식 결합 점수)</div>
  <div class="chart-wrap"><canvas id="barChart"></canvas></div>
</div>

<div class="chart-box">
  <div class="chart-title">의심도 점수 상위 30건 상세 — 확인 우선순위 리스트</div>
  <table>
    <thead><tr><th>순위</th><th>시군구</th><th>상가명(기준)</th><th>건물명</th><th>건물연식</th><th>등록전유부</th><th>실제영업중</th><th>격차</th><th>배율</th><th>의심도점수</th><th>규모구분</th><th>노후여부</th></tr></thead>
    <tbody>{rows_html}</tbody>
  </table>
</div>

<div class="note">
※ 방법론: verification_log.csv에서 "등록전유부수 &lt; 실제영업중수" 불일치가 확인된 {result['n_mismatched']}개 건물을 대상으로,<br>
격차(실제영업중수 − 등록전유부수)·배율(실제영업중수 ÷ 등록전유부수)·{age_note}<br>
모두 표본 내 min-max 정규화(0~100) 후 결합했다.<br>
"규모구분"·"노후여부"는 의심도점수 계산에는 영향을 주지 않는 해석용 라벨이다. 실제영업중수 100개 이상은 "대형(재점검)"으로,
이미 다중이용시설 등 별도 안전관리를 받고 있을 가능성이 높아 신규 사각지대 발굴보다 기존 관리 현황 재점검 대상으로 활용을 권장한다.
100개 미만 "중소(신규확인)"이면서 "노후(30년+)"까지 겹치는 건은 새로운 관리 사각지대일 가능성이 상대적으로 높아 현장 확인 우선순위로 권장한다.<br>
데이터: 소상공인시장진흥공단 상가(상권)정보 API, 국토교통부 건축HUB 건축물대장정보 API(2026년 실측).
</div>

<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.js"></script>
<script>
new Chart(document.getElementById('barChart'), {{
  type: 'bar',
  data: {{
    labels: {bar_labels},
    datasets: [{{ data: {bar_values}, backgroundColor: '#e34948', borderRadius: 3 }}]
  }},
  options: {{
    indexAxis: 'y',
    responsive: true, maintainAspectRatio: false,
    plugins: {{ legend: {{ display: false }} }},
    scales: {{
      x: {{ grid: {{ color: '#e1e0d9' }}, min: 0, max: 100 }},
      y: {{ grid: {{ display: false }}, ticks: {{ font: {{ size: 10 }} }} }}
    }}
  }}
}});
</script>
</body>
</html>"""


if __name__ == "__main__":
    result = analyze()
    html = generate(result)
    os.makedirs(os.path.join(BASE_DIR, "html"), exist_ok=True)
    output_path = os.path.join(BASE_DIR, "html", "역산공실탐지기반_의심건물스크리닝.html")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"\nHTML 생성 완료: {output_path}")