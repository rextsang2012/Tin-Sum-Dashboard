import streamlit as st
import pandas as pd
import plotly.express as px
import requests
import pytz
from datetime import datetime
import streamlit.components.v1 as components

# ==========================================
# 1. 網頁基本設定 & CSS 樣式 (電視全螢幕滿版比例)
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
    
    /* 🔴 [佈局調整] 極小化邊緣留白，讓內容盡量向外擴張 */
    .block-container {
        padding-top: 1rem !important;
        padding-bottom: 1rem !important;
        padding-left: 2rem !important;
        padding-right: 2rem !important;
        max-width: 100% !important;
    }

    /* --- 頂部深藍色標題列 --- */
    .main-header {
        background-color: #1e213a;
        color: white;
        padding: 40px; 
        text-align: center;
        border-radius: 8px;
        margin-top: -60px; 
        margin-bottom: 30px;
        font-family: sans-serif;
    }
    
    /* 🔴 [字體放大] 頂部主標題字體大小 (田心救護站) */
    .main-header h2 { margin: 0; font-weight: 600; font-size: 6rem; }
    
    /* 🔴 [字體放大] 頂部副標題字體大小 (太陽能發電系統) */
    .main-header span { color: #A0A5B5; font-size: 5rem; font-weight: normal; }
    
    /* 卡片背景與邊框設定 */
    div[data-testid="stVerticalBlock"] > div { background-color: #FFFFFF; }
    .stApp { background-color: #F0F2F6; }

    /* --- 數據顯示區 (Metrics) --- */
    
    /* 🔴 [字體放大] 數據的標題大小 (例如 "今日發電量" 這行字) */
    [data-testid="stMetricLabel"] p {
        font-size: 3.5rem !important; 
        color: #555555 !important;
        font-weight: bold !important;
        white-space: nowrap !important;
    }

    /* 🔴 [字體放大] 數據的數值大小 (例如 0.00 kW, 6.76 kWh 的數字) */
    [data-testid="stMetricValue"] {
        font-size: 5.5rem !important; 
        color: #00E676 !important; 
        font-weight: bold !important;
        padding-top: 20px !important;
        padding-bottom: 20px !important;
        white-space: nowrap !important;
    }
    
    </style>
""", unsafe_allow_html=True)

# ==========================================
# 2. SolarEdge API 設定與資料抓取函數
# ==========================================
API_KEY = st.secrets["SOLAREDGE_API_KEY"]
SITE_ID = '4873924'
BASE_URL = f"https://monitoringapi.solaredge.com/site/{SITE_ID}"

def format_power(w): return f"{w/1000:.2f} kW" if w is not None else "0.00 kW"
def format_energy(wh):
    if wh is None: return "0.00 Wh"
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
        # 🔴 [字體放大] 區塊標題字體大小 ("| 效能")
        st.markdown("<h2 style='margin-bottom: 20px; font-size: 3rem; color: #333;'>| 效能</h2>", unsafe_allow_html=True)
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("⚡ 電流 (目前功率)", current_power)
        m2.metric("📅 今日發電量", today_energy)
        m3.metric("🗓️ 本月發電量", month_energy)
        m4.metric("♾️ 總發電量", lifetime_energy)

    with st.container(border=True):
        # 🔴 [字體放大] 區塊標題字體大小 ("| 功率和電量")
        st.markdown("<h2 style='margin-bottom: 5px; font-size: 3rem; color: #333;'>| 功率和電量</h2>", unsafe_allow_html=True)
        
        # 🔴 [字體放大] 圖表上方的附註字體大小
        st.markdown("<p style='color: #666; font-size: 2rem; margin-bottom: 20px;'>今日功率 (kW)</p>", unsafe_allow_html=True)
        
        if not df_chart.empty:
            fig = px.area(df_chart, x="date", y="value", color_discrete_sequence=['#00E676'])
            
            # 處理夜間無數據或逆變器休眠情況 (防止圖表縮成一條線)
            max_value = df_chart['value'].max()
            y_axis_max = max_value * 1.1 if max_value > 0 else 5.0  

            fig.update_layout(
                margin=dict(l=80, r=50, t=30, b=80), 
                # 🔴 [消除留白關鍵] 將圖表高度拉長至 850，以填滿螢幕下方空間
                height=850, 
                xaxis_title=None,
                yaxis_title=None,
                plot_bgcolor='white',
                paper_bgcolor='white'
            )
            
            fig.update_xaxes(
                showgrid=False,
                # 🔴 [字體放大] X 軸時間文字大小 
                tickfont=dict(size=32, color='#555'),
                tickformat="%H:%M" 
            )
            
            fig.update_yaxes(
                showgrid=True, 
                gridcolor='#E0E0E0', 
                gridwidth=2,
                range=[0, y_axis_max], 
                # 🔴 [字體放大] Y 軸數值文字大小
                tickfont=dict(size=32, color='#555')
            )
            st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})
        else:
            st.info("今日尚無發電數據。")

with col_right:
    with st.container(border=True):
        # 🔴 [字體放大] 區塊標題字體大小 ("| 環境效益")
        st.markdown("<h2 style='margin-bottom: 0; font-size: 3rem; color: #333;'>| 環境效益</h2>", unsafe_allow_html=True)
        
        # 🔴 [消除留白關鍵] 大幅增加工廠圖示的大小，並增加 margin-top/bottom 將右側空間撐開，對齊左側 850px 的圖表
        st.markdown("<h1 style='text-align: center; font-size: 24rem; margin-bottom: 80px; margin-top: 150px;'>🏭</h1>", unsafe_allow_html=True)
        
        st.metric("🌱 節省二氧化碳 (kg)", co2_saved)
        
        # 底部加入彈性空間以完美貼齊
        st.markdown("<br>"*5, unsafe_allow_html=True) 

# 底部更新時間
hkt = pytz.timezone('Asia/Hong_Kong')
update_time = datetime.now(hkt).strftime("%Y/%m/%d %p %I:%M:%S")

# 🔴 [字體放大] 底部更新時間的字體大小
st.markdown(f"<p style='color: #888888; font-size: 1.8rem; text-align: right; margin-top: 10px;'>🕒 儀表板最後更新: {update_time}</p>", unsafe_allow_html=True)

# 自動重新整理腳本 (5分鐘 = 300000 毫秒)
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
