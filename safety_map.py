"""
노후상가/전통시장 위치(위도경도) + 소속 자치구
정확한 지번 주소는 아니고 그 상권 있는 동/구 중심좌표로 근사한 거임
(일단 프로토타입이라 이렇게 해둠, 나중에 실서비스 가면 상가정보 API의
실제 lon/lat 필드 그대로 쓰면 됨)
자치구는 상권명이 위치한 일반적으로 알려진 행정구역 기준 (정밀 지번 대조는 아님)
"""

MARKET_COORDS = {
    '세운상가가동': (37.5701, 126.9917, '종로구'),
    '낙원시장(낙원지하시장(대일상가))': (37.5730, 126.9870, '종로구'),
    '동대문상가A동': (37.5701, 126.9986, '종로구'),
    '동대문상가B동': (37.5701, 126.9986, '종로구'),
    '동대문상가C동': (37.5701, 126.9986, '종로구'),
    '동대문상가D동': (37.5701, 126.9986, '종로구'),
    '남대문시장(자유상가)': (37.5592, 126.9784, '중구'),
    '용산전자상가(용산역)': (37.5296, 126.9648, '용산구'),
    '평화시장(남평화시장, 제일평화시장, 신평화패션타운)': (37.5705, 126.9995, '중구'),
    '청계천공구상가': (37.5701, 126.9950, '중구'),
    '테크노상가(엘리시움)': (37.5290, 126.9660, '용산구'),
    '방산종합시장(방산시장)': (37.5695, 126.9975, '중구'),
    '광장시장(광장전통시장)': (37.5701, 127.0010, '종로구'),
    '경동시장': (37.5825, 127.0388, '동대문구'),
    '청량리종합시장': (37.5803, 127.0466, '동대문구'),
    '청량리전통시장': (37.5807, 127.0455, '동대문구'),
    '황학동벼룩시장': (37.5720, 127.0160, '중구'),
    '신림중앙시장(조원동 펭귄시장)': (37.4845, 126.9296, '관악구'),
    '영등포전통시장': (37.5163, 126.9068, '영등포구'),
    '영등포유통상가': (37.5170, 126.9060, '영등포구'),
    '영등포시장기계공구상가': (37.5158, 126.9075, '영등포구'),
    '동묘시장(동묘벼룩시장)': (37.5730, 127.0165, '종로구'),
    '중부시장(신중부시장)': (37.5651, 126.9945, '중구'),
    '통인시장': (37.5807, 126.9700, '종로구'),
    '자양골목전통시장(자양골목시장)': (37.5350, 127.0790, '광진구'),
    '길음시장': (37.6068, 127.0254, '성북구'),
    '정릉시장': (37.6094, 127.0080, '성북구'),
    '수유전통시장(수유시장, 수유골목시장)': (37.6376, 127.0257, '강북구'),
    '창동신창시장': (37.6534, 127.0473, '도봉구'),
    '쌍문시장(쌍문역골목시장)': (37.6486, 127.0347, '도봉구'),
    '신설종합시장': (37.5758, 127.0224, '동대문구'),
    '상계중앙시장': (37.6600, 127.0730, '노원구'),
    '화곡중앙시장': (37.5417, 126.8402, '강서구'),
    '봉천중앙시장': (37.4823, 126.9522, '관악구'),
    '신림종합시장': (37.4845, 126.9296, '관악구'),
    '사당시장': (37.4766, 126.9816, '동작구'),
    '노량진중앙시장': (37.5135, 126.9427, '동작구'),
    '가락시장': (37.4924, 127.1185, '송파구'),
    '답십리 건축자재시장': (37.5713, 127.0450, '동대문구'),
    '남성사계시장(남성시장)': (37.4870, 126.9750, '동작구'),
    '중랑동부시장(중랑교종합상가)': (37.6063, 127.0925, '중랑구'),
    '성동용답상가시장': (37.5637, 127.0475, '성동구'),
    '삼익패션타운(남대문시장)': (37.5592, 126.9784, '중구'),
    '숭례문수입상가(남대문시장)': (37.5592, 126.9784, '중구'),
    '동대문종합시장(동대문종합시장 신관, 동대문종합시장D동상가)': (37.5701, 126.9986, '종로구'),
    '동대문패션타운 관광특구': (37.5701, 126.9986, '종로구'),
    '청평화시장': (37.5705, 126.9995, '중구'),
    '동평화시장': (37.5705, 126.9995, '중구'),
}

