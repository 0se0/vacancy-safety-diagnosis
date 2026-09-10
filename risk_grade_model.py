"""
노후상권 안전관리 우선순위 등급 모델 (A~D)

alt_vacancy_indicator.py에서 나온 두 지표(점포수 순증감률, 최근4분기 평균폐업률)
합쳐서 상권별로 등급 매김. 세운상가 화재(2025.5.28, 114개 점포 중 40여개가
공실이었음) 보고 이런 거 미리 알 수 있으면 좋겠다 싶어서 만듦.

필요한 거: alt_vacancy_indicator.py의 analyze() 결과 그대로 받아서 씀

★ 전력사용량 추세를 세 번째 신호로 추가(2026-09-01, market_energy_matching.py로
  2026-09-02에 범위 확대) — 상가정보 API를 스캔해 얻은 실제 건물명(bldNm)을
  상권명과 매칭한 결과, 다른 상권과 이름이 겹치지 않게 "구 안에서 유일하게 매칭되는
  건물"만 안전하게 골라냄 — 틀린 매칭으로 잘못된 에너지 데이터를 붙이느니 안 붙이는
  쪽을 택함(예: "평화시장/청평화시장/동평화시장"처럼 상권명이 겹치는 경우 제외).
  1차(8개구) 4곳 + 2차(10개구) 4곳 = 8/48곳.
  ★★ 2026-09-07: alt_vacancy_indicator.py의 TARGET_MARKETS가 48 -> 277개로
  커지면서 재매칭 대상도 늘어남. 서울 25개구 전체를 다시 스캔해 27곳이 새로
  매칭됐으나, 그중 2곳("신신림시장(삼성동시장)"과 "신월중앙시장")은 각각 기존
  "신림중앙시장(조원동 펭귄시장)", "화곡중앙시장"과 정확히 같은 건물(도로명코드+
  본번+부번)에 매칭돼 있었다 — "구 안에서 유일 매칭" 검사는 상권 하나당 건물이
  여럿 걸리는 경우만 막아주지, 서로 다른 두 상권명이 같은 건물에 매칭되는 경우는
  못 잡는다. 이런 경우는 상권명 자체가 같은 실체를 가리키거나(신림 사례일 가능성)
  코어명 매칭이 우연히 같은 건물을 짚은 것(화곡/신월 사례, 서로 다른 동인데 같은
  건물에 매칭된 건 후자일 가능성이 높음)일 수 있어 판단이 갈린다 - 둘 다 원래
  수작업으로 큐레이션된 48개 쪽(신림중앙시장, 화곡중앙시장)을 남기고 기계적으로
  확장된 277개 쪽에서 온 나머지 2곳은 제외했다. 25곳만 반영해 총 8+25=33/277곳.
  나머지는 (a) 매칭됐지만 에너지 데이터 자체가 없거나(스킵됨) (b) 이름이 겹쳐
  안전 매칭 조건을 못 채운 경우다.
  MARKET_ENERGY_TREND에 없는 상권은 기존 2지표(점포수+폐업률) 방식 그대로 등급이
  매겨짐.
"""

from alt_vacancy_indicator import analyze

