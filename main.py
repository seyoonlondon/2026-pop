import re
import pandas as pd
import streamlit as st
import plotly.graph_objects as go

st.set_page_config(page_title="연령별 인구 구조", page_icon="📊", layout="wide")

DATA_FILE = "202606_202606_연령별인구현황_월간.csv"

# ---------------------------------------------------------
# 1. 데이터 로딩
# ---------------------------------------------------------
@st.cache_data
def load_data(path):
    df = pd.read_csv(path, encoding="cp949", low_memory=False)

    # 숫자 컬럼의 콤마 제거 후 숫자형 변환
    for col in df.columns[1:]:
        df[col] = df[col].astype(str).str.replace(",", "", regex=False)
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # 행정구역명 정리 (코드 괄호 제거) : "서울특별시 종로구 (1111000000)" -> "서울특별시 종로구"
    df["지역명"] = df["행정구역"].str.replace(r"\s*\(\d+\)\s*$", "", regex=True)

    return df


def parse_age_columns(columns):
    """'2026년06월_계_0세' 같은 컬럼명에서 (연월, 성별, 나이) 추출"""
    pattern = re.compile(r"^(\d{4}년\d{2}월)_(계|남|여)_(\d+세|100세 이상)$")
    parsed = []
    for col in columns:
        m = pattern.match(col)
        if m:
            ym, gender, age_label = m.groups()
            age = 100 if "이상" in age_label else int(age_label.replace("세", ""))
            parsed.append((col, ym, gender, age))
    return parsed


st.title("📊 지역별 연령별 인구 구조")
st.caption("행정안전부 주민등록 연령별 인구현황 데이터를 활용한 연령 분포 뷰어")

# ---------------------------------------------------------
# 2. 데이터 로드 (같은 폴더의 고정 파일명 사용)
# ---------------------------------------------------------
try:
    df = load_data(DATA_FILE)
except FileNotFoundError:
    st.error(f"'{DATA_FILE}' 파일을 찾을 수 없습니다. app.py와 같은 폴더에 있는지 확인해주세요.")
    st.stop()

age_cols = parse_age_columns(df.columns)

if not age_cols:
    st.error("연령별 인구 컬럼을 찾을 수 없습니다. CSV 형식을 확인해주세요.")
    st.stop()

year_month = age_cols[0][1]  # 예: '2026년06월'

# ---------------------------------------------------------
# 3. 지역 선택 (검색 입력 + 목록 선택 동시 지원)
# ---------------------------------------------------------
region_list = sorted(df["지역명"].dropna().unique().tolist())

st.subheader("🔍 지역 선택")
col1, col2 = st.columns([1, 2])

with col1:
    search_text = st.text_input("지역명 검색 (예: 강남구, 종로구)", "")

with col2:
    if search_text:
        filtered_regions = [r for r in region_list if search_text in r]
        if not filtered_regions:
            st.warning("검색 결과가 없습니다. 전체 목록에서 선택해주세요.")
            filtered_regions = region_list
    else:
        filtered_regions = region_list

    selected_region = st.selectbox(
        "지역 선택 (검색 결과 중에서 선택하거나, 검색 없이 전체 목록에서 선택 가능)",
        filtered_regions,
        index=0,
    )

# 성별 선택
gender_map = {"전체(계)": "계", "남자": "남", "여자": "여"}
selected_genders = st.multiselect(
    "표시할 성별", list(gender_map.keys()), default=["전체(계)"]
)

if not selected_genders:
    st.info("표시할 성별을 하나 이상 선택해주세요.")
    st.stop()

# ---------------------------------------------------------
# 4. 선택 지역 데이터 추출
# ---------------------------------------------------------
row = df[df["지역명"] == selected_region]

if row.empty:
    st.error("선택한 지역의 데이터를 찾을 수 없습니다.")
    st.stop()

row = row.iloc[0]

# 총 인구수 표시
total_col = f"{year_month}_계_총인구수"
if total_col in df.columns:
    st.metric(f"{selected_region} 총 인구수 ({year_month})", f"{int(row[total_col]):,} 명")

# ---------------------------------------------------------
# 5. 꺾은선 그래프 (Plotly)
# ---------------------------------------------------------
fig = go.Figure()

colors = {"계": "#2E86AB", "남": "#4C72B0", "여": "#DD5E89"}

for label in selected_genders:
    gender = gender_map[label]
    ages = sorted(
        {age for (_, ym, g, age) in age_cols if g == gender and ym == year_month}
    )
    col_map = {
        age: col for (col, ym, g, age) in age_cols if g == gender and ym == year_month
    }
    y_values = [row[col_map[age]] for age in ages]

    fig.add_trace(
        go.Scatter(
            x=ages,
            y=y_values,
            mode="lines",
            name=label,
            line=dict(width=2, color=colors.get(gender)),
        )
    )

fig.update_layout(
    title=f"{selected_region} 연령별 인구 분포 ({year_month})",
    xaxis_title="나이 (세, 100=100세 이상)",
    yaxis_title="인구수 (명)",
    hovermode="x unified",
    height=550,
    legend_title="성별",
)

st.plotly_chart(fig, use_container_width=True)

# ---------------------------------------------------------
# 6. 원본 데이터 확인 (선택 사항)
# ---------------------------------------------------------
with st.expander("원본 데이터 보기"):
    st.dataframe(row.to_frame().T)