# 2026-09-07: alt_vacancy_indicator.py의 TARGET_MARKETS가 48개 -> 277개로
# 확장되면서 나머지 229곳은 좌표가 없었음. geocode_missing_markets.py로
# OpenStreetMap Nominatim 지오코딩을 돌려 107곳 확보(122곳은 검색 결과 없음/
# 서울 밖 매칭이라 실패, cvs/market_coords_geocoded.csv에 기록됨 - 미확보 상태로
# 남기고 지어내지 않음). 위 48개와 마찬가지로 정밀 지번 좌표가 아니라
# "그 이름으로 OSM에 등록된 가장 근접한 지점" 기준 근사치.
MARKET_COORDS.update({
    '가락시장역': (37.4926, 127.1188, '송파구'),
    '가리봉시장': (37.4829, 126.8872, '구로구'),
    '강북북부시장': (37.6362, 127.0304, '강북구'),
    '강서농산물도매시장': (37.5533, 126.8208, '강서구'),
    '개봉중앙시장': (37.4909, 126.8562, '구로구'),
    '경창시장': (37.5247, 126.8424, '양천구'),
    '고척근린시장': (37.5010, 126.8510, '구로구'),
    '공덕시장': (37.5447, 126.9535, '마포구'),
    '공릉동 도깨비시장': (37.6225, 127.0760, '노원구'),
    '공항시장': (37.5634, 126.8104, '강서구'),
    '공항시장역 1번': (37.5633, 126.8105, '강서구'),
    '공항시장역 3번': (37.5633, 126.8105, '강서구'),
    '구로시장': (37.4889, 126.8851, '구로구'),
    '금남시장': (37.5482, 127.0217, '성동구'),
    '까치산시장': (37.5322, 126.8471, '강서구'),
    '남구로시장': (37.4893, 126.8911, '구로구'),
    '남문시장': (37.4738, 126.9007, '금천구'),
    '남서울상가': (37.4990, 127.0519, '강남구'),
    '남성역골목시장': (37.4837, 126.9729, '동작구'),
    '노룬산시장(노룬산골목시장)': (37.5370, 127.0627, '광진구'),
    '답십리시장': (37.5737, 127.0576, '동대문구'),
    '대림상가(청계상가)': (37.5540, 127.0344, '성동구'),
    '대신시장': (37.5118, 126.9161, '영등포구'),
    '대조시장': (37.6088, 126.9264, '은평구'),
    '돈암시장(돈암제일시장)': (37.5913, 127.0167, '성북구'),
    '동문시장': (37.5702, 127.0120, '종로구'),
    '동부시장': (37.5943, 127.0772, '중랑구'),
    '동진시장': (37.5623, 126.9268, '마포구'),
    '뚝도시장': (37.5387, 127.0556, '성동구'),
    '마장축산물시장': (37.5704, 127.0375, '성동구'),
    '마전교지하쇼핑센터(구 한일상가)': (37.5701, 127.0020, '종로구'),
    '마천시장': (37.4981, 127.1504, '송파구'),
    '마천중앙시장': (37.4998, 127.1525, '송파구'),
    '마포농수산물시장': (37.5650, 126.8985, '마포구'),
    '만리시장': (37.5513, 126.9636, '용산구'),
    '망원시장': (37.5566, 126.9061, '마포구'),
    '명일전통시장': (37.5500, 127.1437, '강동구'),
    '모래내시장(서중시장)': (37.5705, 126.9140, '서대문구'),
    '밤나무골시장': (37.6094, 127.0356, '성북구'),
    '방이시장': (37.5117, 127.1130, '송파구'),
    '방학동도깨비시장': (37.6652, 127.0355, '도봉구'),
    '백련시장': (37.5768, 126.9248, '서대문구'),
    '백운시장': (37.6556, 127.0151, '도봉구'),
    '봉일시장': (37.4862, 126.9385, '관악구'),
    '비단길현대시장(현대시장)': (37.4574, 126.9034, '금천구'),
    '사가정시장': (37.5804, 127.0893, '중랑구'),
    '상계주공1단지(가)상가': (37.6472, 127.0630, '노원구'),
    '상도전통시장': (37.4986, 126.9518, '동작구'),
    '새마을시장': (37.5089, 127.0866, '송파구'),
    '서울약령시장': (37.5784, 127.0369, '동대문구'),
    '서울중앙시장(신중앙시장)': (37.5670, 127.0197, '중구'),
    '석관시장': (37.6088, 127.0592, '성북구'),
    '성대전통시장(성대시장)': (37.4993, 126.9312, '동작구'),
    '솔샘시장(미아6,7동골목시장)': (37.6196, 127.0193, '강북구'),
    '숭인시장': (37.6135, 127.0298, '강북구'),
    '신도봉시장': (37.6693, 127.0436, '도봉구'),
    '신림현대종합상가': (37.4746, 126.9337, '관악구'),
    '신사상가': (37.5323, 127.0284, '강남구'),
    '신성시장(신성골목시장)': (37.5583, 127.0879, '광진구'),
    '신신림시장(삼성동시장)': (37.4691, 126.9315, '관악구'),
    '신영시장': (37.5363, 126.8328, '양천구'),
    '신원시장': (37.4828, 126.9268, '관악구'),
    '신월중앙시장': (37.5281, 126.8424, '강서구'),
    '신흥시장': (37.5954, 126.9149, '은평구'),
    '아현시장': (37.5567, 126.9527, '마포구'),
    '암사종합시장': (37.5499, 127.1282, '강동구'),
    '양재시민의숲역(양재동꽃시장, aT센터)': (37.4702, 127.0386, '서초구'),
    '양재시장': (37.4843, 127.0380, '서초구'),
    '연서시장': (37.6193, 126.9219, '은평구'),
    '영동교골목시장': (37.5395, 127.0627, '광진구'),
    '영등포시장역 1번': (37.5234, 126.9054, '영등포구'),
    '영등포시장역 3번': (37.5234, 126.9054, '영등포구'),
    '영등포시장역 4번': (37.5234, 126.9054, '영등포구'),
    '영등포청과시장(조광시장)': (37.5206, 126.9011, '영등포구'),
    '영일시장': (37.5184, 126.9009, '영등포구'),
    '영진시장': (37.4998, 126.9168, '영등포구'),
    '영천시장': (37.5706, 126.9612, '서대문구'),
    '영천시장입구': (37.5694, 126.9631, '서대문구'),
    '오류시장': (37.4966, 126.8436, '구로구'),
    '우리시장': (37.4981, 126.9045, '영등포구'),
    '우림시장': (37.5955, 127.0992, '중랑구'),
    '유진상가': (37.5916, 126.9431, '서대문구'),
    '은행나무시장': (37.4509, 126.9090, '금천구'),
    '응암시장(신응암시장)': (37.5940, 126.9188, '은평구'),
    '이경시장': (37.5945, 127.0662, '동대문구'),
    '이태원시장': (37.5338, 126.9900, '용산구'),
    '인왕시장(홍제골목형상점가)': (37.5914, 126.9434, '서대문구'),
    '인헌시장(원당종합시장)': (37.4748, 126.9657, '관악구'),
    '인현시장': (37.5633, 126.9952, '중구'),
    '자동차부품상가': (37.5645, 127.0578, '동대문구'),
    '장미제일시장(중화동제일시장)': (37.6051, 127.0765, '중랑구'),
    '전곡시장': (37.5778, 127.0685, '동대문구'),
    '전농로터리시장': (37.5789, 127.0566, '동대문구'),
    '제일시장': (37.5639, 127.0813, '광진구'),
    '조양시장': (37.5389, 127.0674, '광진구'),
    '조원동 펭귄시장(신림중앙시장)': (37.4835, 126.9123, '관악구'),
    '증산종합시장': (37.5815, 126.9050, '은평구'),
    '청량리수산시장': (37.5786, 127.0405, '동대문구'),
    '충신시장': (37.5753, 127.0053, '종로구'),
    '평화시장(통일상가, 동화상가)': (37.5694, 127.0046, '중구'),
    '푸른터시장(기능상실)': (37.4781, 126.9013, '금천구'),
    '풍납시장': (37.5372, 127.1227, '송파구'),
    '한아름시장': (37.5437, 127.0699, '광진구'),
    '홍연시장': (37.5770, 126.9305, '서대문구'),
    '화곡본동시장': (37.5432, 126.8437, '강서구'),
    '후암시장': (37.5507, 126.9771, '용산구'),
    '흑석시장': (37.5072, 126.9618, '동작구'),
})