# 33곳만 안전하게 매칭됨(위 설명 참고). 값 = 전기사용량 전반기(2024.01~2025.01)
# 대비 후반기(2025.02~2025.12) 평균 순증감률(%). energy_vacancy_indicator.py의
# load_energy_usage()로 실측한 24개월 전력사용량에서 계산.
MARKET_ENERGY_TREND = {
    # 1차 매칭 (2026-09-01, 8개구)
    "세운상가가동": -1.0,
    "방산종합시장(방산시장)": -3.5,
    "통인시장": 21.0,
    "동대문패션타운 관광특구": 2.0,
    # 2차 매칭 (2026-09-02, 신규 10개구)
    "용산전자상가(용산역)": 1.3,
    "신림중앙시장(조원동 펭귄시장)": -12.8,
    "화곡중앙시장": -1.8,
    "사당시장": -9.0,
    # 3차 매칭 (2026-09-07, TARGET_MARKETS 277개 확장 후 25개구 재스캔,
    # 동일 건물 중복 매칭 2곳 제외)
    "강북북부시장": -8.7,
    "개봉중앙시장": -3.9,
    "노룬산시장(노룬산골목시장)": -3.9,
    "대조시장": -1.4,
    "동진시장": -99.3,  # 극단값 - 전반기 1,988kWh -> 후반기 15kWh, 거의 완전 단전 수준. 영업중단 전환 가능성
    "뚝도시장": -4.4,
    "마장축산물시장": 6.4,
    "마포농수산물시장": -0.0,
    "망원시장": -5.0,
    "모래내시장(서중시장)": -4.0,
    "봉일시장": 0.9,
    "새마을시장": 2.4,
    "숭인시장": -4.0,
    "신도봉시장": 17.3,
    "신사상가": -2.9,
    "양재시장": -14.6,
    "연서시장": -2.9,
    "영일시장": -0.9,
    "이경시장": -1.3,
    "이태원시장": -0.1,
    "인헌시장(원당종합시장)": 0.8,
    "조양시장": -2.2,
    "증산종합시장": 1.7,
    "한아름시장": -7.2,
    "관악종합시장(신원시장)": -5.0,
}


def decline_to_score(net_change_pct: float) -> float:
    """
    점포수 순증감률 -> 0~100 위험점수로 변환
    alt_vacancy_indicator.py 고위험/중위험 기준(-3%, -7%)이랑 똑같은 임계값 씀
    (안 그러면 두 모델이 서로 다른 얘기 하게 됨)

    0%(증가/유지)=0점, -3%=30점, -7%=60점, -25%(제일 심한 경우)=100점
    중간은 그냥 직선으로 보간, 범위 밖은 0이나 100으로 고정
    """
    x = net_change_pct
    points = [(0, 0), (-3, 30), (-7, 60), (-25, 100)]
    if x >= points[0][0]:
        return 0.0
    if x <= points[-1][0]:
        return 100.0
    for (x1, y1), (x2, y2) in zip(points, points[1:]):
        if x2 <= x <= x1:
            ratio = (x - x1) / (x2 - x1)
            return round(y1 + ratio * (y2 - y1), 1)
    return 100.0


def closure_to_score(recent_close_rate_avg: float) -> float:
    """
    최근4분기 평균폐업률 -> 0~100 위험점수
    0%=0점, 3%=50점, 7%(관측된 것 중 제일 높은 수준)=100점, 나머지는 직선보간
    """
    x = recent_close_rate_avg
    points = [(0, 0), (3, 50), (7, 100)]
    if x <= points[0][0]:
        return 0.0
    if x >= points[-1][0]:
        return 100.0
    for (x1, y1), (x2, y2) in zip(points, points[1:]):
        if x1 <= x <= x2:
            ratio = (x - x1) / (x2 - x1)
            return round(y1 + ratio * (y2 - y1), 1)
    return 100.0


