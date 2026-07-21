import re
import numpy as np
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


@st.cache_data
def build_age_ratio_matrix(df, age_cols, year_month, gender="계"):
    """지역별 연령 비율(%) 매트릭스를 만든다. index=지역명, columns=나이(0~100)"""
    ages = sorted({age for (_, ym, g, age) in age_cols if g == gender and ym == year_month})
    col_map = {age: col for (col, ym, g, age) in age_cols if g == gender and ym == year_month}
    cols = [col_map[a] for a in ages]

    total_col = f"{year_month}_{gender}_총인구수"
    sub = df[["지역명", total_col] + cols].copy()
    sub = sub[sub[total_col] > 0]  # 인구가 0인 지역 제외 (비율 계산 불가)

    ratio = sub[cols].div(sub[total_col], axis=0) * 100
    ratio.index = sub["지역명"].values
    ratio.columns = ages
    return ratio


def find_similar_regions(ratio_matrix, target_region, top_n=5):
    """코사인 유사도 기준 가장 인구구조가 비슷한 지역 Top N을 반환"""
    if target_region not in ratio_matrix.index:
        return pd.Series(dtype=float)

    mat = ratio_matrix.values
    target_vec = ratio_matrix.loc[target_region].values

    norms = np.linalg.norm(mat, axis=1)
    target_norm = np.linalg.norm(target_vec)
    sims = (mat @ target_vec) / (norms * target_norm + 1e-9)

    sim_series = pd.Series(sims, index=ratio_matrix.index)
    sim_series = sim_series.drop(index=target_region, errors="ignore")

    # 완전히 이름이 같은 중복 행이 있을 경우 대비
    sim_series = sim_series.groupby(sim_series.index).max()

    return sim_series.sort_values(ascending=False).head(top_n)


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
    search_text = st.text_input("지역명 검색 (예: 강남구, 종로구, 청운효자동)", "")

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
# 5. 꺾은선 그래프 (Plotly) - 선택 지역 연령별 인구
# ---------------------------------------------------------
st.subheader(f"📈 {selected_region} 연령별 인구 분포")

fig = go.Figure()
colors = {"계": "#2E86AB", "남": "#4C72B0", "여": "#DD5E89"}

for label in selected_genders:
    gender = gender_map[label]
    ages = sorted({age for (_, ym, g, age) in age_cols if g == gender and ym == year_month})
    col_map = {age: col for (col, ym, g, age) in age_cols if g == gender and ym == year_month}
    y_values = [row[col_map[age]] for age in ages]

    fig.add_trace(
        go.Scatter(
            x=ages, y=y_values, mode="lines", name=label,
            line=dict(width=2, color=colors.get(gender)),
        )
    )

fig.update_layout(
    xaxis_title="나이 (세, 100=100세 이상)",
    yaxis_title="인구수 (명)",
    hovermode="x unified",
    height=500,
    legend_title="성별",
)
st.plotly_chart(fig, use_container_width=True)

# ---------------------------------------------------------
# 6. 인구구조가 가장 비슷한 지역 Top 5 (전국, 읍면동 포함)
# ---------------------------------------------------------
st.subheader(f"🧭 '{selected_region}'과 인구구조가 가장 비슷한 지역 Top 5 (전국)")

ratio_matrix = build_age_ratio_matrix(df, age_cols, year_month, gender="계")
top5 = find_similar_regions(ratio_matrix, selected_region, top_n=5)

if top5.empty:
    st.info("비교할 지역 데이터가 부족합니다.")
else:
    fig2 = go.Figure()

    # 선택 지역 (굵은 선, 강조)
    fig2.add_trace(
        go.Scatter(
            x=ratio_matrix.columns,
            y=ratio_matrix.loc[selected_region],
            mode="lines",
            name=f"★ {selected_region} (기준)",
            line=dict(width=4, color="#2E2E2E"),
        )
    )

    # Top 5 유사 지역 (얇은 선)
    palette = ["#EF553B", "#00CC96", "#AB63FA", "#FFA15A", "#19D3F3"]
    for i, (region_name, sim_score) in enumerate(top5.items()):
        fig2.add_trace(
            go.Scatter(
                x=ratio_matrix.columns,
                y=ratio_matrix.loc[region_name],
                mode="lines",
                name=f"{region_name} (유사도 {sim_score:.3f})",
                line=dict(width=2, color=palette[i % len(palette)], dash="dot"),
            )
        )

    fig2.update_layout(
        xaxis_title="나이 (세, 100=100세 이상)",
        yaxis_title="연령별 인구 비율 (%)",
        hovermode="x unified",
        height=550,
        legend_title="지역 (코사인 유사도)",
    )
    st.plotly_chart(fig2, use_container_width=True)

    st.dataframe(
        top5.rename("유사도").reset_index().rename(columns={"index": "지역명"}),
        use_container_width=True,
    )

# ---------------------------------------------------------
# 7. 원본 데이터 확인 (선택 사항)
# ---------------------------------------------------------
with st.expander("원본 데이터 보기"):
    st.dataframe(row.to_frame().T)
