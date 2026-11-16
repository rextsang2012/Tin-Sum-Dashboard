import streamlit as st
import pandas as pd
import plotly.express as px
import requests
import pytz
import os
from datetime import datetime, timedelta
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
# 2. SolarEdge API V2 —「省 credit」資料層
#
#    ⚠️ V2 為 credit 制：每次 API 呼叫 = 1 credit，免費版每月僅 2,000 credits。
#    本版策略（約 1,300 credits/月，含安全餘量）：
#      ① 快資料（今日曲線+目前功率+今日電量）：只用 1 次呼叫
#         → /energy?resolution=QUARTER_HOUR 一魚三吃（曲線=每格Wh÷0.25h、
#           今日總量=sum、目前功率=最後一個完整 15 分鐘格）
#      ② 慢資料（本月+總發電量）：每 12 小時才查 1 輪（2 次呼叫）
#      ③ 安裝日直接寫死，省掉 site details 呼叫
#      ④ 夜間（19:00–06:00）不呼叫 API，沿用日間最後數據
# ==========================================
try:
    API_KEY = st.secrets["SOLAREDGE_API_KEY"]          # Streamlit Cloud
except Exception:
    API_KEY = os.getenv("SOLAREDGE_API_KEY", "")      # 本機測試用環境變數

SITE_ID = '4873924'
BASE_URL = f"https://monitoringapi.solaredge.com/v2/sites/{SITE_ID}"
HEADERS = {"X-API-Key": API_KEY, "Accept": "application/json"}
HKT = pytz.timezone('Asia/Hong_Kong')

# ===== 可調參數（改這裡即可，注意 credit 消耗）=====
FAST_TTL   = 21 * 60       # 快資料快取秒數（21 分鐘 ≈ 每 20 分鐘 1 次呼叫）
SLOW_TTL   = 12 * 3600     # 慢資料快取秒數（12 小時）
DAY_START_HOUR = 6         # 白天抓資料時段（本地時間）
DAY_END_HOUR   = 19        # 之後為夜間模式：不耗 credit，沿用最後數據
INSTALL_DATE   = "2026-05-07"   # 田心救護站安裝日（寫死可省 1 credit/次）
# 消耗估算：白天 13h × 3 次/h + 慢資料 4 次/日 ≈ 43 credits/日 ≈ 1,300/月
# 若升級付費方案（如 Business Starter $100/月 = 20,000 credits），
# 可把 FAST_TTL 降為 301（每 5 分鐘）並把 DAY 時段拉長，即時性更好。

# 夜間模式用：保留當日最後一次成功數據（程序重啟後會清空，屆時顯示待機）
_LAST_GOOD = {}

def format_power(w): return f"{w/1000:.2f} kW" if w is not None else "0.00 kW"
def format_energy(wh):
    if wh is None: return "0.00 Wh"
    if wh >= 1_000_000: return f"{wh/1_000_000:.2f} MWh"
    elif wh >= 1000: return f"{wh/1000:.2f} kWh"
    else: return f"{wh:.2f} Wh"

def _iso(dt):
    # V2 要求帶時區的 ISO8601，例如 2026-11-16T00:00:00+08:00
    return dt.isoformat(timespec="seconds")

def _get(path="", **params):
    r = requests.get(f"{BASE_URL}{path}", headers=HEADERS, params=params, timeout=30)
    if r.status_code == 429:
        if "Monthly credit" in r.text:
            raise RuntimeError(
                "本月 SolarEdge API 額度已用盡（免費版每月 2,000 credits），"
                "將於計費週期重置後自動恢復。詳情見 developer.solaredge.com → Settings → Plans。")
        raise RuntimeError(f"API 速率限制（429），請稍後再試：{r.text[:150]}")
    if r.status_code != 200:
        raise RuntimeError(f"HTTP {r.status_code}: {r.text[:200]}")
    return r.json()