def compute_risk_grades(result: dict, w_vacancy: float = 0.5, w_closure: float = 0.5,
                         w_vacancy_with_energy: float = 0.4, w_closure_with_energy: float = 0.4,
                         w_energy: float = 0.2):
    """
    지표 합쳐서 위험점수(0~100)랑 등급(A~D) 뽑음. MARKET_ENERGY_TREND에 있는 상권은
    전력사용량 추세까지 3개 신호(0.4:0.4:0.2)로, 없는 상권은 기존 2개 신호(0.5:0.5)로
    계산 - 표본이 8곳뿐이라 에너지 가중치를 낮게 잡음(향후 매칭 범위 넓어지면 조정).

    처음엔 4분위수로 그냥 25%씩 나눴었는데, 그러면 표본 수 상관없이 무조건
    D/C/B/A가 균등하게 나눠져서 이상했음. 그래서 절대기준(고정 임계값)으로 바꿈 -
    alt_vacancy_indicator.py랑 똑같은 -3%/-7% 기준 그대로 쓰니까 두 모델 판정이
    서로 안 어긋남. 이제 등급 개수도 실제 심각도에 따라 다르게 나옴 (강제로 4등분 안 함)

    등급 기준: 60점 이상 D(최우선점검), 40~60 C, 20~40 B, 20미만 A
    """
    summary = result['summary']

    rows = []
    for s in summary:
        decline_score = decline_to_score(s['net_change_pct'])
        closure_score = closure_to_score(s['recent_close_rate_avg'])
        energy_trend = MARKET_ENERGY_TREND.get(s['name'])

        if energy_trend is not None:
            energy_score = decline_to_score(energy_trend)  # 감소율->점수 변환 로직 재사용
            risk_score = round(
                w_vacancy_with_energy * decline_score
                + w_closure_with_energy * closure_score
                + w_energy * energy_score, 1)
        else:
            energy_score = None
            risk_score = round(w_vacancy * decline_score + w_closure * closure_score, 1)

        if risk_score >= 60:
            grade = "D"
        elif risk_score >= 40:
            grade = "C"
        elif risk_score >= 20:
            grade = "B"
        else:
            grade = "A"

        rows.append({
            "name": s['name'],
            "net_change_pct": s['net_change_pct'],
            "recent_close_rate_avg": s['recent_close_rate_avg'],
            "energy_trend_pct": energy_trend,
            "risk_score": risk_score,
            "grade": grade,
        })
    rows.sort(key=lambda r: r['risk_score'], reverse=True)
    return rows


if __name__ == "__main__":
    result = analyze()
    rows = compute_risk_grades(result)

    print("=== 노후상권 안전관리 우선순위 등급 (위험점수 내림차순) ===")
    for r in rows:
        print(f"[{r['grade']}] {r['name']:45s} 위험점수 {r['risk_score']:5.1f}  "
              f"(점포수 순증감 {r['net_change_pct']:+.1f}%, 최근폐업률 {r['recent_close_rate_avg']}%)")

    grade_counts = {}
    for r in rows:
        grade_counts[r['grade']] = grade_counts.get(r['grade'], 0) + 1
    print("\n등급별 분포:", grade_counts)


# HTML (compute_risk_grades() 결과로 역산공실탐지기반_안전등급모델.html 뽑음)
import json
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

GRADE_COLOR = {"D": "#e34948", "C": "#f59e0b", "B": "#2a78d6", "A": "#3b6d11"}
GRADE_DESC = {
    "D": "최우선 점검 대상",
    "C": "우선 점검 권고",
    "B": "정기 모니터링",
    "A": "양호",
}


