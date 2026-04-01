import streamlit as st
import pandas as pd
import google.generativeai as genai
import io
import json

# --- 1. デザイン固定（視認性重視・白背景/黒文字） ---
st.set_page_config(page_title="RaceLog Gemini Edition", layout="wide")
st.markdown("""
    <style>
    .stApp { background-color: white !important; color: black !important; }
    h1, h2, h3, label, p { color: #1e3a8a !important; font-weight: bold !important; }
    .stDataFrame { border: 1px solid #1e3a8a; }
    </style>
    """, unsafe_allow_html=True)

# --- 2. Gemini API 設定 ---
if "GEMINI_API_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
else:
    st.error("Secretsに GEMINI_API_KEY を設定してください。")
    st.stop()

# --- 3. 解析用プロンプト（テンプレを学習させる） ---
PROMPT = """
添付された走行試験記録の画像を解析し、以下の項目を正確に抽出してJSON形式で出力してください。
特にタイヤ内圧、表面温度、電圧は、表の行（Lap 1, 2...）と列を正確に一致させてください。

出力フォーマット:
{
  "header": {
    "No": "", "種目": "", "ドライバー": "", "走行場所": "", "記録": "",
    "天気": "", "気温": "", "湿度": "", "路面状態": "", "路面温度": "",
    "開始時刻": "", "終了時刻": "", "走行時間": "", "セッティング": ""
  },
  "table": [
    {"Lap": 1, "Time": "", "内圧FL": "", "内圧FR": "", "内圧RL": "", "内圧RR": "", "表面温FL": "", "表面温FR": "", "表面温RL": "", "表面温RR": "", "ディスクFL": "", "ディスクFR": "", "ディスクRL": "", "ディスクRR": "", "HV前": "", "HV後": "", "LV前": "", "LV後": ""},
    ... (33行分)
  ],
  "feedback": ""
}
手書き文字が読みにくい場合は、文脈から推測するか、空欄にしてください。
"""

def analyze_with_gemini(image_file):
    model = genai.GenerativeModel('gemini-1.5-flash-latest')
    img = genai.upload_file(image_file) # 一時アップロード
    response = model.generate_content([PROMPT, img])
    
    # JSON部分のみを抽出
    json_str = response.text.replace('```json', '').replace('```', '').strip()
    return json.loads(json_str)

# --- 4. メインUI ---
st.title("🏎️ RaceLog Pro: Gemini AI Engine")

if 'session_data' not in st.session_state:
    st.session_state.session_data = {}

col1, col2 = st.columns([1, 1])

with col1:
    st.subheader("1. 画像アップロード")
    uploaded = st.file_uploader("ログシートを選択", type=["jpg", "png", "jpeg"])
    if uploaded:
        st.image(uploaded, use_container_width=True)
        if st.button("AIに読み取らせる（座標不要）"):
            with st.spinner("Geminiが画像全体を構造解析中..."):
                try:
                    # 画像を一時ファイルとして保存
                    with open("temp_img.jpg", "wb") as f:
                        f.write(uploaded.getbuffer())
                    
                    result = analyze_with_gemini("temp_img.jpg")
                    key = result["header"]["No"] or f"Unknown_{len(st.session_state.session_data)}"
                    st.session_state.session_data[key] = result
                    st.success("解析完了！")
                except Exception as e:
                    st.error(f"解析エラー: {e}")

with col2:
   if st.session_state.session_data:
        selected_no = st.selectbox("確認・修正中:", list(st.session_state.session_data.keys()))
        data = st.session_state.session_data[selected_no]
        
        st.subheader("2. 解析結果の確認")
        # ヘッダー編集
        h_df = pd.DataFrame([data["header"]])
        edited_h = st.data_editor(h_df, hide_index=True, key=f"h_{selected_no}")
        
        # テーブル編集
        t_df = pd.DataFrame(data["table"])
        edited_t = st.data_editor(t_df, hide_index=True, height=500, key=f"t_{selected_no}")
        
        # フィードバック
        data["feedback"] = st.text_area("フィードバック", data["feedback"])

        # 保存
        if st.button("このデータをExcel出力用に確定"):
            data["header"] = edited_h.iloc[0].to_dict()
            data["table"] = edited_t.to_dict('records')
            st.toast("保存しました")

# --- Excelダウンロード ---
if st.session_state.session_data:
    st.divider()
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine='xlsxwriter') as writer:
        for no, d in st.session_state.session_data.items():
            pd.DataFrame([d["header"]]).to_excel(writer, sheet_name=f"No_{no}", index=False)
            pd.DataFrame(d["table"]).to_excel(writer, sheet_name=f"No_{no}", startrow=3, index=False)
            pd.DataFrame([{"フィードバック": d["feedback"]}]).to_excel(writer, sheet_name=f"No_{no}", startrow=38, index=False)
    
    st.download_button("📈 全シートをExcelでダウンロード", buf.getvalue(), "RaceReport_Final.xlsx")
