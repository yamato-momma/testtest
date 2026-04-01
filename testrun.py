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
        # 【解決策】モデルのフルパスを明示的に指定
        model = genai.GenerativeModel(model_name='gemini-1.5-flash')
        
        img_data = uploaded_file.getvalue()
        
        # 解析実行
        response = model.generate_content([
            PROMPT,
            {'mime_type': 'image/jpeg', 'data': img_data}
        ])
        
        text = response.text
        # JSONを抽出
        start_idx = text.find('{')
        end_idx = text.rfind('}') + 1
        json_str = text[start_idx:end_idx]
        return json.loads(json_str)
        
    except Exception as e:
        # 詳細なエラーを画面に出す
        st.error(f"解析エラー詳細: {e}")
        return None

# --- 4. メインUI ---
st.title("🏎️ RaceLog Pro: Gemini Engine")

if 'session_data' not in st.session_state:
    st.session_state.session_data = {}

uploaded = st.file_uploader("ログシートを選択", type=["jpg", "png", "jpeg"])
if uploaded:
    if st.button("✨ AI解析を実行"):
        with st.spinner("AIが通信プロトコルを確立中..."):
            result = analyze_with_gemini(uploaded)
            if result:
                key = result["header"].get("No") or f"Session_{len(st.session_state.session_data)}"
                st.session_state.session_data[key] = result
                st.success("解析成功！")

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

    # Excel出力
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine='xlsxwriter') as writer:
        for no, d in st.session_state.session_data.items():
            s_name = f"No_{no}".replace("-", "_")[:30]
            pd.DataFrame(list(d["header"].items())).to_excel(writer, sheet_name=s_name, index=False, header=False)
            pd.DataFrame(d["table"]).to_excel(writer, sheet_name=s_name, startrow=len(d["header"])+2, index=False)
    
    st.download_button("📈 Excelを一括ダウンロード", buf.getvalue(), "RaceLog_Output.xlsx")