def generate(rows: list) -> str:
    n_total = len(rows)
    grade_counts = {"A": 0, "B": 0, "C": 0, "D": 0}
    for r in rows:
        grade_counts[r["grade"]] += 1

    bar_labels = json.dumps([r["name"] for r in rows], ensure_ascii=False)
    bar_values = json.dumps([r["risk_score"] for r in rows])
    bar_colors = json.dumps([GRADE_COLOR[r["grade"]] for r in rows])

    n_with_energy = sum(1 for r in rows if r.get("energy_trend_pct") is not None)

    rows_html = ""
    for r in rows:
        color = GRADE_COLOR[r["grade"]]
        energy_cell = f"{r['energy_trend_pct']:+.1f}%" if r.get("energy_trend_pct") is not None else "<span style=\"color:#c8c6bf;\">-</span>"
        rows_html += f"""<tr>
            <td>{r['name']}</td>
            <td style="text-align:center;"><span class="grade-badge" style="background:{color};">{r['grade']}</span></td>
            <td>{r['risk_score']}</td>
            <td>{r['net_change_pct']:+.1f}%</td>
            <td>{r['recent_close_rate_avg']}%</td>
            <td>{energy_cell}</td>
            <td style="color:{color};font-weight:600;">{GRADE_DESC[r['grade']]}</td>
        </tr>"""

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>역산공실탐지기반 — 노후상권 안전관리 우선순위 등급 모델</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #f8f8f7; color: #0b0b0b; padding: 2rem; }}
  h1 {{ font-size: 18px; font-weight: 500; margin-bottom: 4px; }}
  .subtitle {{ font-size: 12px; color: #898781; margin-bottom: 1.5rem; }}
  .caveat {{ background: #fef2f2; border-left: 3px solid #e34948; padding: 0.875rem 1.1rem; font-size: 12px; color: #52514e; margin-bottom: 1.5rem; line-height: 1.7; }}
  .kpi-grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 1.5rem; }}
  .kpi-card {{ background: #f1f0eb; border-radius: 8px; padding: 1rem; text-align: center; }}
  .kpi-label {{ font-size: 12px; color: #898781; margin-bottom: 6px; }}
  .kpi-value {{ font-size: 26px; font-weight: 600; }}
  .kpi-sub {{ font-size: 11px; color: #898781; margin-top: 4px; }}
  .chart-box {{ background: #fff; border-radius: 12px; border: 0.5px solid rgba(11,11,11,0.1); padding: 1.25rem; margin-bottom: 1.5rem; }}
  .chart-title {{ font-size: 13px; font-weight: 500; color: #52514e; margin-bottom: 12px; }}
  .chart-wrap {{ position: relative; height: 320px; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 12px; }}
  th {{ text-align: left; color: #898781; font-weight: 500; padding: 6px 8px; border-bottom: 1px solid #e8e7e2; }}
  td {{ padding: 8px; border-bottom: 1px solid #f1f0eb; }}
  .grade-badge {{ display: inline-block; width: 24px; height: 24px; line-height: 24px; border-radius: 50%; color: #fff; font-weight: 700; font-size: 13px; }}
  .note {{ font-size: 11px; color: #898781; margin-top: 1.5rem; line-height: 1.6; }}
</style>
</head>
<body>
<h1>역산공실탐지기반 — 노후상권 안전관리 우선순위 등급 모델</h1>
<div class="subtitle">점포수 시계열 순증감률 + 최근4분기 평균폐업률 + 전력사용량 추세({n_with_energy}곳) 결합 | 노후 대형상가 {n_total}곳 실측 분석</div>

<div class="caveat">
📍 <b>이 모델의 배경:</b> 2025.5.28 을지로 세운상가 인근 화재 당시 전체 114개 점포 중 40여개가 공실 상태였다(뉴스1·연합뉴스 보도).<br>
국토교통부 통계상 전국 건축물의 44.4%, 상업용 건축물의 34.4%가 30년 이상 노후 건축물이다(2024년말 기준).<br>
공실·폐업이 심화된 노후 상권은 관리 소홀로 이어져 안전사고 위험을 높일 수 있다는 문제의식에서,<br>
검증된 지표를 결합해 지자체·소방당국이 점검 우선순위를 정하는 데 참고할 수 있는 등급을 산출한다.<br>
{n_with_energy}곳은 상가정보 API 실측 건물명과 전기 사용량 데이터를 직접 대조해 확보한 전력사용량 추세까지 세 번째
신호로 반영했다(나머지는 상권명이 서로 겹치거나 스캔 범위 밖이라 안전하게 매칭되는 건물이 없어 미반영).
</div>

<div class="kpi-grid">
  <div class="kpi-card">
    <div class="kpi-label">분석 대상 노후상권</div>
    <div class="kpi-value" style="color:#52514e;">{n_total}곳</div>
  </div>
  <div class="kpi-card">
    <div class="kpi-label">D등급 (최우선 점검)</div>
    <div class="kpi-value" style="color:{GRADE_COLOR['D']};">{grade_counts['D']}곳</div>
  </div>
  <div class="kpi-card">
    <div class="kpi-label">C등급 (우선 점검 권고)</div>
    <div class="kpi-value" style="color:{GRADE_COLOR['C']};">{grade_counts['C']}곳</div>
  </div>
  <div class="kpi-card">
    <div class="kpi-label">B+A등급 (모니터링/양호)</div>
    <div class="kpi-value" style="color:{GRADE_COLOR['B']};">{grade_counts['B']+grade_counts['A']}곳</div>
  </div>
</div>

<div class="chart-box">
  <div class="chart-title">상권별 위험점수 (등급 순)</div>
  <div class="chart-wrap"><canvas id="barChart"></canvas></div>
</div>

<div class="chart-box">
  <div class="chart-title">상세 — 등급별 산출 근거</div>
  <table>
    <thead><tr><th>상권명</th><th style="text-align:center;">등급</th><th>위험점수</th><th>점포수 순증감률</th><th>최근4분기 평균폐업률</th><th>전력사용량 추세</th><th>권고사항</th></tr></thead>
    <tbody>{rows_html}</tbody>
  </table>
</div>

<div class="note">
※ 방법론: 점포수 순증감률(감소할수록 위험)과 최근4분기 평균폐업률(높을수록 위험)을 각각 0~100으로
절대기준 점수화(decline_to_score, closure_to_score — alt_vacancy_indicator.py의 고위험/중위험 실측
임계값 -3%/-7%와 동일 기준 사용)한 뒤 결합해 위험점수를 산출. 전력사용량 추세가 확보된
{n_with_energy}곳은 점포수·폐업률·전력사용량을 0.4:0.4:0.2로, 나머지 {n_total - n_with_energy}곳은
점포수·폐업률만 0.5:0.5로 결합한다(전력 데이터는 표본이 {n_with_energy}곳뿐이라 가중치를 낮게 잡음).<br>
점포수·폐업률 두 점수는 상관계수 -0.08로 서로 거의 독립적이며, 실제 위험 발생 여부를 검증할 정답 데이터가
아직 없어 균등 가중치를 적용했다(향후 소방·안전 점검 이력과 연계해 회귀 기반 가중치로 보완 예정).<br>
표본 내 상대 순위(4분위수)가 아닌 고정 임계값(60점 이상 D, 40~60 C, 20~40 B, 20미만 A)을 사용하므로 등급 수가
4등분으로 강제되지 않고 실제 심각도 분포에 따라 달라진다.<br> 노후 대형상가 {n_total}곳 실측 분석 결과
D등급 {grade_counts['D']}곳·C등급 {grade_counts['C']}곳·B등급 {grade_counts['B']}곳·A등급 {grade_counts['A']}곳으로 분류됐다.<br>
데이터: 서울시 우리마을가게 상권분석서비스(2021~2025), 소상공인 상가정보 API + 한국전력 전기사용량 통계(2024~2025).
전력사용량 매칭 범위(현재 18개구)를 넓히면 나머지 상권에도 적용할 수 있다.
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
    rows = compute_risk_grades(result)

    print("=== 노후상권 안전관리 우선순위 등급 (위험점수 내림차순) ===")
    for r in rows:
        print(f"[{r['grade']}] {r['name']:45s} 위험점수 {r['risk_score']:5.1f}  "
              f"(점포수 순증감 {r['net_change_pct']:+.1f}%, 최근폐업률 {r['recent_close_rate_avg']}%)")

    grade_counts = {}
    for r in rows:
        grade_counts[r['grade']] = grade_counts.get(r['grade'], 0) + 1
    print("\n등급별 분포:", grade_counts)

    html = generate(rows)
    output_path = os.path.join(BASE_DIR, "html", "역산공실탐지기반_안전등급모델.html")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"\nHTML 생성 완료: {output_path}")