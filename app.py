import streamlit as st
import pandas as pd
import plotly.express as px
import requests
import pytz
from datetime import datetime
import streamlit.components.v1 as components

# ==========================================
# 1. 網頁基本設定 & CSS 樣式
# ==========================================
st.set_page_config(page_title="SolarEdge Dashboard", layout="wide", initial_sidebar_state="collapsed")

st.markdown("""
    <style>
    /* 隱藏預設選單、頂部裝飾條 */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    
    /* 隱藏滑鼠游標 (適用於 Wayland Kiosk 模式) */
    * { cursor: none !important; }
    
    /* 調整頁面四周留白 */
    .block-container {
        padding-top: 2rem !important;
        padding-bottom: 2rem !important;
        padding-left: 3rem !important;
        padding-right: 3rem !important;
        max-width: 100% !important;
    }

    /* --- 頂部深藍色標題列 --- */
    .main-header {
        background-color: #1e213a;
        color: white;
        padding: 30px; 
        text-align: center;
        border-radius: 8px;
        margin-top: -30px; 
        margin-bottom: 30px;
        font-family: sans-serif;
    }
    
    /* 🔴 [電視專用調整] 頂部主標題 (田心救護站) 字體大小 */
    .main-header h2 { margin: 0; font-weight: 600; font-size: 6rem; }
    
    /* 🔴 [電視專用調整] 頂部副標題 (太陽能發電系統) 字體大小 */
    .main-header span { color: #A0A5B5; font-size: 6rem; font-weight: normal; }
    
    /* 卡片背景與邊框設定 */
    div[data-testid="stVerticalBlock"] > div { background-color: #FFFFFF; }
    .stApp { background-color: #F0F2F6; }

    /* --- 數據顯示區 (Metrics) --- */
    
    /* 🔴 [電視專用調整] 數據的數值大小 (例如 0.00 kW, 6.76 kWh 的綠色大數字) */
    div[data-testid="stMetricValue"] { 
        font-size: 7rem !important; /* 稍微調整讓畫面更平衡，若要更大可改為 8rem */
        color: #00E676; 
        font-weight: bold; 
        white-space: nowrap !important;
        overflow: visible !important;
        padding-top: 15px;
        padding-bottom: 15px;
    }
    
    /* 🔴 [電視專用調整] 數據的標題大小 (例如 "今日發電量" 這行字) 
       (備註: 已修正 Streamlit 選擇器，現在會確實生效) */
    [data-testid="stMetricLabel"] * {
        font-size: 3.5rem !important; /* 原本因選擇器失效所以字很小，現在改為 3.5rem，若不夠大可繼續上調至 4rem */
        white-space: normal !important;
        text-overflow: clip !important;
        color: #555555;
        font-weight: bold;
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
        <h2>田心救護站 <span style="margin: 0 20px;">|</span> <span>太陽能發電系統</span></h2>
    </div>
''', unsafe_allow_html=True)

col_left, col_right = st.columns([2.5, 1])

with col_left:
    with st.container(border=True):
        # 🔴 [電視專用調整] 區塊標題字體大小 (例如 "| 效能") -> 已調整為 4.5rem
        st.markdown("<h2 style='margin-bottom: 0; font-size: 4.5rem;'>| 效能</h2>", unsafe_allow_html=True)
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("⚡ 電流 (目前功率)", current_power)
        m2.metric("📅 今日發電量", today_energy)
        m3.metric("🗓️ 本月發電量", month_energy)
        m4.metric("♾️ 總發電量", lifetime_energy) # 稍微縮短標題以避免電視螢幕文字斷行

    with st.container(border=True):
        # 🔴 [電視專用調整] 區塊標題字體大小 (例如 "| 功率和電量") -> 已統一調整為 4.5rem
        st.markdown("<h2 style='margin-bottom: 0; font-size: 4.5rem;'>| 功率和電量</h2>", unsafe_allow_html=True)
        
        # 🔴 [電視專用調整] 圖表上方的附註字體大小 ("今日功率 (kW)") -> 已調整為 3rem
        st.markdown("<p style='color: #666; font-size: 3.5rem; margin-top: 10px; margin-bottom: 0;'>今日功率 (kW)</p>", unsafe_allow_html=True)
        
        if not df_chart.empty:
            fig = px.area(df_chart, x="date", y="value", color_discrete_sequence=['#00E676'])
            fig.update_layout(
                margin=dict(l=20, r=20, t=20, b=20),
                # 🔴 [電視專用調整] 圖表的整體高度 
                height=850, 
                xaxis_title=None,
                yaxis_title=None,
                plot_bgcolor='white',
                paper_bgcolor='white',
                # 🔴 [電視專用調整] 圖表 X軸與Y軸的數字大小 -> 已從 22 放大至 36
                font=dict(size=36) 
            )
            fig.update_xaxes(showgrid=False)
            fig.update_yaxes(showgrid=True, gridcolor='#E0E0E0', gridwidth=1)
            st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})
        else:
            # 🔴 [電視專用調整] 提示訊息字體放大
            st.markdown("<p style='font-size: 3rem; color: #888;'>今日尚無發電數據，或太陽下山變流器已休眠。</p>", unsafe_allow_html=True)

with col_right:
    with st.container(border=True):
        # 🔴 [電視專用調整] 區塊標題字體大小 (例如 "| 環境效益") -> 已調整為 4.5rem (與左側統一)
        st.markdown("<h2 style='margin-bottom: 0; font-size: 4.5rem;'>| 環境效益</h2>", unsafe_allow_html=True)
        
        # 🔴 [電視專用調整] 工廠圖示的大小
        st.markdown("<h1 style='text-align: center; color: #78909C; font-size: 20rem; margin-bottom: 40px; margin-top: 80px;'>🏭</h1>", unsafe_allow_html=True)
        
        st.metric("🌱 節省二氧化碳 (kg)", co2_saved)
        
        # 🔴 [電視專用調整] 加入隱形換行符號以平衡左右兩側的卡片高度
        st.markdown("<br><br><br><br><br><br><br><br><br><br><br>", unsafe_allow_html=True) 

# 底部更新時間
hkt = pytz.timezone('Asia/Hong_Kong')
update_time = datetime.now(hkt).strftime("%Y/%m/%d %p %I:%M:%S")
# 🔴 [電視專用調整] 底部更新時間的字體大小 -> 已從 1.5rem 放大至 2.5rem
st.markdown(f"<p style='color: #888888; font-size: 2.5rem; text-align: right; margin-top: 15px;'>🕒 儀表板最後更新: {update_time}</p>", unsafe_allow_html=True)

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
