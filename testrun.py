import streamlit as st
import pandas as pd
import google.generativeai as genai
import io
import json

# --- 1. デザイン設定 ---
st.set_page_config(page_title="TUFT Rog R", layout="wide")
st.markdown("""
    <style>
    .stApp { background-color: #ffffff !important; }
    h1, h2, h3, label, p, span { color: #1e3a8a !important; font-weight: bold !important; }
    input, textarea { background-color: #f0f2f6 !important; color: #000000 !important; border: 1px solid #1e3a8a !important; }
    </style>
    """, unsafe_allow_html=True)

# --- 2. Gemini API 設定 ---
if "GEMINI_API_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
else:
    st.error("Secretsに GEMINI_API_KEY を設定してください．")
    st.stop()

# --- 3. 解析用プロンプト ---
PROMPT = """
走行試験記録の画像を解析し，全ての項目を抽出してJSON形式で出力してください．
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
        # 【解決策】現在利用可能なモデルをリストアップし，動くものを自動選択
        models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        
        # 優先順位：1.5-flash -> 1.5-pro -> その他
        target_model = next((m for m in models if "1.5-flash" in m), 
                            next((m for m in models if "1.5-pro" in m), models[0]))
        
        model = genai.GenerativeModel(model_name=target_model)
        
        img_data = uploaded_file.getvalue()
        response = model.generate_content([
            PROMPT,
            {'mime_type': 'image/jpeg', 'data': img_data}
        ])
        
        text = response.text
        start_idx = text.find('{')
        end_idx = text.rfind('}') + 1
        return json.loads(text[start_idx:end_idx])
    except Exception as e:
        st.error(f"解析エラー詳細: {e}")
        return None

# --- 4. メインUI ---
st.title("🏎️ RaceLog Pro: Gemini Engine v7")

if 'session_data' not in st.session_state:
    st.session_state.session_data = {}

uploaded = st.file_uploader("ログシートを選択", type=["jpg", "png", "jpeg"])
if uploaded:
    if st.button("実行"):
        with st.spinner("解析中..."):
            result = analyze_with_gemini(uploaded)
            if result:
                key = result["header"].get("No") or f"Session_{len(st.session_state.session_data)}"
                st.session_state.session_data[key] = result
                st.success(f"解析成功！")

if st.session_state.session_data:
    selected_no = st.selectbox("確認・修正するNo:", list(st.session_state.session_data.keys()))
    data = st.session_state.session_data[selected_no]
    
    tab_h, tab_l, tab_t, tab_f = st.tabs(["📋 基本情報", "⏱️ ラップタイム", "🛞 4輪個別詳細", "💬 フィードバック"])
    
    with tab_h:
        data["header"] = st.data_editor(pd.DataFrame([data["header"]]), hide_index=True).iloc[0].to_dict()
    with tab_l:
        data["laps"] = st.data_editor(pd.DataFrame(data["laps"]), hide_index=True, height=400).to_dict('records')
    with tab_t:
        col_f, col_r = st.columns(2)
        for i, pos in enumerate(["FL", "FR", "RL", "RR"]):
            with (col_f if i < 2 else col_r):
                st.write(f"### 🛞 {pos}")
                df_pos = pd.DataFrame(data["tire_data"][pos])
                data["tire_data"][pos] = st.data_editor(df_pos, hide_index=True, key=f"{pos}_{selected_no}").to_dict('records')
    with tab_f:
        data["feedback"] = st.text_area("内容", data["feedback"], height=200)

    # Excel出力
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine='xlsxwriter') as writer:
        for no, d in st.session_state.session_data.items():
            s_name = f"No_{no}".replace("-", "_")[:31]
            pd.DataFrame(list(d["header"].items())).to_excel(writer, sheet_name=s_name, index=False, header=False)
            pd.DataFrame(d["laps"]).to_excel(writer, sheet_name=s_name, startrow=len(d["header"])+2, index=False)
            curr_row = len(d["header"]) + len(d["laps"]) + 5
            for pos in ["FL", "FR", "RL", "RR"]:
                pd.DataFrame([{"タイヤ位置": pos}]).to_excel(writer, sheet_name=s_name, startrow=curr_row, index=False, header=False)
                pd.DataFrame(d["tire_data"][pos]).to_excel(writer, sheet_name=s_name, startrow=curr_row+1, index=False)
                curr_row += len(d["tire_data"][pos]) + 3
    
    st.download_button("📈 Excelダウンロード", buf.getvalue(), f"Log_{selected_no}.xlsx")
