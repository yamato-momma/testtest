import streamlit as st
import pandas as pd
import google.generativeai as genai
import io
import json

# --- 1. デザイン設定（白背景に黒文字を絶対維持） ---
st.set_page_config(page_title="RaceLog Pro Gemini", layout="wide")
st.markdown("""
    <style>
    .stApp { background-color: #ffffff !important; color: #000000 !important; }
    h1, h2, h3, label, p, span { color: #1e3a8a !important; font-weight: bold !important; }
    .stDataFrame { border: 1px solid #1e3a8a; }
    input, textarea { background-color: #f0f2f6 !important; color: #000000 !important; }
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
添付された走行試験記録の画像を解析し、以下の項目を正確に抽出してJSON形式のみで出力してください。
項目名は必ず以下の英語キーを使用してください。

{
  "header": {
    "No": "右上のNo", "Event": "種目", "Driver": "ドライバー", "Track": "走行場所", 
    "Weather": "天気", "Temp": "気温", "Humidity": "湿度", "Road_Cond": "路面状態", 
    "Road_Temp": "路面温度", "Start": "開始時刻", "End": "終了時刻"
  },
  "table": [
    {"Lap": 1, "Time": "", "P_FL": "内圧FL", "P_FR": "内圧FR", "T_FL": "表面温FL", "T_FR": "表面温FR", "HV": "HV電圧", "LV": "LV電圧"},
    ... (33行分)
  ],
  "feedback": "ドライバーフィードバックの内容"
}
"""

def analyze_with_gemini(uploaded_file):
    # エラー回避のため、モデル名を最も標準的なものに固定
    model = genai.GenerativeModel('gemini-1.5-flash')
    
    # 画像データを直接読み込む（一時ファイルを使わない方法）
    img_data = uploaded_file.getvalue()
    image_parts = [{"mime_type": "image/jpeg", "data": img_data}]
    
    # 解析実行
    response = model.generate_content([PROMPT, image_parts[0]])
    
    # JSONの抽出
    text = response.text
    try:
        # ```json ... ``` の中身を取り出す
        if "```json" in text:
            json_str = text.split("```json")[1].split("```")[0].strip()
        else:
            json_str = text.strip()
        return json.loads(json_str)
    except Exception as e:
        st.error(f"JSONパースエラー: {e}\nAIの返答: {text}")
        return None

# --- 4. メインUI ---
st.title("🏎️ RaceLog Pro: Gemini Engine")

if 'session_data' not in st.session_state:
    st.session_state.session_data = {}

col1, col2 = st.columns([1, 1])

with col1:
    st.subheader("1. 画像アップロード")
    uploaded = st.file_uploader("ログシートを選択", type=["jpg", "png", "jpeg"])
    if uploaded:
        st.image(uploaded, use_container_width=True)
        if st.button("✨ AI解析を実行"):
            with st.spinner("Geminiが構造を読み取り中..."):
                result = analyze_with_gemini(uploaded)
                if result:
                    key = result["header"].get("No") or f"Session_{len(st.session_state.session_data)}"
                    st.session_state.session_data[key] = result
                    st.success("解析成功！")

with col2:
    # 修正済み：session_state の重複を削除
    if st.session_state.session_data:
        selected_no = st.selectbox("確認・修正中のNo:", list(st.session_state.session_data.keys()))
        data = st.session_state.session_data[selected_no]
        
        st.subheader("2. データの確認・修正")
        # ヘッダー
        h_df = pd.DataFrame([data["header"]])
        data["header"] = st.data_editor(h_df, hide_index=True, key=f"h_{selected_no}").iloc[0].to_dict()
        
        # テーブル
        t_df = pd.DataFrame(data["table"])
        data["table"] = st.data_editor(t_df, hide_index=True, height=400, key=f"t_{selected_no}").to_dict('records')
        
        st.subheader("3. フィードバック")
        data["feedback"] = st.text_area("内容", data["feedback"], key=f"f_{selected_no}")

# --- 5. Excel出力 ---
if st.session_state.session_data:
    st.divider()
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine='xlsxwriter') as writer:
        for no, d in st.session_state.session_data.items():
            # ヘッダーとテーブルを一つのシートに
            pd.DataFrame([d["header"]]).to_excel(writer, sheet_name=f"No_{no}", index=False)
            pd.DataFrame(d["table"]).to_excel(writer, sheet_name=f"No_{no}", startrow=3, index=False)
    
    st.download_button("📈 全データをExcelで保存", buf.getvalue(), "RaceLog_Final.xlsx")
