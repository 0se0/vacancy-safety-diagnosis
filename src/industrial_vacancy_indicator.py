"""
노후산업단지 가동률 분석 - 산업단지로 확장 가능한지 보는 근거자료

상가에서 발견한 "등록정보랑 실제운영이 안 맞는" 패턴이 산업단지에서도
똑같이 나타나는지 궁금해서 만들어봄. 대전 안전공업 화재(2026.3.20)난
대덕구 문평동이 "대전산업단지[재생사업지구]"인데, 여기 입주업체 대비
가동업체 비율 계산해서 전국이랑 비교해봄.

필요 파일: 한국산업단지공단_전국산업단지현황통계_노후산업단지_20250930.csv
"""

import pandas as pd
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CSV_FILE = "한국산업단지공단_전국산업단지현황통계_노후산업단지_20250930.csv"

# 대전 화재난 그 산업단지
HIGHLIGHT_COMPLEX = "대전산업단지[재생사업지구]"


def analyze():
    """
    전국 노후산업단지 가동률(가동업체/입주업체*100) 다 계산하고
    대전산업단지 순위/비교 통계 뽑음
    """
    path = os.path.join(BASE_DIR, "cvs", CSV_FILE)
    df = pd.read_csv(path, encoding="cp949")

    df = df[(df["입주업체(개)"].notna()) & (df["입주업체(개)"] > 0)].copy()
    df["가동률"] = (df["가동업체(개)"] / df["입주업체(개)"] * 100).round(1)
    df["가동률_raw"] = df["가동업체(개)"] / df["입주업체(개)"] * 100  # 반올림 안 한 원본값 (정렬할 때 이거 써야 동점 문제 안 생김)
    df["미가동업체수"] = df["입주업체(개)"] - df["가동업체(개)"]
    df["단지_표시명"] = df["시도"] + " " + df["시군"] + " " + df["단지명"]

    df_sorted = df.sort_values(["가동률_raw", "단지명"], kind="mergesort")  # 가동률 낮은(위험한) 순 정렬. raw값+이름 같이 써야 동점일 때도 순위가 안 흔들림

    national_avg = round(df["가동률"].mean(), 1)
    national_median = round(df["가동률"].median(), 1)
    n_total = len(df)

    # 하이라이트 대상 찾기
    highlight_row = df[df["단지명"] == HIGHLIGHT_COMPLEX]
    highlight_info = None
    if not highlight_row.empty:
        row = highlight_row.iloc[0]
        rank = int((df_sorted["단지명"] == HIGHLIGHT_COMPLEX).values.argmax()) + 1
        highlight_info = {
            "단지명": row["단지명"],
            "시도": row["시도"],
            "시군": row["시군"],
            "입주업체": int(row["입주업체(개)"]),
            "가동업체": int(row["가동업체(개)"]),
            "미가동업체수": int(row["미가동업체수"]),
            "가동률": float(row["가동률"]),
            "전국순위(낮은순)": rank,
            "전국단지수": n_total,
        }

    # 가동률 하위 10곳 (위험도 높은 순)
    bottom10 = df_sorted.head(10)[["단지_표시명", "입주업체(개)", "가동업체(개)", "가동률"]].to_dict("records")

    return {
        "national_avg": national_avg,
        "national_median": national_median,
        "n_total": n_total,
        "highlight": highlight_info,
        "bottom10": bottom10,
        "full_df": df,  # HTML 생성용
    }


if __name__ == "__main__":
    result = analyze()
    print(f"전국 노후산업단지 {result['n_total']}곳 평균 가동률: {result['national_avg']}%  (중앙값 {result['national_median']}%)")
    print()
    if result["highlight"]:
        h = result["highlight"]
        print(f"[하이라이트] {h['시도']} {h['시군']} {h['단지명']}")
        print(f"  입주업체 {h['입주업체']}개 / 가동업체 {h['가동업체']}개 / 미가동 {h['미가동업체수']}개")
        print(f"  가동률 {h['가동률']}%  (전국 {h['전국단지수']}곳 중 낮은 순 {h['전국순위(낮은순)']}위)")
    print()
    print("=== 가동률 하위 10곳 (관리사각지대 위험 높은 순) ===")
    for r in result["bottom10"]:
        print(f"  {r['단지_표시명']:35s} 입주 {r['입주업체(개)']:5d}개 / 가동 {r['가동업체(개)']:5d}개  가동률 {r['가동률']}%")


# HTML (analyze() 결과로 역산공실탐지기반_산업단지가동률.html 뽑음)
import json

