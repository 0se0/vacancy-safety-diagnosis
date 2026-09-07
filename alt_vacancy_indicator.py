"""
대안 알고리즘 - 노후 대형상가 점포수 시계열로 공실위험 보는 지표

verification_scan.py로 건물 실측 돌려봤는데 강변테크노마트 같은
대형 복합상가는 등록전유부수랑 실제영업중수가 아예 말이 안 될 정도로 차이남
(강변테크노마트: 등록 1건인데 실제 영업 500개...). 그래서 이런 건물은
호실 단위로 매칭하는 게 의미가 없다고 판단해서, 대신 점포수 시계열
증감(개업률/폐업률)으로 공실위험을 추정하는 쪽으로 바꿈.

필요한 파일: 서울시_상권분석서비스_점포-상권__2021년.csv ~ 2025년.csv
"""

import pandas as pd
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
YEARS = ['2021', '2022', '2023', '2024', '2025']

# 노후 대형상가/전통시장 리스트. 10개 -> 48개(수작업 큐레이션) -> 277개(2026-09-07,
# 상권분석서비스 CSV 전체에서 상권명에 "시장" 또는 "상가"가 들어간 상권 전부 + 이름은
# 안 걸리지만 기존에 이미 포함돼 있던 항목까지 합집합)로 확장.
# ★ "노후·대형"을 실제로 걸러낸 게 아니라 이름 패턴으로만 넓힌 것 — 신축/소규모
#   상가나 "(기능상실)"로 이미 표기된 폐쇄 시장도 섞여 있음. analyze()가 CSV에
#   해당 상권이 없으면 자동으로 건너뛰므로 존재하지 않는 이름을 넣어도 안전하다.
TARGET_MARKETS = [
    '가락시장',
    '가락시장역',
    '가리봉시장',
    '강남개포시장',
    '강남골목시장',
    '강남시장(강남구 강남시장)',
    '강남시장(동작구 강남시장)',
    '강북북부골목시장',
    '강북북부시장',
    '강북종합전통시장(강북종합골목시장)',
    '강서농산물도매시장',
    '개봉중앙시장',
    '개봉프라자(고척근린시장)',
    '경동광성상가(경동시장)',
    '경동시장',
    '경창시장',
    '고분다리전통시장',
    '고척골목시장상점가(그라운드 고척)',
    '고척근린시장',
    '공덕시장',
    '공릉동 도깨비시장',
    '공항시장',
    '공항시장역 1번',
    '공항시장역 3번',
    '관악신사시장',
    '관악종합시장(신원시장)',
    '관악중부시장',
    '광장시장(광장전통시장)',
    '구로시장',
    '금남시장',
    '길동복조리시장',
    '길음시장',
    '까치산시장',
    '낙원시장(낙원지하시장(대일상가))',
    '남구로시장',
    '남대문시장(자유상가)',
    '남문시장',
    '남부골목시장(남부화곡시장, 남부시장)',
    '남부종합시장',
    '남서울상가',
    '남성사계시장(남성시장)',
    '남성역골목시장',
    '노량진중앙시장',
    '노룬산시장(노룬산골목시장)',
    '논현종합시장',
    '능동로골목시장',
    '답십리 건축자재시장',
    '답십리시장',
    '답십리현대시장',
    '대림골목시장(대림시장, 양지시장)',
    '대림상가(청계상가)',
    '대림중앙시장',
    '대명여울빛거리시장(대명시장)',
    '대신시장',
    '대원종합시장',
    '대조시장',
    '도곡시장',
    '도림시장',
    '독산동 우시장',
    '돈암시장(돈암제일시장)',
    '돌곶이시장(석관황금시장)',
    '동남상가',
    '동대문문구완구거리(동대문문구완구시장)',
    '동대문상가A동',
    '동대문상가B동',
    '동대문상가C동',
    '동대문상가D동',
    '동대문종합시장(동대문종합시장 신관, 동대문종합시장D동상가)',
    '동대문패션타운 관광특구',
    '동묘시장(동묘벼룩시장)',
    '동문시장',
    '동부시장',
    '동서시장',
    '동원전통종합시장(동원시장, 동원전통시장 상점가)',
    '동진시장',
    '동평화시장',
    '둔촌역전통시장',
    '등마루시장',
    '뚝도시장',
    '마장축산물시장',
    '마전교지하쇼핑센터(구 한일상가)',
    '마천시장',
    '마천중앙시장',
    '마포농수산물시장',
    '마포시장',
    '만리시장',
    '망원시장',
    '망원월드컵시장',
    '면곡골목시장',
    '면목골목시장(면목시장)',
    '명일전통시장',
    '모래내시장(서중시장)',
    '목2동시장',
    '목동깨비시장(목3동시장)',
    '목사랑시장(목4동시장)',
    '묵1동도깨비시장',
    '미성동 도깨비시장 골목형상점가',
    '박미시장(기능상실)',
    '밤나무골시장',
    '방산종합시장(방산시장)',
    '방신전통시장',
    '방이시장',
    '방천골목시장',
    '방학동도깨비시장',
    '백련시장',
    '백운시장',
    '백학시장',
    '번동시장',
    '보광시장',
    '본동인정시장(기능상실)',
    '봉일시장',
    '봉천제일종합시장',
    '봉천중앙시장',
    '봉천현대시장',
    '비단길현대시장(현대시장)',
    '사가정시장',
    '사당시장',
    '삼구시장(로타리상가)',
    '삼성동 시장(삼성동시장)',
    '삼양골목시장(삼양시장)',
    '삼익패션타운(남대문시장)',
    '상계역전종합상가',
    '상계주공1단지(가)상가',
    '상계중앙시장',
    '상도전통시장',
    '새마을시장',
    '새석관시장',
    '서교시장',
    '서울약령시장',
    '서울중앙시장(신중앙시장)',
    '석관시장',
    '석촌시장',
    '성내전통시장',
    '성대전통시장(성대시장)',
    '성동용답상가시장',
    '세운상가가동',
    '세종마을음식문화거리(금천교시장)',
    '솔샘시장(미아6,7동골목시장)',
    '송화벽화시장(송화골목시장)',
    '수유북부골목시장',
    '수유북부시장옆',
    '수유시장옆',
    '수유재래시장',
    '수유전통시장(수유시장, 수유골목시장)',
    '수유중앙골목시장(수유중앙시장)',
    '수일시장',
    '숭례문수입상가(남대문시장)',
    '숭인시장',
    '시영2단지 무지개종합상가(중계 무지개2단지아파트상가)',
    '시영B상가(중계 그린아파트 B 상가)',
    '신곡종합시장(신월6동 골목시장)',
    '신노량진시장(기능상실)',
    '신도봉시장',
    '신동시장',
    '신림종합시장',
    '신림중앙시장(조원동 펭귄시장)',
    '신림현대종합상가',
    '신사상가',
    '신설종합시장',
    '신성시장(신성골목시장)',
    '신수시장',
    '신신림시장(삼성동시장)',
    '신영시장',
    '신원시장',
    '신월3동 골목시장',
    '신월7동 골목시장(약수시장, 우성상가)',
    '신월중앙시장',
    '신정1동 골목시장(신정제일시장)',
    '신정2동 골목시장(오목교중앙시장)',
    '신정3동 골목시장',
    '신흥시장',
    '쌍문시장(쌍문역골목시장)',
    '아현시장',
    '암사종합시장',
    '약수시장',
    '양남시장',
    '양재시민의숲역(양재동꽃시장, aT센터)',
    '양재시장',
    '역촌중앙시장',
    '연서시장',
    '영동교골목시장',
    '영동전통시장',
    '영등포시장기계공구상가',
    '영등포시장역 1번',
    '영등포시장역 3번',
    '영등포시장역 4번',
    '영등포유통상가',
    '영등포전통시장',
    '영등포청과시장(조광시장)',
    '영등포청과시장교차로',
    '영림시장',
    '영신상가(제일상가)',
    '영일시장',
    '영진시장',
    '영진시장A동',
    '영천시장',
    '영천시장입구',
    '오류2동버들시장',
    '오류시장',
    '용두시장',
    '용산용문시장',
    '용산전자상가(용산역)',
    '우리시장',
    '우림골목시장',
    '우림시장',
    '우이골목시장(우이시장)',
    '월정로시장',
    '유영시장',
    '유진상가',
    '은행나무시장',
    '응암시장(신응암시장)',
    '이경시장',
    '이문제일시장',
    '이촌종합시장',
    '이태원시장',
    '인왕시장(홍제골목형상점가)',
    '인헌시장(원당종합시장)',
    '인현시장',
    '자동차부품상가',
    '자양골목전통시장(자양골목시장)',
    '자양종합시장(기능상실)',
    '장미원골목시장',
    '장미제일시장(중화동제일시장)',
    '장안제일시장',
    '장위전통시장',
    '전곡시장',
    '전농1동주민센터(전농시장)',
    '전농로터리시장',
    '정릉시장',
    '정릉아리랑시장',
    '제일시장',
    '조양시장',
    '조원동 펭귄시장(신림중앙시장)',
    '종로신진시장',
    '중곡제일시장(중곡제일골목시장, 광성시장)',
    '중랑동부시장',
    '중랑동부시장(중랑교종합상가)',
    '중부시장(신중부시장)',
    '증산골목시장',
    '증산종합시장',
    '창동골목시장',
    '창동신창시장',
    '창신골목시장',
    '청계천공구상가',
    '청담삼익시장',
    '청량리농수산물시장',
    '청량리수산시장',
    '청량리전통시장',
    '청량리종합시장',
    '청량리청과물시장',
    '청량종합도매시장',
    '청평화시장',
    '충신시장',
    '충신시장옆',
    '태능엔터피아(태릉시장)',
    '태릉시장 특화거리',
    '테크노상가(엘리시움)',
    '통인시장',
    '평화시장(남평화시장, 제일평화시장, 신평화패션타운)',
    '평화시장(통일상가, 동화상가)',
    '포방터시장',
    '푸른터시장(기능상실)',
    '풍납시장',
    '한아름시장',
    '한양대앞상점가(한양시장, 왕십리맛골목)',
    '합정시장',
    '행당시장상점가',
    '홍릉시장',
    '홍연시장',
    '화곡본동시장',
    '화곡중앙시장',
    '화양제일골목시장',
    '황학동벼룩시장',
    '황학시장(서울중앙시장, 신중앙시장)',
    '회기시장',
    '후암시장',
    '흑석시장',
]

