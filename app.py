import streamlit as st
import pandas as pd
import plotly.express as px
import requests
import pytz
import os
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
# 2. SolarEdge API V2 設定與資料抓取函數
#    (V1 已於 2026-11 下線：/overview 與 /envBenefits 已移除、
#     認證改為 HTTP header、路徑改為 /v2/sites/{siteId})
# ==========================================
try:
    API_KEY = st.secrets["SOLAREDGE_API_KEY"]          # Streamlit Cloud
except Exception:
    API_KEY = os.getenv("SOLAREDGE_API_KEY", "")      # 本機測試用環境變數

SITE_ID = '4873924'
BASE_URL = f"https://monitoringapi.solaredge.com/v2/sites/{SITE_ID}"
HEADERS = {"X-API-Key": API_KEY, "Accept": "application/json"}   # V2 用 header，不再用 ?api_key=
HKT = pytz.timezone('Asia/Hong_Kong')

def format_power(w): return f"{w/1000:.2f} kW" if w is not None else "0.00 kW"
def format_energy(wh):
    if wh is None: return "0.00 Wh"
    if wh >= 1_000_000: return f"{wh/1_000_000:.2f} MWh"
    elif wh >= 1000: return f"{wh/1000:.2f} kWh"
    else: return f"{wh:.2f} Wh"

def _iso(dt):
    # V2 要求帶時區的 ISO8601，例如 2026-11-13T00:00:00+08:00
    return dt.isoformat(timespec="seconds")

def _get(path="", **params):
    r = requests.get(f"{BASE_URL}{path}", headers=HEADERS, params=params, timeout=30)
    if r.status_code != 200:
        raise RuntimeError(f"HTTP {r.status_code}: {r.text[:200]}")
    return r.json()

def _sum_energy(start, end, resolution="DAY"):
    # V2 的 /energy 回傳逐區間數值，要自行加總；「from」是 Python 關鍵字，須用 dict 展開
    d = _get("/energy", **{"from": _iso(start), "to": _iso(end),
                           "resolution": resolution, "unit": "WH"})
    return sum(v["value"] for v in (d.get("values") or []) if v.get("value") is not None)

@st.cache_data(ttl=300)
def fetch_solaredge_data():
    now = datetime.now(HKT)
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    month_start = day_start.replace(day=1)

    data = {"power_df": pd.DataFrame(), "current_power_w": None,
            "today_wh": 0.0, "month_wh": 0.0, "lifetime_wh": 0.0, "error": None}
    try:
        # 站點資訊：取安裝日，作為總發電量起算日
        details = _get()
        start_raw = str(details.get("installationDate") or "")[:10]
        life_start = (datetime.fromisoformat(start_raw).replace(tzinfo=HKT)
                      if start_raw else datetime(2009, 1, 1, tzinfo=HKT))

        # 今日功率曲線（15 分鐘區間均值，單位 W）
        power = _get("/power", **{"from": _iso(day_start), "to": _iso(now),
                                  "resolution": "QUARTER_HOUR", "unit": "W"})
        vals = power.get("values") or []
        if vals:
            data["current_power_w"] = next(
                (v["value"] for v in reversed(vals) if v.get("value") is not None), None)
            df = pd.DataFrame(vals).rename(columns={"timestamp": "date"})
            df["date"] = pd.to_datetime(df["date"])
            df["value"] = df["value"].fillna(0).astype(float) / 1000.0
            data["power_df"] = df

        # V2 沒有 /overview，三個發電量分別查詢並加總
        data["today_wh"] = _sum_energy(day_start, now, "DAY")
        data["month_wh"] = _sum_energy(month_start, now, "DAY")
        data["lifetime_wh"] = _sum_energy(life_start, now, "MONTH")
    except Exception as e:
        data["error"] = str(e)   # 不再靜默吞錯，畫面會顯示原因
    return data

api_data = fetch_solaredge_data()
df_chart = api_data["power_df"]

if api_data["error"]:
    st.error(f"SolarEdge 資料讀取失敗：{api_data['error']}")

current_power    = format_power(api_data["current_power_w"])
today_energy     = format_energy(api_data["today_wh"])
month_energy     = format_energy(api_data["month_wh"])
# 🔴 [修正] 舊版多除了一次 100，導致總發電量少顯示 100 倍
lifetime_energy  = f"{api_data['lifetime_wh'] / 1_000_000:,.2f} MWh"

calc_co2 = (api_data["lifetime_wh"] / 1000) * 0.39
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
update_time = datetime.now(HKT).strftime("%Y/%m/%d %p %I:%M:%S")

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