# 2026-09-07 2차 재시도: 122곳 실패분에 괄호 안 별칭 검색을 추가해 19곳 성공했으나,
# 그중 3곳("남부골목시장" 등)은 흔한 별칭("남부시장"·"우성상가"·"대림시장")으로
# 매칭돼 이름이 암시하는 지역(화곡/신월/대림)과 실제 매칭된 구가 명백히 달라 오검색으로
# 판단해 제외(cvs/market_coords_geocoded.csv도 실패로 되돌림). 나머지 16곳만 반영.
MARKET_COORDS.update({
    '개봉프라자(고척근린시장)': (37.5010, 126.8510, '구로구'),
    '경동광성상가(경동시장)': (37.5794, 127.0388, '동대문구'),
    '관악종합시장(신원시장)': (37.4828, 126.9268, '관악구'),
    '대명여울빛거리시장(대명시장)': (37.4541, 126.9023, '금천구'),
    '동원전통종합시장(동원시장, 동원전통시장 상점가)': (37.5905, 127.0937, '중랑구'),
    '목동깨비시장(목3동시장)': (37.5496, 126.8639, '양천구'),
    '삼성동 시장(삼성동시장)': (37.4693, 126.9315, '관악구'),
    '삼양골목시장(삼양시장)': (37.6249, 127.0184, '강북구'),
    '수유중앙골목시장(수유중앙시장)': (37.6403, 127.0213, '강북구'),
    '신정1동 골목시장(신정제일시장)': (37.5212, 126.8550, '양천구'),
    '신정2동 골목시장(오목교중앙시장)': (37.5204, 126.8758, '양천구'),
    '영신상가(제일상가)': (37.5699, 126.9986, '종로구'),
    '중곡제일시장(중곡제일골목시장, 광성시장)': (37.5636, 127.0812, '광진구'),
    '태능엔터피아(태릉시장)': (37.5997, 127.0782, '중랑구'),
    '한양대앞상점가(한양시장, 왕십리맛골목)': (37.5588, 127.0409, '성동구'),
    '황학시장(서울중앙시장, 신중앙시장)': (37.5670, 127.0197, '중구'),
})


