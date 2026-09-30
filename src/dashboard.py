"""
대시보드용 CSV 분석
한국부동산원 임대동향조사 CSV 읽어서 분석결과 리턴함

필요한 파일:
  - 임대동향_지역별_공실률_2024년3분기___중대형_상가.csv
  - 임대동향_지역별_공실률_2024년3분기___소규모_상가.csv
  - 임대동향_지역별_임대료_2024년3분기___중대형_상가.csv
  - 임대동향_지역별_임대료_2024년3분기___소규모_상가.csv
"""

import pandas as pd
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

QUARTERS = [
    '2024년 3분기', '2024년 4분기',
    '2025년 1분기', '2025년 2분기', '2025년 3분기', '2025년 4분기',
    '2026년 1분기'
]
QUARTER_LABELS = ['24Q3', '24Q4', '25Q1', '25Q2', '25Q3', '25Q4', '26Q1']


def _read(filename):
    path = os.path.join(BASE_DIR, "cvs", filename)
    return pd.read_csv(path, encoding='cp949')


def _national_trend(df):
    """전국 행의 분기별 수치 리스트 반환"""
    row = df[df['지역'] == '전국'].iloc[0]
    return [float(row[q]) for q in QUARTERS]


def _region_latest(df):
    """
    시도 단위(지역 == 지역.1)의 최신 분기 수치를
    내림차순 정렬한 [(지역명, 값), ...] 반환
    """
    col = QUARTERS[-1]
    mask = (df['지역'] == df['지역.1']) & (~df['지역'].isin(['지역', '전국']))
    region_df = df[mask][['지역', col]].copy()
    region_df[col] = pd.to_numeric(region_df[col], errors='coerce')
    region_df = region_df.dropna().sort_values(col, ascending=False)
    return list(zip(region_df['지역'].tolist(), region_df[col].tolist()))


def analyze():
    """
    CSV 4개를 읽고 대시보드에 필요한 모든 수치를 딕셔너리로 반환.

    반환값 구조:
    {
        'quarter_labels': [...],          # 분기 레이블 리스트
        'vac_large_trend': [...],         # 중대형 공실률 추이
        'vac_small_trend': [...],         # 소규모 공실률 추이
        'rent_large_trend': [...],        # 중대형 임대료 추이
        'rent_small_trend': [...],        # 소규모 임대료 추이
        'region_labels': [...],           # 지역명 리스트 (내림차순)
        'region_vals': [...],             # 지역별 공실률 리스트 (내림차순)
        'region_colors': [...],           # 전국 평균 기준 색상 리스트
        'kpi': {
            'vac_large_latest': float,    # 중대형 공실률 최신값
            'vac_large_chg': float,       # 중대형 공실률 변화 (%p)
            'vac_small_latest': float,    # 소규모 공실률 최신값
            'vac_small_chg': float,       # 소규모 공실률 변화 (%p)
            'rent_large_latest': float,   # 중대형 임대료 최신값
            'rent_large_chg': float,      # 중대형 임대료 변화율 (%)
            'rent_small_latest': float,   # 소규모 임대료 최신값
            'rent_small_chg': float,      # 소규모 임대료 변화율 (%)
        }
    }
    """
    df_vac_large  = _read('임대동향_지역별_공실률_2024년3분기___중대형_상가.csv')
    df_vac_small  = _read('임대동향_지역별_공실률_2024년3분기___소규모_상가.csv')
    df_rent_large = _read('임대동향_지역별_임대료_2024년3분기___중대형_상가.csv')
    df_rent_small = _read('임대동향_지역별_임대료_2024년3분기___소규모_상가.csv')

    # 전국 추이
    vac_large_trend  = _national_trend(df_vac_large)
    vac_small_trend  = _national_trend(df_vac_small)
    rent_large_trend = _national_trend(df_rent_large)
    rent_small_trend = _national_trend(df_rent_small)

    # KPI 계산
    vac_large_latest  = vac_large_trend[-1]
    vac_large_base    = vac_large_trend[0]
    vac_small_latest  = vac_small_trend[-1]
    vac_small_base    = vac_small_trend[0]
    rent_large_latest = rent_large_trend[-1]
    rent_large_base   = rent_large_trend[0]
    rent_small_latest = rent_small_trend[-1]
    rent_small_base   = rent_small_trend[0]

    kpi = {
        'vac_large_latest':  vac_large_latest,
        'vac_large_chg':     round(vac_large_latest - vac_large_base, 1),
        'vac_small_latest':  vac_small_latest,
        'vac_small_chg':     round(vac_small_latest - vac_small_base, 1),
        'rent_large_latest': rent_large_latest,
        'rent_large_chg':    round((rent_large_latest - rent_large_base) / rent_large_base * 100, 1),
        'rent_small_latest': rent_small_latest,
        'rent_small_chg':    round((rent_small_latest - rent_small_base) / rent_small_base * 100, 1),
    }

    # 지역별 공실률 (내림차순)
    region_sorted = _region_latest(df_vac_large)
    avg = kpi['vac_large_latest']
    region_labels = [r[0] for r in region_sorted]
    region_vals   = [r[1] for r in region_sorted]
    region_colors = ['#e34948' if v > avg else '#2a78d6' for v in region_vals]

    return {
        'quarter_labels':    QUARTER_LABELS,
        'vac_large_trend':   vac_large_trend,
        'vac_small_trend':   vac_small_trend,
        'rent_large_trend':  rent_large_trend,
        'rent_small_trend':  rent_small_trend,
        'region_labels':     region_labels,
        'region_vals':       region_vals,
        'region_colors':     region_colors,
        'kpi':               kpi,
    }