def _sum_energy(start, end, resolution):
    # 「from」是 Python 關鍵字，須用 dict 展開
    d = _get("/energy", **{"from": _iso(start), "to": _iso(end),
                           "resolution": resolution, "unit": "WH"})
    return sum(v["value"] for v in (d.get("values") or []) if v.get("value") is not None)

@st.cache_data(ttl=FAST_TTL)
def fetch_fast():
    """快資料：1 次 API 呼叫，同時取回今日曲線 / 今日電量 / 目前功率。"""
    now = datetime.now(HKT)
    data = {"power_df": pd.DataFrame(), "current_power_w": None,
            "today_wh": 0.0, "night": False, "error": None}
    try:
        if not (DAY_START_HOUR <= now.hour < DAY_END_HOUR):
            data["night"] = True            # 夜間：完全不呼叫 API
            return data

        day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        d = _get("/energy", **{"from": _iso(day_start), "to": _iso(now),
                               "resolution": "QUARTER_HOUR", "unit": "WH"})
        vals = [v for v in (d.get("values") or []) if v.get("value") is not None]
        if vals:
            data["today_wh"] = sum(v["value"] for v in vals)
            # 目前功率：用最後一個「完整」的 15 分鐘格（Wh ÷ 0.25h = W）
            complete = [v for v in vals
                        if datetime.fromisoformat(v["timestamp"]) <= now - timedelta(minutes=15)]
            last = complete[-1] if complete else vals[-1]
            data["current_power_w"] = last["value"] / 0.25
            # 曲線：每格 15 分鐘平均功率（kW）＝ Wh ÷ 0.25h ÷ 1000
            df = pd.DataFrame(d.get("values") or []).rename(columns={"timestamp": "date"})
            df["date"] = pd.to_datetime(df["date"])
            df["value"] = df["value"].fillna(0).astype(float) / 250.0
            data["power_df"] = df
    except Exception as e:
        data["error"] = str(e)
    return data

@st.cache_data(ttl=SLOW_TTL)
def fetch_slow():
    """慢資料：每 12 小時 2 次呼叫（本月電量 + 總發電量）。"""
    now = datetime.now(HKT)
    data = {"month_wh": 0.0, "lifetime_wh": 0.0, "error": None}
    try:
        month_start = now.replace(hour=0, minute=0, second=0, microsecond=0, day=1)
        life_start = datetime.fromisoformat(INSTALL_DATE).replace(tzinfo=HKT)
        data["month_wh"] = _sum_energy(month_start, now, "DAY")
        data["lifetime_wh"] = _sum_energy(life_start, now, "MONTH")
    except Exception as e:
        data["error"] = str(e)
    return data

fast = fetch_fast()
slow = fetch_slow()

# 夜間模式：沿用當日最後一次成功數據，畫面不會歸零
today_key = datetime.now(HKT).strftime("%Y-%m-%d")
if fast["night"] and today_key in _LAST_GOOD:
    fast = _LAST_GOOD[today_key]
elif not fast["night"] and fast["error"] is None:
    _LAST_GOOD[today_key] = fast

if fast["error"]:
    st.error(f"SolarEdge 資料讀取失敗：{fast['error']}")
if slow["error"]:
    st.warning(f"本月/總發電量暫時無法更新：{slow['error']}")

current_power    = format_power(fast["current_power_w"])
today_energy     = format_energy(fast["today_wh"])
month_energy     = format_energy(slow["month_wh"])
lifetime_energy  = f"{slow['lifetime_wh'] / 1_000_000:,.2f} MWh"

calc_co2 = (slow["lifetime_wh"] / 1000) * 0.39
co2_saved = f"{calc_co2:,.1f}"

df_chart = fast["power_df"]

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

# 自動重新整理腳本 — 與 FAST_TTL 對齊：20 分鐘 = 1,200,000 毫秒
components.html(
    """
    <script>
        setTimeout(function(){
            window.parent.location.reload(1);
        }, 1200000);
    </script>
    """,
    height=0,
    width=0,
)