# 연도별 컬럼명 차이 통일 (2021~2024는 한글, 2025는 영문)
COLUMN_MAP = {
    '기준_년분기_코드': 'stdr_yyqu_cd',
    '상권_코드_명': 'trdar_cd_nm',
    '점포_수': 'stor_co',
    '개업_점포_수': 'opbiz_stor_co',
    '폐업_점포_수': 'clsbiz_stor_co',
}


def _read_year(year: str) -> pd.DataFrame:
    path = os.path.join(BASE_DIR, "cvs", f'서울시_상권분석서비스_점포-상권__{year}년.csv')
    df = pd.read_csv(path, encoding='cp949')
    df = df.rename(columns=COLUMN_MAP)
    return df[['stdr_yyqu_cd', 'trdar_cd_nm', 'stor_co', 'opbiz_stor_co', 'clsbiz_stor_co']]


def analyze():
    """
    전체 연도 CSV를 읽어 TARGET_MARKETS 각각의 분기별 점포수/개업/폐업 추이를 계산.

    반환값:
    {
        'markets': {
            상권명: {
                'quarters': [...],
                'total_stores': [...],
                'open_stores': [...],
                'close_stores': [...],
                'net_change_pct': float,   # 최초 대비 최종 분기 순증감률(%)
                'recent_close_rate_avg': float,  # 최근 4개분기 평균 폐업률(%)
            }, ...
        },
        'summary': [  # 순감소율 내림차순 정렬 (공실위험 높은 순)
            {'name': ..., 'net_change_pct': ..., 'latest_total': ..., 'risk_level': ...}, ...
        ]
    }
    """
    frames = [_read_year(y) for y in YEARS]
    full = pd.concat(frames, ignore_index=True)

    result_markets = {}
    for market in TARGET_MARKETS:
        sub = full[full['trdar_cd_nm'] == market]
        if sub.empty:
            continue
        agg = sub.groupby('stdr_yyqu_cd').agg(
            total_stores=('stor_co', 'sum'),
            open_stores=('opbiz_stor_co', 'sum'),
            close_stores=('clsbiz_stor_co', 'sum'),
        ).reset_index().sort_values('stdr_yyqu_cd')

        quarters = agg['stdr_yyqu_cd'].astype(str).tolist()
        total = agg['total_stores'].tolist()
        opened = agg['open_stores'].tolist()
        closed = agg['close_stores'].tolist()

        net_change_pct = round((total[-1] - total[0]) / total[0] * 100, 1) if total[0] else 0.0

        # 최근 4개 분기 평균 폐업률(%)
        recent_n = min(4, len(agg))
        recent_close_rate = [
            (c / t * 100) if t else 0.0
            for c, t in zip(closed[-recent_n:], total[-recent_n:])
        ]
        recent_close_rate_avg = round(sum(recent_close_rate) / len(recent_close_rate), 1) if recent_close_rate else 0.0

        result_markets[market] = {
            'quarters': quarters,
            'total_stores': total,
            'open_stores': opened,
            'close_stores': closed,
            'net_change_pct': net_change_pct,
            'recent_close_rate_avg': recent_close_rate_avg,
        }

    # 공실위험 요약 (순감소율이 클수록 위험 높음)
    summary = []
    for name, d in result_markets.items():
        if d['net_change_pct'] <= -7:
            risk = '고위험'
        elif d['net_change_pct'] <= -3:
            risk = '중위험'
        else:
            risk = '저위험'
        summary.append({
            'name': name,
            'net_change_pct': d['net_change_pct'],
            'latest_total': d['total_stores'][-1],
            'recent_close_rate_avg': d['recent_close_rate_avg'],
            'risk_level': risk,
        })
    summary.sort(key=lambda x: x['net_change_pct'])

    return {'markets': result_markets, 'summary': summary}


