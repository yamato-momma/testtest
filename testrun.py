import streamlit as st
import pandas as pd
import google.generativeai as genai
import io
import json

# --- 1. デザイン設定（白背景・黒文字） ---
st.set_page_config(page_title="RaceLog Pro Gemini", layout="wide")
st.markdown("""
    <style>
    .stApp { background-color: #ffffff !important; }
    h1, h2, h3, label, p, span { color: #1e3a8a !important; font-weight: bold !important; }
    input, textarea { background-color: #f0f2f6 !important; color: #000000 !important; }
    [data-testid="stTable"] td { color: black !important; }
    </style>
    """, unsafe_allow_html=True)

# --- 2. Gemini API 設定 ---
if "GEMINI_API_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
else:
    st.error("Secretsに GEMINI_API_KEY を設定してください。")
    st.stop()

# --- 3. 解析用プロンプト ---
PROMPT = """
走行試験記録の画像を解析し、全ての項目を抽出してJSON形式で出力してください。
{
  "header": { "No": "", "種目": "", "ドライバー": "", "走行場所": "", "天気": "", "気温": "", "路面温度": "" },
  "table": [ {"Lap": 1, "Time": "", "P_FL": "", "P_FR": "", "T_FL": "", "T_FR": "", "HV": "", "LV": ""} ],
  "feedback": ""
}
"""

def analyze_with_gemini(uploaded_file):
    try:
        # 【解決策】利用可能なモデルをリストアップし、1.5-flash または最新版を自動選択
        available_models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        
        # 優先順位をつけてモデルを選択
        target_model = None
        for m in ["models/gemini-1.5-flash", "models/gemini-1.5-pro", "models/gemini-pro-vision"]:
            if m in available_models:
                target_model = m
                break
        
        if not target_model:
            target_model = available_models[0] # 何でもいいから動くものを選ぶ

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
st.title("🏎️ RaceLog Pro: Gemini Engine")

if 'session_data' not in st.session_state:
    st.session_state.session_data = {}

uploaded = st.file_uploader("ログシートを選択", type=["jpg", "png", "jpeg"])
if uploaded:
    if st.button("✨ AI解析を実行"):
        with st.spinner("利用可能な最新AIモデルを探索して解析中..."):
            result = analyze_with_gemini(uploaded)
            if result:
                key = result["header"].get("No") or f"Session_{len(st.session_state.session_data)}"
                st.session_state.session_data[key] = result
                st.success(f"解析成功！ (使用モデル: {key})")

if st.session_state.session_data:
    selected_no = st.selectbox("確認・修正するNo:", list(st.session_state.session_data.keys()))
    data = st.session_state.session_data[selected_no]
    
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("基本情報")
        data["header"] = st.data_editor(pd.DataFrame([data["header"]]), hide_index=True).iloc[0].to_dict()
    with col2:
        st.subheader("フィードバック")
        data["feedback"] = st.text_area("内容", data["feedback"], height=100)
    
    st.subheader("詳細データ（タイム・内圧など）")
    data["table"] = st.data_editor(pd.DataFrame(data["table"]), hide_index=True, height=400).to_dict('records')

    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine='xlsxwriter') as writer:
        for no, d in st.session_state.session_data.items():
            s_name = f"No_{no}".replace("-", "_")[:30]
            pd.DataFrame(list(d["header"].items())).to_excel(writer, sheet_name=s_name, index=False, header=False)
            pd.DataFrame(d["table"]).to_excel(writer, sheet_name=s_name, startrow=len(d["header"])+2, index=False)
    
    st.download_button("📈 Excelを一括ダウンロード", buf.getvalue(), "RaceLog_Output.xlsx")
