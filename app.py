import streamlit as st
import pandas as pd
import plotly.express as px
import requests
import pytz
from datetime import datetime

# ==========================================
# 1. 網頁基本設定 & CSS 美化
# ==========================================
st.set_page_config(page_title="SolarEdge Dashboard", layout="wide")

st.markdown("""
    <style>
    header {visibility: hidden;}
    .main-header {
        background-color: #1e213a;
        color: white;
        padding: 15px;
        text-align: center;
        border-radius: 8px;
        margin-top: -60px;
        margin-bottom: 20px;
        font-family: sans-serif;
    }
    .main-header h2 { margin: 0; font-weight: 600; font-size: 1.8rem; }
    .main-header span { color: #A0A5B5; font-size: 0.9em; font-weight: normal; }
    div[data-testid="stVerticalBlock"] > div { background-color: #FFFFFF; }
    div[data-testid="stMetricValue"] { color: #00E676; font-weight: bold; }
    .stApp { background-color: #F0F2F6; }
    </style>
""", unsafe_allow_html=True)

# ==========================================
# 2. SolarEdge API 設定與資料抓取函數
# ==========================================
API_KEY = 'ER7AXC88DZ7DGYWH3MNZRCKRYRRQOARV'
SITE_ID = '4873924'
BASE_URL = f"https://monitoringapi.solaredge.com/site/{SITE_ID}"

# 數值格式化小工具
def format_power(w): return f"{w/1000:.2f} kW" if w is not None else "0 kW"
def format_energy(wh):
    if wh is None: return "0 Wh"
    if wh >= 1_000_000: return f"{wh/1_000_000:.2f} MWh"
    elif wh >= 1000: return f"{wh/1000:.2f} kWh"
    else: return f"{wh:.2f} Wh"

# 抓取資料 (加入 @st.cache_data 避免每次重整網頁都頻繁消耗 API 額度)
@st.cache_data(ttl=300) # 5分鐘更新一次
def fetch_solaredge_data():
    data = {"overview": {}, "envBenefits": {}, "power_df": pd.DataFrame()}
    try:
        # 抓取總覽數據 (發電量)
        res_ov = requests.get(f"{BASE_URL}/overview?api_key={API_KEY}")
        if res_ov.status_code == 200:
            data["overview"] = res_ov.json().get("overview", {})

        # 抓取環境效益
        res_env = requests.get(f"{BASE_URL}/envBenefits?systemUnits=Metric&api_key={API_KEY}")
        if res_env.status_code == 200:
            data["envBenefits"] = res_env.json().get("envBenefits", {})

        # 抓取今日功率曲線 (確保使用底線 Asia/Hong_Kong)
        hkt = pytz.timezone('Asia/Hong_Kong')
        today_str = datetime.now(hkt).strftime("%Y-%m-%d")
        res_pwr = requests.get(f"{BASE_URL}/power?startTime={today_str}%2000:00:00&endTime={today_str}%2023:59:59&api_key={API_KEY}")
        if res_pwr.status_code == 200:
            vals = res_pwr.json().get("power", {}).get("values", [])
            df = pd.DataFrame(vals)
            if not df.empty:
                df['date'] = pd.to_datetime(df['date'])
                df['value'] = df['value'].fillna(0) / 1000 # 將 Watts 轉為 kW
                data["power_df"] = df
    except Exception as e:
        st.error(f"連線 API 時發生錯誤: {e}")
    return data

# 取得資料
api_data = fetch_solaredge_data()
ov = api_data["overview"]
env = api_data["envBenefits"]
df_chart = api_data["power_df"]

# 解析數值
current_power = format_power(ov.get("currentPower", {}).get("power"))
today_energy = format_energy(ov.get("lastDayData", {}).get("energy"))
month_energy = format_energy(ov.get("lastMonthData", {}).get("energy"))
lifetime_energy = format_energy(ov.get("lifeTimeData", {}).get("energy"))

# 環境數值
co2_saved = f"{env.get('gasEmissionSaved', {}).get('co2', 0):.1f}"
trees_planted = str(env.get('treesPlanted', 0))

# ==========================================
# 3. 網頁介面排版與繪製
# ==========================================
st.markdown(f'''
    <div class="main-header">
        <h2>Tin Sum Ambulance Depot <span style="margin: 0 10px;">|</span> <span>即時系統資訊</span></h2>
    </div>
''', unsafe_allow_html=True)

col_left, col_right = st.columns([2, 1])

# 左側區塊
with col_left:
    with st.container(border=True):
        st.markdown("**| 效能 (來自真實 API)**")
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("⚡ 電流 (目前功率)", current_power)
        m2.metric("📅 今日發電量", today_energy)
        m3.metric("🗓️ 本月發電量", month_energy)
        m4.metric("♾️ 整個使用期發電量", lifetime_energy)

    with st.container(border=True):
        st.markdown("**| 功率和電量**")
        st.caption("今日功率 (kW)")
        if not df_chart.empty:
            fig = px.area(df_chart, x="date", y="value", color_discrete_sequence=['#00E676'])
            fig.update_layout(
                margin=dict(l=0, r=0, t=10, b=0),
                height=350,
                xaxis_title=None,
                yaxis_title=None,
                plot_bgcolor='white',
                paper_bgcolor='white'
            )
            fig.update_xaxes(showgrid=False)
            fig.update_yaxes(showgrid=True, gridcolor='#E0E0E0', gridwidth=1)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("今日尚無發電數據，或太陽下山變流器已休眠。")

# 右側區塊
with col_right:
    with st.container(border=True):
        st.markdown("**| 環境效益**")
        env1, env2 = st.columns(2)
        env1.markdown("<h1 style='text-align: center; color: #78909C;'>🏭</h1>", unsafe_allow_html=True)
        env1.metric("kg of 節省二氧化碳", co2_saved)

        env2.markdown("<h1 style='text-align: center; color: #78909C;'>🌲</h1>", unsafe_allow_html=True)
        env2.metric("等效植樹量", trees_planted)

    with st.container(border=True):
        # 修正了 warning: 改用 use_container_width=True
        st.image("https://images.unsplash.com/photo-1509391366360-1e97f52ce23b?q=80&w=800&auto=format&fit=crop", use_container_width=True)

# 底部更新時間 (確保使用底線 Asia/Hong_Kong)
hkt = pytz.timezone('Asia/Hong_Kong')
update_time = datetime.now(hkt).strftime("%Y/%m/%d %p %I:%M:%S")
st.markdown(f"<p style='color: #888888; font-size: 0.8em;'>🕒 儀表板最後更新: {update_time}</p>", unsafe_allow_html=True)
