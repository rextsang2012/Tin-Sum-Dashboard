import streamlit as st
import pandas as pd
import plotly.express as px
import requests
import pytz
from datetime import datetime
import streamlit.components.v1 as components

# ==========================================
# 1. 網頁基本設定 & 電視全螢幕最佳化 CSS (放大字體與間距)
# ==========================================
st.set_page_config(page_title="SolarEdge Dashboard", layout="wide", initial_sidebar_state="collapsed")

st.markdown("""
    <style>
    /* 隱藏預設選單、頂部裝飾條與底部浮水印 */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    
    /* 調整頁面四周的留白，讓畫面有呼吸空間但不會太多 */
    .block-container {
        padding-top: 2rem !important;
        padding-bottom: 2rem !important;
        padding-left: 3rem !important;
        padding-right: 3rem !important;
        max-width: 100% !important;
    }

    /* 頂部深藍色標題列最佳化：放大標題字體以適應電視 */
    .main-header {
        background-color: #1e213a;
        color: white;
        padding: 20px;
        text-align: center;
        border-radius: 8px;
        margin-top: -30px; 
        margin-bottom: 20px;
        font-family: sans-serif;
    }
    .main-header h2 { margin: 0; font-weight: 600; font-size: 2.2rem; }
    .main-header span { color: #A0A5B5; font-size: 1.2rem; font-weight: normal; }
    
    /* 卡片背景與邊框設定 */
    div[data-testid="stVerticalBlock"] > div { background-color: #FFFFFF; }
    .stApp { background-color: #F0F2F6; }

    /* 【關鍵修改 1】：大幅放大數值 (Metric Value) 字體，適應遠距離觀看 */
    div[data-testid="stMetricValue"] { 
        font-size: 3.5rem !important; 
        color: #00E676; 
        font-weight: bold; 
        white-space: nowrap !important;
        overflow: visible !important;
        padding-top: 10px;
        padding-bottom: 10px;
    }
    
    /* 【關鍵修改 2】：放大標題 (Metric Label) 字體 */
    div[data-testid="stMetricLabel"] {
        overflow: visible !important;
        white-space: normal !important;
    }
    div[data-testid="stMetricLabel"] > div > p {
        font-size: 1.2rem !important;
        white-space: normal !important;
        text-overflow: clip !important;
    }
    </style>
""", unsafe_allow_html=True)

# ==========================================
# 2. SolarEdge API 設定與資料抓取函數
# ==========================================
API_KEY = st.secrets["SOLAREDGE_API_KEY"]
SITE_ID = '4873924'
BASE_URL = f"https://monitoringapi.solaredge.com/site/{SITE_ID}"

def format_power(w): return f"{w/1000:.2f} kW" if w is not None else "0 kW"
def format_energy(wh):
    if wh is None: return "0 Wh"
    if wh >= 1_000_000: return f"{wh/1_000_000:.2f} MWh"
    elif wh >= 1000: return f"{wh/1000:.2f} kWh"
    else: return f"{wh:.2f} Wh"

@st.cache_data(ttl=300) 
def fetch_solaredge_data():
    data = {"overview": {}, "envBenefits": {}, "power_df": pd.DataFrame()}
    try:
        res_ov = requests.get(f"{BASE_URL}/overview?api_key={API_KEY}")
        if res_ov.status_code == 200:
            data["overview"] = res_ov.json().get("overview", {})

        res_env = requests.get(f"{BASE_URL}/envBenefits?systemUnits=Metric&api_key={API_KEY}")
        if res_env.status_code == 200:
            data["envBenefits"] = res_env.json().get("envBenefits", {})

        hkt = pytz.timezone('Asia/Hong_Kong')
        today_str = datetime.now(hkt).strftime("%Y-%m-%d")
        res_pwr = requests.get(f"{BASE_URL}/power?startTime={today_str}%2000:00:00&endTime={today_str}%2023:59:59&api_key={API_KEY}")
        if res_pwr.status_code == 200:
            vals = res_pwr.json().get("power", {}).get("values", [])
            df = pd.DataFrame(vals)
            if not df.empty:
                df['date'] = pd.to_datetime(df['date'])
                df['value'] = df['value'].fillna(0) / 1000 
                data["power_df"] = df
    except Exception as e:
        pass 
    return data