# HTML (analyze() 결과 받아서 역산공실탐지기반_대안알고리즘.html로 뽑음)
import json


def _sparkline_svg(values: list, width: int = 120, height: int = 28) -> str:
    """분기별 점포수 추이를 작은 라인 스파크라인 SVG로 그림.
    (이 행 안에서만 상대적인 min~max로 정규화 — 절대값 비교용이 아니라
    '언제 줄고 언제 멈췄는지' 형태만 보여주기 위한 용도)
    """
    if not values or len(values) < 2:
        return ""
    vmin, vmax = min(values), max(values)
    rng = (vmax - vmin) or 1
    n = len(values)
    pts = []
    for i, v in enumerate(values):
        x = round(i / (n - 1) * (width - 4) + 2, 1)
        y = round(height - 2 - (v - vmin) / rng * (height - 4), 1)
        pts.append(f"{x},{y}")
    points_str = " ".join(pts)
    last_x, last_y = pts[-1].split(",")
    color = "#e34948" if values[-1] < values[0] else "#3b6d11"
    return (
        f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}">'
        f'<polyline points="{points_str}" fill="none" stroke="{color}" stroke-width="1.5"/>'
        f'<circle cx="{last_x}" cy="{last_y}" r="2" fill="{color}"/>'
        f'</svg>'
    )