# HTML (analyze() 결과로 역산공실탐지기반_대시보드.html 뽑음)
import json

def generate(data: dict) -> str:
    kpi = data['kpi']

    region_labels_js  = json.dumps(data['region_labels'],  ensure_ascii=False)
    region_vals_js    = json.dumps(data['region_vals'])
    region_colors_js  = json.dumps(data['region_colors'])
    quarter_labels_js = json.dumps(data['quarter_labels'])
    vac_large_js      = json.dumps(data['vac_large_trend'])
    vac_small_js      = json.dumps(data['vac_small_trend'])
    rent_large_js     = json.dumps(data['rent_large_trend'])
    rent_small_js     = json.dumps(data['rent_small_trend'])
    avg_vac           = kpi['vac_large_latest']

    vac_chg_str   = f"+{kpi['vac_large_chg']:.1f}%p"
    vac_s_chg_str = f"{kpi['vac_small_chg']:+.1f}%p"
    rent_l_chg   = f"{kpi['rent_large_chg']:+.1f}%"
    rent_s_chg   = f"{kpi['rent_small_chg']:+.1f}%"
    rent_s_arrow = "↓" if kpi['rent_small_chg'] < 0 else "↑"

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>역산공실탐지기반 — 공공데이터 기반 상가 공실 현황 대시보드</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #f8f8f7; color: #0b0b0b; padding: 2rem; }}
  h1 {{ font-size: 18px; font-weight: 500; margin-bottom: 1.5rem; color: #0b0b0b; }}
  .kpi-grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 2rem; }}
  .kpi-card {{ background: #f1f0eb; border-radius: 8px; padding: 1rem; text-align: center; }}
  .kpi-label {{ font-size: 13px; color: #898781; margin-bottom: 6px; }}
  .kpi-value {{ font-size: 28px; font-weight: 500; }}
  .kpi-sub {{ font-size: 12px; color: #898781; margin-top: 4px; }}
  .red {{ color: #e34948; }} .gray {{ color: #888780; }} .blue {{ color: #2a78d6; }}
  .chart-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-bottom: 2rem; }}
  .chart-box {{ background: #fff; border-radius: 12px; border: 0.5px solid rgba(11,11,11,0.1); padding: 1.25rem; }}
  .chart-title {{ font-size: 13px; font-weight: 500; color: #52514e; margin-bottom: 4px; }}
  .legend {{ display: flex; gap: 12px; margin-bottom: 8px; flex-wrap: wrap; }}
  .legend-item {{ display: flex; align-items: center; gap: 4px; font-size: 11px; color: #52514e; }}
  .legend-dot {{ width: 10px; height: 10px; border-radius: 2px; }}
  .chart-wrap {{ position: relative; height: 280px; }}
  .chart-foot {{ font-size: 11px; color: #898781; margin-top: 8px; }}
  .problem-box {{ background: #f1f0eb; padding: 1rem 1.25rem; border-left: 3px solid #e34948; margin-bottom: 8px; }}
  .problem-title {{ font-size: 13px; font-weight: 500; color: #0b0b0b; margin-bottom: 8px; }}
  .problem-body {{ font-size: 13px; color: #52514e; line-height: 1.6; }}
  .footnote {{ font-size: 11px; color: #898781; margin-bottom: 12px; }}
  .solution-bar {{ background: #eaf3de; border-radius: 8px; padding: 0.875rem 1.25rem; }}
  .solution-text {{ font-size: 13px; color: #3b6d11; font-weight: 500; }}
</style>
</head>
<body>
<h1>역산공실탐지기반 — 공공데이터 기반 전국 상가 공실·건축물 노후화 현황</h1>
<div class="kpi-grid">
  <div class="kpi-card">
    <div class="kpi-label">전국 중대형 상가 공실률</div>
    <div class="kpi-value red">{kpi['vac_large_latest']:.1f}%</div>
    <div class="kpi-sub">2026년 1분기 ↑ 2024년 3분기 대비 {vac_chg_str}</div>
  </div>
  <div class="kpi-card">
    <div class="kpi-label">전국 소규모 상가 공실률</div>
    <div class="kpi-value red">{kpi['vac_small_latest']:.1f}%</div>
    <div class="kpi-sub">2026년 1분기 ↑ 2024년 3분기 대비 {vac_s_chg_str}</div>
  </div>
  <div class="kpi-card">
    <div class="kpi-label">전국 건축물 노후 비율</div>
    <div class="kpi-value gray">44.4%</div>
    <div class="kpi-sub">준공 30년 경과 (2024년말 기준)</div>
  </div>
  <div class="kpi-card">
    <div class="kpi-label">상업용 건축물 노후 비율</div>
    <div class="kpi-value gray">34.4%</div>
    <div class="kpi-sub">준공 30년 경과 (2024년말 기준)</div>
  </div>

</div>
<div class="chart-grid">
  <div class="chart-box">
    <div class="chart-title">지역별 중대형 상가 공실률 (2026년 1분기)</div>
    <div class="legend">
      <span class="legend-item"><span class="legend-dot" style="background:#e34948;"></span>전국 평균 이상</span>
      <span class="legend-item"><span class="legend-dot" style="background:#2a78d6;"></span>전국 평균 이하</span>
    </div>
    <div class="chart-wrap">
      <canvas id="regionChart" role="img" aria-label="지역별 중대형 상가 공실률 내림차순">지역별 공실률 내림차순</canvas>
    </div>
    <div class="chart-foot">출처: 한국부동산원 상업용부동산 임대동향조사 (2026년 1분기)</div>
  </div>
  <div class="chart-box">
    <div class="chart-title">전국 노후 건축물 비율 추이 (2005~2024)</div>
    <div class="legend">
      <span class="legend-item"><span class="legend-dot" style="background:#e34948;"></span>노후 건축물 비율(30년 이상, %)</span>
    </div>
    <div class="chart-wrap">
      <canvas id="trendChart" role="img" aria-label="전국 노후 건축물 비율 추이">노후 건축물 비율 추이</canvas>
    </div>
    <div class="chart-foot">출처: 국회입법조사처 현안분석 제133호(2020), 국토교통부 「전국 건축물 현황」(각 연도) | 노후건축물은 사용 과정에서 불법 용도변경·증축 등이 이루어지며 안전에 더 취약해진다(국회입법조사처, 2020)</div>
  </div>
</div>
<div class="problem-box">
  <div class="problem-title">🔥 관리 사각지대 문제</div>
  <div class="problem-body">공실·폐업이 심화된 노후 상권은 관리 소홀로 이어져 화재 등 안전사고 위험을 높인다(세운상가 화재, 대전 안전공업 화재 등). 그러나 "어느 노후 상권이 관리 사각지대에 놓여 있는지"를 사전에 파악할 수 있는 공공 지표는 없다.</div>
</div>
<div class="footnote">※ 노후 건축물 비율(44.4%) 출처: 국토교통부 「2024년도 전국 건축물 현황」(2025.09.29)</div>
<div class="solution-bar">
  <div class="solution-text">⇄ 공공데이터 교차 분석으로 공실·노후 상권을 탐지하고, 안전관리 우선순위 등급(A~D)을 산출 → 지자체·소방당국의 점검 인력 배분 효율화</div>
</div>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.js"></script>
<script>
const gridColor = '#e1e0d9';
const labelColor = '#898781';
const avg = {avg_vac};
new Chart(document.getElementById('regionChart'), {{
  type: 'bar',
  data: {{
    labels: {region_labels_js},
    datasets: [{{ data: {region_vals_js}, backgroundColor: {region_colors_js}, borderRadius: 3, borderSkipped: false }}]
  }},
  options: {{
    responsive: true, maintainAspectRatio: false,
    plugins: {{ legend: {{ display: false }}, tooltip: {{ callbacks: {{ label: ctx => ctx.parsed.y.toFixed(1) + '%' }} }} }},
    scales: {{
      x: {{ grid: {{ color: gridColor }}, ticks: {{ color: labelColor, font: {{ size: 10 }}, autoSkip: false, maxRotation: 45 }} }},
      y: {{ grid: {{ color: gridColor }}, ticks: {{ color: labelColor, font: {{ size: 11 }}, callback: v => v + '%' }}, min: 0, max: 30 }}
    }}
  }}
}});
new Chart(document.getElementById('trendChart'), {{
  type: 'line',
  data: {{
    labels: ['2005', '2017', '2018', '2019', '2022', '2024'],
    datasets: [
      {{ label: '노후 건축물 비율(%)', data: [29.0, 36.5, 37.1, 37.8, 41.0, 44.4], borderColor: '#e34948', backgroundColor: 'rgba(227,73,72,0.07)', borderWidth: 2, pointRadius: 4, pointBackgroundColor: '#e34948', fill: true, tension: 0.3 }}
    ]
  }},
  options: {{
    responsive: true, maintainAspectRatio: false,
    plugins: {{ legend: {{ display: false }}, tooltip: {{ callbacks: {{ label: ctx => ctx.parsed.y.toFixed(1) + '%' }} }} }},
    scales: {{
      x: {{ grid: {{ color: gridColor }}, ticks: {{ color: labelColor, font: {{ size: 11 }} }}, title: {{ display: true, text: '(연도 간격이 균등하지 않음 — 실제 공표 연도만 표시)', color: labelColor, font: {{ size: 10 }} }} }},
      y: {{ grid: {{ color: gridColor }}, ticks: {{ color: '#e34948', font: {{ size: 11 }}, callback: v => v + '%' }}, min: 20, max: 50 }}
    }}
  }}
}});
</script>
</body>
</html>"""


if __name__ == '__main__':
    print('CSV 분석 중...')
    data = analyze()

    kpi = data['kpi']
    print('=== 전국 KPI ===')
    print(f"중대형 공실률: {kpi['vac_large_latest']:.1f}%  (24Q3 대비 +{kpi['vac_large_chg']:.1f}%p)")
    print(f"소규모 공실률: {kpi['vac_small_latest']:.1f}%  (24Q3 대비 {kpi['vac_small_chg']:+.1f}%p)")
    print(f"중대형 임대료: {kpi['rent_large_latest']:.1f}천원/㎡  (24Q3 대비 {kpi['rent_large_chg']:+.1f}%)")
    print(f"소규모 임대료: {kpi['rent_small_latest']:.1f}천원/㎡  (24Q3 대비 {kpi['rent_small_chg']:+.1f}%)")

    print('HTML 생성 중...')
    html = generate(data)

    output_path = os.path.join(os.path.dirname(BASE_DIR), "html", '역산공실탐지기반_대시보드.html')
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"생성 완료: {output_path}")