api_data = fetch_solaredge_data()
ov = api_data["overview"]
df_chart = api_data["power_df"]

current_power = format_power(ov.get("currentPower", {}).get("power"))
today_energy = format_energy(ov.get("lastDayData", {}).get("energy"))
month_energy = format_energy(ov.get("lastMonthData", {}).get("energy"))

raw_lifetime_wh = ov.get("lifeTimeData", {}).get("energy", 0)
calc_lifetime_mwh = (raw_lifetime_wh / 1_000_000) / 100 
lifetime_energy = f"{calc_lifetime_mwh:,.2f} MWh"

calc_co2 = (raw_lifetime_wh / 1000) * 0.39
co2_saved = f"{calc_co2:,.1f}"

# ==========================================
# 3. 網頁介面排版與繪製
# ==========================================
st.markdown(f'''
    <div class="main-header">
        <h2>田心救護站 <span style="margin: 0 15px;">|</span> <span>太陽能發電系統</span></h2>
    </div>
''', unsafe_allow_html=True)

col_left, col_right = st.columns([2.5, 1])

with col_left:
    with st.container(border=True):
        st.markdown("<h3 style='margin-bottom: 0;'>| 效能</h3>", unsafe_allow_html=True)
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("⚡ 電流 (目前功率)", current_power)
        m2.metric("📅 今日發電量", today_energy)
        m3.metric("🗓️ 本月發電量", month_energy)
        m4.metric("♾️ 整個使用期發電量", lifetime_energy)

    with st.container(border=True):
        st.markdown("<h3 style='margin-bottom: 0;'>| 功率和電量</h3>", unsafe_allow_html=True)
        st.caption("今日功率 (kW)")
        if not df_chart.empty:
            fig = px.area(df_chart, x="date", y="value", color_discrete_sequence=['#00E676'])
            fig.update_layout(
                margin=dict(l=10, r=10, t=20, b=10),
                height=550, # 【關鍵修改 3】：將圖表高度從 180 大幅提升至 550，填滿下方空白
                xaxis_title=None,
                yaxis_title=None,
                plot_bgcolor='white',
                paper_bgcolor='white',
                font=dict(size=14) # 放大圖表軸線字體
            )
            fig.update_xaxes(showgrid=False)
            fig.update_yaxes(showgrid=True, gridcolor='#E0E0E0', gridwidth=1)
            st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})
        else:
            st.info("今日尚無發電數據，或太陽下山變流器已休眠。")

with col_right:
    with st.container(border=True):
        st.markdown("<h3 style='margin-bottom: 0;'>| 環境效益</h3>", unsafe_allow_html=True)
        st.markdown("<h1 style='text-align: center; color: #78909C; font-size: 6rem; margin-bottom: 20px; margin-top: 40px;'>🏭</h1>", unsafe_allow_html=True)
        st.metric("kg of 節省二氧化碳", co2_saved)
        # 增加一些空行讓右側卡片高度與左側大致對齊
        st.markdown("<br><br><br><br><br><br><br><br>", unsafe_allow_html=True) 

# 底部更新時間
hkt = pytz.timezone('Asia/Hong_Kong')
update_time = datetime.now(hkt).strftime("%Y/%m/%d %p %I:%M:%S")
st.markdown(f"<p style='color: #888888; font-size: 1rem; text-align: right; margin-top: 10px;'>🕒 儀表板最後更新: {update_time}</p>", unsafe_allow_html=True)

# 自動重新整理腳本
components.html(
    """
    <script>
        setTimeout(function(){
            window.parent.location.reload(1);
        }, 300000);
    </script>
    """,
    height=0,
    width=0,
)