# 안전등급 지도(risk_grade_model + alt_vacancy_indicator 결과 + 위 좌표 합쳐서)
"""
안전등급 지도 - 1단계 메인화면으로 쓸 프로토타입
risk_grade_model.py에서 나온 A~D 등급 + 위 MARKET_COORDS 위치 데이터 합쳐서
서울 지도 위에 노후상가들 안전관리 우선순위 등급 표시함

[수정] 폐업률을 팝업에 표시 + 등급 필터 버튼 추가
(이미 markers 데이터에 close_rate 값이 있었는데 팝업에서 안 보여주고 있던 걸 반영)
"""
import json
import os
from alt_vacancy_indicator import analyze
from risk_grade_model import compute_risk_grades

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

GRADE_COLOR = {"D": "#e34948", "C": "#f59e0b", "B": "#2a78d6", "A": "#3b6d11"}
GRADE_LABEL = {"D": "최우선 점검", "C": "우선 점검 권고", "B": "정기 모니터링", "A": "양호"}


def generate(rows: list) -> str:
    markers = []
    districts_used = set()
    for r in rows:
        coord = MARKET_COORDS.get(r["name"])
        if not coord:
            continue
        lat, lng, district = coord
        districts_used.add(district)
        markers.append({
            "name": r["name"], "grade": r["grade"], "score": r["risk_score"],
            "net_change": r["net_change_pct"], "close_rate": r["recent_close_rate_avg"],
            "lat": lat, "lng": lng, "district": district, "color": GRADE_COLOR[r["grade"]],
        })

    markers_json = json.dumps(markers, ensure_ascii=False)
    districts_sorted = sorted(districts_used)
    districts_json = json.dumps(districts_sorted, ensure_ascii=False)
    grade_counts = {"A": 0, "B": 0, "C": 0, "D": 0}
    for r in rows:
        grade_counts[r["grade"]] += 1

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>역산공실탐지기반 — 안전등급 지도 (1단계 메인화면)</title>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css" />
<script src="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js"></script>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #f8f8f7; color: #0b0b0b; padding: 2rem; }}
  h1 {{ font-size: 18px; font-weight: 500; margin-bottom: 4px; }}
  .subtitle {{ font-size: 12px; color: #898781; margin-bottom: 1.5rem; }}
  .caveat {{ background: #fff7ed; border-left: 3px solid #f59e0b; padding: 0.75rem 1rem; font-size: 12px; color: #52514e; margin-bottom: 1.5rem; line-height: 1.6; }}
  .layout {{ display: grid; grid-template-columns: 1fr 320px; gap: 20px; }}
  .map-box {{ background: #fff; border-radius: 12px; border: 0.5px solid rgba(11,11,11,0.1); padding: 1.25rem; position: relative; }}
  .map-title {{ font-size: 13px; font-weight: 500; color: #52514e; margin-bottom: 12px; }}
  #mapArea {{ width: 100%; height: 620px; border-radius: 8px; overflow: hidden; }}
  .legend {{ position: absolute; z-index: 1000; top: 4.2rem; right: 2.2rem; background: rgba(255,255,255,0.95); border: 1px solid #e8e7e2;
    border-radius: 8px; padding: 10px 14px; font-size: 11px; }}
  .legend-row {{ display: flex; align-items: center; gap: 6px; margin-bottom: 4px; cursor: pointer; user-select: none; }}
  .legend-row.off {{ opacity: 0.35; }}
  .legend-dot {{ width: 10px; height: 10px; border-radius: 50%; }}
  .filter-hint {{ font-size: 9px; color: #898781; margin-top: 6px; border-top: 1px solid #e8e7e2; padding-top: 6px; }}
  .side-panel {{ display: flex; flex-direction: column; gap: 10px; }}
  .kpi-card {{ background: #f1f0eb; border-radius: 8px; padding: 0.875rem; text-align: center; }}
  .kpi-label {{ font-size: 11px; color: #898781; margin-bottom: 4px; }}
  .kpi-value {{ font-size: 22px; font-weight: 600; }}
  .top-list {{ background: #fff; border-radius: 10px; border: 0.5px solid rgba(11,11,11,0.1); padding: 1rem; }}
  .top-list-title {{ font-size: 12px; font-weight: 600; color: #52514e; margin-bottom: 8px; }}
  .top-item {{ display: flex; justify-content: space-between; font-size: 11px; padding: 4px 0; border-bottom: 1px solid #f1f0eb; }}
  .note {{ font-size: 11px; color: #898781; margin-top: 1.5rem; line-height: 1.6; }}
  .leaflet-popup-content {{ font-size: 12px; line-height: 1.6; }}
</style>
</head>
<body>
<h1>역산공실탐지기반 — 안전등급 지도 (1단계 메인화면 프로토타입)</h1>
<div class="subtitle">서울시 노후 대형상가·전통시장 {len(rows)}곳 | 공실 순증감률 + 폐업률 결합 안전관리 우선순위 등급</div>

<div class="caveat">
📍 <b>위치 정확도 안내:</b> 지도에 표시된 안전등급(D~A)과 위험점수는 `risk_grade_model.py`가 48개 상권의 실측 데이터로 계산한 결과 그대로다.<br>
다만 마커의 정확한 좌표(위경도)는 각 상권이 위치한 동/구의 중심점으로 표시한 근사치이며, 실제 건물의 정밀 주소 좌표는 아니다. 자치구 표기도 상권명 기준으로 통상 알려진 행정구역이며, 정밀 지번 대조 결과는 아니다.<br>
(예: 동대문상가 A~D동은 실제로 같은 복합건물 내 동(wing) 구분이라 근사치로도 위치가 크게 다르지 않지만, 일부 인접 건물은 정밀도가 떨어질 수 있다.)<br>
지도 자체는 실제 OpenStreetMap 타일을 사용한다.(Leaflet.js) 실 서비스 단계에서는 상가정보 API의 정확한 위경도(lon/lat) 필드로 교체할 예정이다.<br>
건물 준공연도·공실 추정 현황은 상권 단위 데이터로는 산출이 어려워 이번 프로토타입에는 포함하지 않았다(향후 건물 단위 실측 데이터 확보 시 반영 예정).
</div>

<div class="layout">
  <div class="map-box">
    <div class="map-title">서울시 안전관리 우선순위 등급 분포 (실제 지도)</div>
    <div id="mapArea"></div>
    <div class="legend" id="legendBox">
      <div style="font-weight:600;margin-bottom:6px;">안전등급 (클릭해서 필터)</div>
      <div class="legend-row" data-grade="D"><div class="legend-dot" style="background:#e34948;"></div>D — 최우선 점검</div>
      <div class="legend-row" data-grade="C"><div class="legend-dot" style="background:#f59e0b;"></div>C — 우선 점검 권고</div>
      <div class="legend-row" data-grade="B"><div class="legend-dot" style="background:#2a78d6;"></div>B — 정기 모니터링</div>
      <div class="legend-row" data-grade="A"><div class="legend-dot" style="background:#3b6d11;"></div>A — 양호</div>
      <div class="filter-hint" style="border-top:none; border-bottom:1px solid #e8e7e2; padding-top:4px; padding-bottom:8px; margin-top:4px; margin-bottom:10px;">
        등급을 클릭하면 지도에서 켜고 끌 수 있습니다.
      </div>

        <div>
        <div style="font-weight:600; margin-bottom:6px;">지역(자치구)</div>
        <div class="filter-hint" style="border-top:none; margin-top:0; padding-top:0;">
          지역 필터는 종로구(11곳)·중구(10곳)가 가장 많습니다.<br> 
          일부 자치구는 상권이 1~3곳뿐이라, 등급 필터와 겹치면 마커가 안 보일 수 있습니다.
        </div><br> 
        <select id="districtFilter" style="width:100%; font-size:11px; padding:4px; border-radius:4px; border:1px solid #d3d1c7;">
          <option value="ALL">전체 보기</option>
        </select>
      </div>
    </div>
  </div>
  <div class="side-panel">
    <div class="kpi-card">
      <div class="kpi-label">분석 대상 상권</div>
      <div class="kpi-value" style="color:#52514e;">{len(rows)}곳</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-label">D등급 (최우선 점검)</div>
      <div class="kpi-value" style="color:#e34948;">{grade_counts['D']}곳</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-label">C등급 (우선 점검 권고)</div>
      <div class="kpi-value" style="color:#d97706;">{grade_counts['C']}곳</div>
    </div>
    <div class="top-list">
      <div class="top-list-title">🔴 D등급 상권 (위험점수 순)</div>
      <div id="dList"></div>
    </div>
  </div>
</div>

<div class="note">
※ 방법론: 점포수 순증감률(2021~2025, 서울시 상권분석서비스)과 최근4분기 평균폐업률을 결합해 위험점수(0~100)
산출,<br< 절대기준 고정 임계값(60점 이상 D, 40~60 C, 20~40 B, 20미만 A)으로 {len(rows)}곳을 등급 분류
(D {grade_counts['D']}곳·C {grade_counts['C']}곳·B {grade_counts['B']}곳·A {grade_counts['A']}곳).<br> 상세 산출 근거는 `역산공실탐지기반_안전등급모델.html` 참고.
지도 타일: © OpenStreetMap contributors.
</div>

<script>
const markers = {markers_json};
const districts = {districts_json};
const gradeColors = {{ D: '#e34948', C: '#f59e0b', B: '#2a78d6', A: '#3b6d11' }};
const activeGrades = new Set(['D','C','B','A']);
let activeDistrict = 'ALL';
const circleByMarker = [];

const map = L.map('mapArea').setView([37.5665, 126.9780], 11);
L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
  maxZoom: 18,
  attribution: '&copy; OpenStreetMap contributors'
}}).addTo(map);

const districtSelect = document.getElementById('districtFilter');
districts.forEach(d => {{
  const opt = document.createElement('option');
  opt.value = d; opt.textContent = d;
  districtSelect.appendChild(opt);
}});

function applyFilters() {{
  circleByMarker.forEach(({{ marker, circle }}) => {{
    const gradeOk = activeGrades.has(marker.grade);
    const districtOk = (activeDistrict === 'ALL') || (marker.district === activeDistrict);
    if (gradeOk && districtOk) {{
      if (!map.hasLayer(circle)) circle.addTo(map);
    }} else {{
      if (map.hasLayer(circle)) map.removeLayer(circle);
    }}
  }});
}}

markers.forEach(m => {{
  const circle = L.circleMarker([m.lat, m.lng], {{
    radius: 8,
    fillColor: m.color,
    color: '#fff',
    weight: 1.5,
    fillOpacity: 0.9,
  }}).addTo(map);
  // 폐업률(close_rate)·자치구(district)를 팝업에 추가 표시
  circle.bindPopup(`<b>[${{m.grade}}] ${{m.name}}</b><br>${{m.district}} · 위험점수 ${{m.score}} · 순증감 ${{m.net_change}}%<br>최근4분기 평균폐업률 ${{m.close_rate}}%`);
  circleByMarker.push({{ marker: m, circle }});
}});

// 범례 클릭 시 해당 등급 마커 켜고 끄기
document.querySelectorAll('.legend-row').forEach(row => {{
  row.addEventListener('click', () => {{
    const grade = row.dataset.grade;
    if (activeGrades.has(grade)) {{
      activeGrades.delete(grade);
      row.classList.add('off');
    }} else {{
      activeGrades.add(grade);
      row.classList.remove('off');
    }}
    applyFilters();
  }});
}});

// 자치구 드롭다운 필터
districtSelect.addEventListener('change', () => {{
  activeDistrict = districtSelect.value;
  applyFilters();
}});

const dList = document.getElementById('dList');
markers.filter(m => m.grade === 'D').sort((a,b) => b.score - a.score).forEach(m => {{
  dList.innerHTML += `<div class="top-item"><span>${{m.name}}</span><span style="color:#e34948;font-weight:600;">${{m.score}}</span></div>`;
}});
</script>
</body>
</html>"""


if __name__ == "__main__":
    result = analyze()
    rows = compute_risk_grades(result)
    html = generate(rows)
    output_path = os.path.join(BASE_DIR, "html", "역산공실탐지기반_안전등급지도.html")
    os.makedirs(os.path.join(BASE_DIR, "html"), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"생성 완료: {output_path}")
    print(f"마커 매칭: {sum(1 for r in rows if r['name'] in MARKET_COORDS)}/{len(rows)}")