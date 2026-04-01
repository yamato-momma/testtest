import streamlit as st
import pandas as pd
import google.generativeai as genai
import io
import json

# --- 1. デザイン設定（白背景・黒文字・濃紺アクセント） ---
st.set_page_config(page_title="RaceLog Pro Gemini", layout="wide")
st.markdown("""
    <style>
    .stApp { background-color: #ffffff !important; }
    h1, h2, h3, label, p, span { color: #1e3a8a !important; font-weight: bold !important; }
    .stDataFrame, .stDataEditor { border: 1px solid #1e3a8a; background-color: #ffffff !important; }
    input, textarea { background-color: #f0f2f6 !important; color: #000000 !important; }
    [data-testid="stTable"] td { color: black !important; }
    </style>
    """, unsafe_allow_html=True)

# --- 2. Gemini API 設定 ---
if "GEMINI_API_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
else:
    st.error("Streamlit Secrets に GEMINI_API_KEY が設定されていません。")
    st.stop()

# --- 3. 解析用プロンプト ---
PROMPT = """
添付された「走行試験記録」の画像を解析し、全ての項目を抽出してJSON形式で出力してください。
項目名と数値を正確に一致させてください。

出力フォーマット:
{
  "header": { "No": "", "種目": "", "ドライバー": "", "走行場所": "", "天気": "", "気温": "", "路面温度": "" },
  "table": [ {"Lap": 1, "Time": "", "P_FL": "", "P_FR": "", "T_FL": "", "T_FR": "", "HV": "", "LV": ""} ],
  "feedback": ""
}
"""

def analyze_with_gemini(uploaded_file):
    # 【最重要】NotFound対策：複数のモデル候補を順番に試す
    model_names = ['models/gemini-1.5-flash', 'gemini-1.5-flash', 'models/gemini-pro-vision']
    
    img_data = uploaded_file.getvalue()
    image_parts = [{"mime_type": "image/jpeg", "data": img_data}]
    
    last_error = None
    for m_name in model_names:
        try:
            model = genai.GenerativeModel(model_name=m_name)
            response = model.generate_content([PROMPT, image_parts[0]])
            
            # JSON抽出
            text = response.text
            json_str = text.split("```json")[-1].split("```")[0].strip()
            return json.loads(json_str)
        except Exception as e:
            last_error = e
            continue # 次のモデルを試す
            
    st.error(f"全モデルで接続に失敗しました。最新のエラー: {last_error}")
    return None

# --- 4. メインUI ---
st.title("🏎️ RaceLog Pro: Gemini Engine")

if 'session_data' not in st.session_state:
    st.session_state.session_data = {}

col1, col2 = st.columns([1, 1])

with col1:
    uploaded = st.file_uploader("ログシートを選択", type=["jpg", "png", "jpeg"])
    if uploaded:
        st.image(uploaded, use_container_width=True)
        if st.button("✨ AI解析を実行"):
            with st.spinner("AIが画像と格闘中..."):
                result = analyze_with_gemini(uploaded)
                if result:
                    key = result["header"].get("No") or f"Session_{len(st.session_state.session_data)}"
                    st.session_state.session_data[key] = result
                    st.success("解析成功！")

with col2:
    if st.session_state.session_data:
        selected_no = st.selectbox("Noを選択:", list(st.session_state.session_data.keys()))
        data = st.session_state.session_data[selected_no]
        
        # 編集画面
        st.subheader("データの確認・修正")
        data["header"] = st.data_editor(pd.DataFrame([data["header"]]), hide_index=True).iloc[0].to_dict()
        data["table"] = st.data_editor(pd.DataFrame(data["table"]), hide_index=True, height=400).to_dict('records')
        data["feedback"] = st.text_area("フィードバック", data["feedback"])

# --- 5. Excel出力 ---
if st.session_state.session_data:
    st.divider()
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine='xlsxwriter') as writer:
        for no, d in st.session_state.session_data.items():
            s_name = f"No_{no}".replace("-", "_")[:30]
            pd.DataFrame(list(d["header"].items())).to_excel(writer, sheet_name=s_name, index=False, header=False)
            pd.DataFrame(d["table"]).to_excel(writer, sheet_name=s_name, startrow=len(d["header"])+2, index=False)
    
    st.download_button("📈 Excelダウンロード", buf.getvalue(), "RaceLog_Output.xlsx")