def generate(result: dict) -> str:
    summary = result['summary']
    markets = result['markets']

    n_total = len(summary)
    n_high = sum(1 for s in summary if s['risk_level'] == '고위험')
    avg_change = round(sum(s['net_change_pct'] for s in summary) / n_total, 1)

    # 차트용 데이터 (상권명, 순증감률) - 순증감률 오름차순(가장 위험한 것부터)
    bar_labels = json.dumps([s['name'] for s in summary], ensure_ascii=False)
    bar_values = json.dumps([s['net_change_pct'] for s in summary])
    bar_colors = json.dumps(['#e34948' if s['risk_level'] == '고위험' else '#2a78d6' for s in summary])

    # 상위 4개 위험 상권의 분기별 점포수 추이 (라인차트용)
    top4 = summary[:4]
    quarters_ref = markets[top4[0]['name']]['quarters']
    quarter_labels_js = json.dumps(quarters_ref)
    line_datasets = []
    colors = ['#e34948', '#f59e0b', '#8b5cf6', '#2a78d6']
    for i, s in enumerate(top4):
        d = markets[s['name']]
        line_datasets.append({
            'label': s['name'],
            'data': d['total_stores'],
            'color': colors[i % len(colors)],
        })
    line_datasets_js = json.dumps(line_datasets, ensure_ascii=False)

    rows_html = ""
    for s in summary:
        risk_class = {'고위험': 'risk-high', '중위험': 'risk-mid', '저위험': 'risk-low'}[s['risk_level']]
        spark = _sparkline_svg(markets[s['name']]['total_stores'])
        rows_html += f"""<tr>
            <td>{s['name']}</td>
            <td class="{risk_class}">{s['net_change_pct']:+.1f}%</td>
            <td>{s['latest_total']:,}</td>
            <td>{s['recent_close_rate_avg']}%</td>
            <td>{spark}</td>
            <td class="{risk_class}">{s['risk_level']}</td>
        </tr>"""

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>역산공실탐지기반 — 대안 알고리즘: 노후 대형상가 점포수 시계열 공실위험 지표</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #f8f8f7; color: #0b0b0b; padding: 2rem; }}
  h1 {{ font-size: 18px; font-weight: 500; margin-bottom: 4px; }}
  .subtitle {{ font-size: 12px; color: #898781; margin-bottom: 1.5rem; }}
  .caveat {{ background: #eff6ff; border-left: 3px solid #2a78d6; padding: 0.875rem 1.1rem; font-size: 12px; color: #52514e; margin-bottom: 1.5rem; line-height: 1.7; }}
  .kpi-grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin-bottom: 1.5rem; }}
  .kpi-card {{ background: #f1f0eb; border-radius: 8px; padding: 1rem; text-align: center; }}
  .kpi-label {{ font-size: 12px; color: #898781; margin-bottom: 6px; }}
  .kpi-value {{ font-size: 24px; font-weight: 500; }}
  .kpi-sub {{ font-size: 11px; color: #898781; margin-top: 4px; }}
  .red {{ color: #e34948; }} .gray {{ color: #52514e; }}
  .chart-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-bottom: 1.5rem; }}
  .chart-box {{ background: #fff; border-radius: 12px; border: 0.5px solid rgba(11,11,11,0.1); padding: 1.25rem; }}
  .chart-title {{ font-size: 13px; font-weight: 500; color: #52514e; margin-bottom: 12px; }}
  .chart-wrap {{ position: relative; height: 300px; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 12px; }}
  th {{ text-align: left; color: #898781; font-weight: 500; padding: 6px 8px; border-bottom: 1px solid #e8e7e2; }}
  td {{ padding: 6px 8px; border-bottom: 1px solid #f1f0eb; }}
  .risk-high {{ color: #e34948; font-weight: 600; }}
  .risk-mid {{ color: #d97706; font-weight: 600; }}
  .risk-low {{ color: #2a78d6; font-weight: 600; }}
  .note {{ font-size: 11px; color: #898781; margin-top: 1.5rem; line-height: 1.6; }}
</style>
</head>
<body>
<h1>역산공실탐지기반 — 대안 알고리즘: 노후 대형상가 점포수 시계열 공실위험 지표</h1>
<div class="subtitle">서울시 우리마을가게 상권분석서비스(2021~2025, 20개 분기) | 노후 대형 복합상가 {n_total}곳 실측 분석</div>

<div class="caveat">
📍 <b>이 지표의 배경:</b> 실제 공공 API(소상공인 상가정보 + 국토교통부 건축HUB 건축물대장)로 서울 25개구 870개 상업건물을 검증한 결과(붙임: verification_scan.py, 역산공실탐지기반_실측검증요약.html),<br>
세운상가·낙원상가·강변테크노마트 등 대형 상업건물 대부분에서 "등록된 전유부(법적 구분소유 단위) 수"와 "실제 영업 중인 사업체 수"가 근본적으로 불일치함을 확인했다(예: 강변테크노마트 영업중
500개 vs 등록 전유부 1건).<br>
개별 호실 단위 매칭이 구조적으로 어려운 이 건물 유형에는, 상가정보 API 자체의시계열 점포수 변화를 공실 위험의 대체 지표로 사용한다.
</div>

<div class="kpi-grid">
  <div class="kpi-card">
    <div class="kpi-label">분석 대상 노후 대형상가</div>
    <div class="kpi-value gray">{n_total}곳</div>
    <div class="kpi-sub">세운상가·낙원상가·동대문상가 등</div>
  </div>
  <div class="kpi-card">
    <div class="kpi-label">고위험(점포수 -7% 이상 감소)</div>
    <div class="kpi-value red">{n_high}곳</div>
    <div class="kpi-sub">전체의 {round(n_high/n_total*100)}%</div>
  </div>
  <div class="kpi-card">
    <div class="kpi-label">평균 점포수 순증감</div>
    <div class="kpi-value red">{avg_change:+.1f}%</div>
    <div class="kpi-sub">2021년 1분기 대비 2025년 4분기</div>
  </div>
</div>

<div class="chart-grid">
  <div class="chart-box">
    <div class="chart-title">상권별 점포수 순증감률 (2021~2025)</div>
    <div class="chart-wrap"><canvas id="barChart"></canvas></div>
  </div>
  <div class="chart-box">
    <div class="chart-title">위험도 상위 4개 상권 — 분기별 점포수 추이</div>
    <div class="chart-wrap"><canvas id="lineChart"></canvas></div>
  </div>
</div>


 <div class="chart-box" style="font-size: 13px !important;">
  <div class="note" style="margin-top:0.75rem; font-size: 12px !important; line-height: 1.6 !important;">
    ※ "20분기 추이"는 각 행별 최소~최대 범위 내 상대적 변화만 보여주는 스파크라인이다(행 간 절대비교용이 아님).<br>
    위험도는 최근4분기 폐업률이 아니라 전체 기간(2021 1분기~2025 4분기) 점포수 순증감률로 판정하므로,<br>
    하락이 과거에 집중되고 최근엔 이미 바닥까지 줄어 안정된 상권(예: 신림종합시장)은 최근폐업률이 0%여도 고위험으로 분류될 수 있다.
  </div><br><br>
  <div class="chart-title">전체 상세 — 노후 대형상가 공실위험 지표</div>
  <table>
    <thead><tr><th>상권명</th><th>점포수 순증감률</th><th>최근 점포수</th><th>최근4분기 평균폐업률</th><th>20분기 추이(2021~2025)</th><th>위험도</th></tr></thead>
    <tbody>{rows_html}</tbody>
  </table>
</div>



<div class="note">
※ 방법론: 각 상권의 분기별 총점포수(모든 업종 합산) 추이를 2021년 1분기 대비 2025년 4분기로 비교해 순증감률을 계산.<br>
 -7% 이상 감소는 고위험, -3~-7%는 중위험, 그 외 저위험으로 분류(임계값은 노후 대형상가
{n_total}곳 표본의 분포에 기반한 기준이며 향후 더 많은 상권으로 검증 시 조정 가능).<br> 최근4분기 평균폐업률은 직전
4개 분기의 (폐업점포수/총점포수) 평균. 데이터: 서울시 우리마을가게 상권분석서비스(상권-점포)
</div>

<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.js"></script>
<script>
const barLabels = {bar_labels};
const barValues = {bar_values};
const barColors = {bar_colors};

new Chart(document.getElementById('barChart'), {{
  type: 'bar',
  data: {{
    labels: barLabels,
    datasets: [{{ data: barValues, backgroundColor: barColors, borderRadius: 3 }}]
  }},
  options: {{
    indexAxis: 'y',
    responsive: true, maintainAspectRatio: false,
    plugins: {{ legend: {{ display: false }}, tooltip: {{ callbacks: {{ label: ctx => ctx.parsed.x.toFixed(1) + '%' }} }} }},
    scales: {{
      x: {{ grid: {{ color: '#e1e0d9' }}, ticks: {{ callback: v => v + '%' }} }},
      y: {{ grid: {{ display: false }}, ticks: {{ font: {{ size: 10 }} }} }}
    }}
  }}
}});

const lineDatasets = {line_datasets_js};
new Chart(document.getElementById('lineChart'), {{
  type: 'line',
  data: {{
    labels: {quarter_labels_js},
    datasets: lineDatasets.map(d => ({{
      label: d.label, data: d.data, borderColor: d.color, backgroundColor: 'transparent',
      borderWidth: 2, pointRadius: 2, tension: 0.2
    }}))
  }},
  options: {{
    responsive: true, maintainAspectRatio: false,
    plugins: {{ legend: {{ display: true, position: 'bottom', labels: {{ font: {{ size: 10 }} }} }} }},
    scales: {{
      x: {{ grid: {{ color: '#e1e0d9' }}, ticks: {{ font: {{ size: 9 }}, maxRotation: 90 }} }},
      y: {{ grid: {{ color: '#e1e0d9' }} }}
    }}
  }}
}});
</script>
</body>
</html>"""


if __name__ == '__main__':
    result = analyze()
    print('=== 노후 대형상가 공실위험 요약 (순감소율 오름차순 = 위험도 높은 순) ===')
    for s in result['summary']:
        print(f"{s['name']:45s}  점포수 순증감 {s['net_change_pct']:+.1f}%  "
              f"최근 점포수 {s['latest_total']}개  최근4분기 평균폐업률 {s['recent_close_rate_avg']}%  [{s['risk_level']}]")

    html = generate(result)
    output_path = os.path.join(BASE_DIR, "html", '역산공실탐지기반_대안알고리즘.html')
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"\nHTML 생성 완료: {output_path}")