import streamlit as st
import pandas as pd
import plotly.express as px
import requests
import pytz
from datetime import datetime
import streamlit.components.v1 as components

# ==========================================
# 1. 網頁基本設定 & 電視螢幕最佳化 CSS (極致壓縮垂直空間)
# ==========================================
st.set_page_config(page_title="SolarEdge Dashboard", layout="wide", initial_sidebar_state="collapsed")

st.markdown("""
    <style>
    /* 隱藏預設選單、頂部裝飾條與底部浮水印 */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    
    /* 極致縮減頁面四周的留白 */
    .block-container {
        padding-top: 1rem !important;
        padding-bottom: 0rem !important;
        padding-left: 2rem !important;
        padding-right: 2rem !important;
        max-width: 100% !important;
    }

    /* 頂部深藍色標題列最佳化：壓扁高度並縮減底部 margin */
    .main-header {
        background-color: #1e213a;
        color: white;
        padding: 10px;
        text-align: center;
        border-radius: 8px;
        margin-top: -40px; 
        margin-bottom: 5px; /* 從 15px 縮減至 5px */
        font-family: sans-serif;
    }
    .main-header h2 { margin: 0; font-weight: 600; font-size: 1.6rem; }
    .main-header span { color: #A0A5B5; font-size: 0.9em; font-weight: normal; }
    
    /* 縮減所有垂直區塊之間的間距 (Gap) */
    div[data-testid="stVerticalBlock"] {
        gap: 0.5rem !important;
    }

    /* 卡片背景與邊框設定 */
    div[data-testid="stVerticalBlock"] > div { background-color: #FFFFFF; }
    .stApp { background-color: #F0F2F6; }

    /* 確保數值 (Metric Value) 不會換行且不會被切斷 */
    div[data-testid="stMetricValue"] { 
        font-size: 1.6rem !important; 
        color: #00E676; 
        font-weight: bold; 
        white-space: nowrap !important;
        overflow: visible !important;
    }
    
    /* 確保標題 (Metric Label) 正常顯示 */
    div[data-testid="stMetricLabel"] {
        overflow: visible !important;
        white-space: normal !important;
    }
    div[data-testid="stMetricLabel"] > div > p {
        font-size: 0.85rem !important;
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
        pass # 隱藏電視螢幕上的錯誤提示，保持畫面整潔
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
        <h2>田心救護站 <span style="margin: 0 10px;">|</span> <span>太陽能發電系統</span></h2>
    </div>
''', unsafe_allow_html=True)

col_left, col_right = st.columns([2.2, 1])

with col_left:
    with st.container(border=True):
        st.markdown("**| 效能**")
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("⚡ 電流 (目前功率)", current_power)
        m2.metric("📅 今日發電量", today_energy)
        m3.metric("🗓️ 本月發電量", month_energy)
        m4.metric("♾️ 總發電量", lifetime_energy)

    with st.container(border=True):
        st.markdown("**| 功率和電量**")
        st.caption("今日功率 (kW)")
        if not df_chart.empty:
            fig = px.area(df_chart, x="date", y="value", color_discrete_sequence=['#00E676'])
            fig.update_layout(
                margin=dict(l=0, r=0, t=10, b=0),
                height=180, # 【關鍵修改】：將高度降至 180，確保電視絕對能顯示完整 X 軸
                xaxis_title=None,
                yaxis_title=None,
                plot_bgcolor='white',
                paper_bgcolor='white'
            )
            fig.update_xaxes(showgrid=False)
            fig.update_yaxes(showgrid=True, gridcolor='#E0E0E0', gridwidth=1)
            # 【關鍵修改】：隱藏 Plotly 的浮動工具列 (displayModeBar: False)
            st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})
        else:
            st.info("今日尚無發電數據，或太陽下山變流器已休眠。")

with col_right:
    with st.container(border=True):
        st.markdown("**| 環境效益**")
        st.markdown("<h1 style='text-align: center; color: #78909C; margin-bottom: 5px; margin-top: 10px;'>🏭</h1>", unsafe_allow_html=True)
        st.metric("kg of 節省二氧化碳", co2_saved)
        st.markdown("<br>", unsafe_allow_html=True)

# 底部更新時間
hkt = pytz.timezone('Asia/Hong_Kong')
update_time = datetime.now(hkt).strftime("%Y/%m/%d %p %I:%M:%S")
st.markdown(f"<p style='color: #888888; font-size: 0.8em; margin-top: -5px;'>🕒 儀表板最後更新: {update_time}</p>", unsafe_allow_html=True)

# 自動重新整理腳本 (每 300,000 毫秒 = 5 分鐘)
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