def generate(result: dict) -> str:
    h = result["highlight"]
    bottom10 = result["bottom10"]

    bar_labels = json.dumps([r["단지_표시명"] for r in bottom10] + [f"{h['시도']} {h['시군']} {h['단지명']} (하이라이트)"], ensure_ascii=False)
    bar_values = json.dumps([r["가동률"] for r in bottom10] + [h["가동률"]])
    bar_colors = json.dumps(["#898781"] * len(bottom10) + ["#e34948"])

    rows_html = ""
    for r in bottom10:
        rows_html += f"""<tr>
            <td>{r['단지_표시명']}</td>
            <td>{r['입주업체(개)']:,}</td>
            <td>{r['가동업체(개)']:,}</td>
            <td>{r['가동률']}%</td>
        </tr>"""

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>역산공실탐지기반 — 노후산업단지 가동률 분석 (확장 근거)</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #f8f8f7; color: #0b0b0b; padding: 2rem; }}
  h1 {{ font-size: 18px; font-weight: 500; margin-bottom: 4px; }}
  .subtitle {{ font-size: 12px; color: #898781; margin-bottom: 1.5rem; }}
  .caveat {{ background: #eff6ff; border-left: 3px solid #2a78d6; padding: 0.875rem 1.1rem; font-size: 12px; color: #52514e; margin-bottom: 1.5rem; line-height: 1.7; }}
  .kpi-grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin-bottom: 1.5rem; }}
  .kpi-card {{ background: #f1f0eb; border-radius: 8px; padding: 1rem; text-align: center; }}
  .kpi-label {{ font-size: 12px; color: #898781; margin-bottom: 6px; }}
  .kpi-value {{ font-size: 26px; font-weight: 600; }}
  .kpi-sub {{ font-size: 11px; color: #898781; margin-top: 4px; }}
  .highlight-box {{ background: #fef2f2; border: 1px solid #f3c9c8; border-radius: 10px; padding: 1.25rem; margin-bottom: 1.5rem; }}
  .highlight-title {{ font-size: 13px; font-weight: 600; color: #e34948; margin-bottom: 8px; }}
  .highlight-body {{ font-size: 13px; color: #52514e; line-height: 1.7; }}
  .chart-box {{ background: #fff; border-radius: 12px; border: 0.5px solid rgba(11,11,11,0.1); padding: 1.25rem; margin-bottom: 1.5rem; }}
  .chart-title {{ font-size: 13px; font-weight: 500; color: #52514e; margin-bottom: 12px; }}
  .chart-wrap {{ position: relative; height: 340px; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 12px; }}
  th {{ text-align: left; color: #898781; font-weight: 500; padding: 6px 8px; border-bottom: 1px solid #e8e7e2; }}
  td {{ padding: 8px; border-bottom: 1px solid #f1f0eb; }}
  .note {{ font-size: 11px; color: #898781; margin-top: 1.5rem; line-height: 1.6; }}
</style>
</head>
<body>
<h1>역산공실탐지기반 — 노후산업단지 가동률 분석 (확장 근거)</h1>
<div class="subtitle">한국산업단지공단 전국산업단지현황통계·노후산업단지 (2025.09.30 기준, 전국 {result['n_total']}곳)</div>

<div class="caveat">
📍 <b>이 분석의 목적:</b> 본 프로젝트가 상업시설(세운상가·낙원상가 등)에서 발견한 "등록정보-실제운영 불일치"
패턴이 산업단지 영역에서도 나타나는지 확인한다. "입주업체(공식 등록)"와 "가동업체(실제 가동)"의 비율(가동률)이
낮을수록 관리 사각지대일 가능성이 크다. 2026.3.20 대전 안전공업 화재(사망 14명)가 발생한 대덕구 문평동
일원은 실제로 "대전산업단지[재생사업지구]"에 해당하며, 이 단지의 가동률을 전국과 비교한다.
</div>

<div class="highlight-box">
  <div class="highlight-title">🔍 하이라이트 — {h['시도']} {h['시군']} {h['단지명']}</div>
  <div class="highlight-body">
    입주업체 <b>{h['입주업체']:,}개</b> 중 실제 가동업체는 <b>{h['가동업체']:,}개</b>뿐이며,
    <b>{h['미가동업체수']:,}개({round(h['미가동업체수']/h['입주업체']*100,1)}%)</b>는 등록만 되어 있을 뿐 실제로는 가동하지 않는다.
    가동률 <b>{h['가동률']}%</b>는 전국 평균({result['national_avg']}%)보다 뚜렷이 낮으며,
    전국 {h['전국단지수']}곳 중 가동률이 낮은 순으로 <b>{h['전국순위(낮은순)']}위</b>다(하위 {round(h['전국순위(낮은순)']/h['전국단지수']*100,1)}%).
    이 단지는 이미 정부에 의해 <b>"재생사업지구"</b>로 지정되어 노후·쇠퇴가 공식 인정된 곳이다.
  </div>
</div>

<div class="kpi-grid">
  <div class="kpi-card">
    <div class="kpi-label">전국 노후산업단지 평균 가동률</div>
    <div class="kpi-value" style="color:#52514e;">{result['national_avg']}%</div>
    <div class="kpi-sub">중앙값 {result['national_median']}%</div>
  </div>
  <div class="kpi-card">
    <div class="kpi-label">대전산업단지 가동률</div>
    <div class="kpi-value" style="color:#e34948;">{h['가동률']}%</div>
    <div class="kpi-sub">평균 대비 {round(h['가동률']-result['national_avg'],1)}%p</div>
  </div>
  <div class="kpi-card">
    <div class="kpi-label">전국 순위 (낮은 순)</div>
    <div class="kpi-value" style="color:#e34948;">{h['전국순위(낮은순)']}위</div>
    <div class="kpi-sub">전체 {h['전국단지수']}곳 중</div>
  </div>
</div>

<div class="chart-box">
  <div class="chart-title">가동률 최하위 10곳 + 대전산업단지 비교</div>
  <div class="chart-wrap"><canvas id="barChart"></canvas></div>
</div>

<div class="chart-box">
  <div class="chart-title">가동률 최하위 10곳 상세</div>
  <table>
    <thead><tr><th>단지명</th><th>입주업체</th><th>가동업체</th><th>가동률</th></tr></thead>
    <tbody>{rows_html}</tbody>
  </table>
</div>

<div class="note">
※ 가동률 = 가동업체(개) / 입주업체(개) × 100. 대전산업단지는 최하위 10곳에는 포함되지 않으나(최하위권은
소규모 단지 위주), 대규모 단지(입주업체 1,083개) 중에서는 관리 사각지대 규모(미가동 197개)가 절대적으로
크다는 점에서 의미가 있다. 데이터: 한국산업단지공단, 전국산업단지현황통계·노후산업단지(2025.09.30 기준).
</div>

<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.js"></script>
<script>
new Chart(document.getElementById('barChart'), {{
  type: 'bar',
  data: {{
    labels: {bar_labels},
    datasets: [{{ data: {bar_values}, backgroundColor: {bar_colors}, borderRadius: 3 }}]
  }},
  options: {{
    indexAxis: 'y',
    responsive: true, maintainAspectRatio: false,
    plugins: {{ legend: {{ display: false }}, tooltip: {{ callbacks: {{ label: ctx => ctx.parsed.x + '%' }} }} }},
    scales: {{
      x: {{ grid: {{ color: '#e1e0d9' }}, min: 0, max: 100, ticks: {{ callback: v => v + '%' }} }},
      y: {{ grid: {{ display: false }}, ticks: {{ font: {{ size: 10 }} }} }}
    }}
  }}
}});
</script>
</body>
</html>"""


if __name__ == "__main__":
    result = analyze()
    print(f"전국 노후산업단지 {result['n_total']}곳 평균 가동률: {result['national_avg']}%  (중앙값 {result['national_median']}%)")
    print()
    if result["highlight"]:
        h = result["highlight"]
        print(f"[하이라이트] {h['시도']} {h['시군']} {h['단지명']}")
        print(f"  입주업체 {h['입주업체']}개 / 가동업체 {h['가동업체']}개 / 미가동 {h['미가동업체수']}개")
        print(f"  가동률 {h['가동률']}%  (전국 {h['전국단지수']}곳 중 낮은 순 {h['전국순위(낮은순)']}위)")
    print()
    print("=== 가동률 하위 10곳 (관리사각지대 위험 높은 순) ===")
    for r in result["bottom10"]:
        print(f"  {r['단지_표시명']:35s} 입주 {r['입주업체(개)']:5d}개 / 가동 {r['가동업체(개)']:5d}개  가동률 {r['가동률']}%")

    html = generate(result)
    output_path = os.path.join(os.path.dirname(BASE_DIR), "html", "역산공실탐지기반_산업단지가동률.html")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"\nHTML 생성 완료: {output_path}")