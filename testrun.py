import streamlit as st
import pandas as pd
import google.generativeai as genai
import io
import json

# --- 1. デザイン設定（白背景・黒文字・プロ仕様） ---
st.set_page_config(page_title="RaceLog Pro Gemini", layout="wide")
st.markdown("""
    <style>
    .stApp { background-color: #ffffff !important; }
    h1, h2, h3, label, p, span { color: #1e3a8a !important; font-weight: bold !important; }
    .stTabs [data-baseweb="tab"] { font-size: 1.2rem; font-weight: bold; }
    .stDataEditor { border: 1px solid #1e3a8a; }
    </style>
    """, unsafe_allow_html=True)

# --- 2. Gemini API 設定 ---
if "GEMINI_API_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
else:
    st.error("Secretsに GEMINI_API_KEY を設定してください。")
    st.stop()

# --- 3. 解析用プロンプト（構造化を強化） ---
PROMPT = """
走行試験記録の画像を解析し、以下の項目を正確に抽出してJSON形式で出力してください。
タイヤデータはFL, FR, RL, RRの4箇所について、内圧、表面温度、ディスク温度をそれぞれ抽出してください。

{
  "header": { "No": "", "種目": "", "ドライバー": "", "走行場所": "", "天気": "", "気温": "", "路面温度": "" },
  "laps": [ {"Lap": 1, "Time": "", "HV": "", "LV": ""} ],
  "tire_data": {
    "FL": [ {"Lap": 1, "Pressure": "", "SurfaceTemp": "", "DiskTemp": ""} ],
    "FR": [ {"Lap": 1, "Pressure": "", "SurfaceTemp": "", "DiskTemp": ""} ],
    "RL": [ {"Lap": 1, "Pressure": "", "SurfaceTemp": "", "DiskTemp": ""} ],
    "RR": [ {"Lap": 1, "Pressure": "", "SurfaceTemp": "", "DiskTemp": ""} ]
  },
  "feedback": ""
}
"""

def analyze_with_gemini(uploaded_file):
    try:
        model = genai.GenerativeModel('gemini-1.5-flash')
        img_data = uploaded_file.getvalue()
        response = model.generate_content([PROMPT, {'mime_type': 'image/jpeg', 'data': img_data}])
        
        text = response.text
        start_idx = text.find('{')
        end_idx = text.rfind('}') + 1
        return json.loads(text[start_idx:end_idx])
    except Exception as e:
        st.error(f"解析エラー: {e}")
        return None

# --- 4. メインUI ---
st.title("🏎️ RaceLog Pro: 4輪データ集中管理")

if 'session_data' not in st.session_state:
    st.session_state.session_data = {}

uploaded = st.file_uploader("ログシートを選択", type=["jpg", "png", "jpeg"])
if uploaded:
    if st.button("✨ 精密解析を実行"):
        with st.spinner("4輪のデータを個別に抽出中..."):
            result = analyze_with_gemini(uploaded)
            if result:
                key = result["header"].get("No") or f"Session_{len(st.session_state.session_data)}"
                st.session_state.session_data[key] = result
                st.success(f"解析成功！ No.{key}")

if st.session_state.session_data:
    selected_no = st.selectbox("確認・修正するNo:", list(st.session_state.session_data.keys()))
    data = st.session_state.session_data[selected_no]
    
    # タブ分けで視認性を向上
    tab_h, tab_l, tab_t, tab_f = st.tabs(["📋 基本情報", "⏱️ ラップタイム", "🛞 タイヤ・ブレーキ詳細", "💬 フィードバック"])
    
    with tab_h:
        data["header"] = st.data_editor(pd.DataFrame([data["header"]]), hide_index=True).iloc[0].to_dict()
    
    with tab_l:
        st.subheader("ラップタイム & 電圧")
        data["laps"] = st.data_editor(pd.DataFrame(data["laps"]), hide_index=True, height=500).to_dict('records')
    
    with tab_t:
        st.subheader("4輪個別データ")
        cols = st.columns(2)
        for i, pos in enumerate(["FL", "FR", "RL", "RR"]):
            with cols[i % 2]:
                st.write(f"### {pos} (Front Left等)")
                df_pos = pd.DataFrame(data["tire_data"][pos])
                data["tire_data"][pos] = st.data_editor(df_pos, hide_index=True, key=f"edit_{pos}_{selected_no}").to_dict('records')

    with tab_f:
        data["feedback"] = st.text_area("ドライバーフィードバック", data["feedback"], height=200)

    # Excel出力（シート内でも表を分けて配置）
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine='xlsxwriter') as writer:
        for no, d in st.session_state.session_data.items():
            s_name = f"No_{no}".replace("-", "_")[:31]
            # 1. 基本情報
            pd.DataFrame(list(d["header"].items())).to_excel(writer, sheet_name=s_name, index=False, header=False)
            # 2. ラップタイム (横に並べる)
            pd.DataFrame(d["laps"]).to_excel(writer, sheet_name=s_name, startrow=len(d["header"])+2, index=False)
            # 3. 各タイヤの表を縦に並べて出力
            current_row = len(d["header"]) + len(d["laps"]) + 5
            for pos in ["FL", "FR", "RL", "RR"]:
                st.write(f"Exporting {pos}...") # デバッグ用
                pd.DataFrame([{"タイヤ位置": pos}]).to_excel(writer, sheet_name=s_name, startrow=current_row, index=False, header=False)
                pd.DataFrame(d["tire_data"][pos]).to_excel(writer, sheet_name=s_name, startrow=current_row+1, index=False)
                current_row += len(d["tire_data"][pos]) + 3
    
    st.download_button("📈 タイヤ別Excelをダウンロード", buf.getvalue(), f"RaceLog_Detailed_{selected_no}.xlsx")
