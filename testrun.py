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
    /* テーブル内の文字色を黒に強制 */
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
特に、タイヤ内圧(FL/FR/RL/RR)、表面温度、ディスク温度、HV/LV電圧の各数値を、表のLap番号(1-33)と正確に一致させてください。

出力フォーマット:
{
  "header": {
    "No": "右上のNo", "種目": "", "ドライバー": "", "走行場所": "", "記録": "",
    "天気": "", "気温": "", "湿度": "", "路面状態": "", "路面温度": "",
    "開始時刻": "", "終了時刻": "", "走行時間": "", "セッティング": ""
  },
  "table": [
    {"Lap": 1, "Time": "", "P_FL": "", "P_FR": "", "P_RL": "", "P_RR": "", "T_FL": "", "T_FR": "", "T_RL": "", "T_RR": "", "D_FL": "", "D_FR": "", "D_RL": "", "D_RR": "", "HV_Pre": "", "HV_Post": "", "LV_Pre": "", "LV_Post": ""},
    ...
  ],
  "feedback": "ドライバーフィードバックの内容"
}
"""

def analyze_with_gemini(uploaded_file):
    # 最新モデルを指定
    model = genai.GenerativeModel(model_name='models/gemini-1.5-flash')
    
    # 画像データの準備
    img_data = uploaded_file.getvalue()
    image_parts = [{"mime_type": "image/jpeg", "data": img_data}]
    
    # 解析実行
    try:
        response = model.generate_content([PROMPT, image_parts[0]])
        text = response.text
        # JSON部分を抽出
        if "```json" in text:
            json_str = text.split("```json")[1].split("```")[0].strip()
        else:
            json_str = text.strip()
        return json.loads(json_str)
    except Exception as e:
        st.error(f"解析中にエラーが発生しました: {e}")
        return None

# --- 4. メインUI ---
st.title("🏎️ RaceLog Pro: Gemini Engine")

if 'session_data' not in st.session_state:
    st.session_state.session_data = {}

col1, col2 = st.columns([1, 1])

with col1:
    st.subheader("1. 画像アップロード")
    uploaded = st.file_uploader("ログシートを選択してください", type=["jpg", "png", "jpeg"])
    if uploaded:
        st.image(uploaded, use_container_width=True)
        if st.button("✨ AI解析を実行"):
            with st.spinner("Geminiが画像を精査しています..."):
                result = analyze_with_gemini(uploaded)
                if result:
                    # Noをキーにして保存
                    key = result["header"].get("No") or f"Session_{len(st.session_state.session_data)}"
                    st.session_state.session_data[key] = result
                    st.success("解析に成功しました！右側で内容を確認してください。")

with col2:
    if st.session_state.session_data:
        selected_no = st.selectbox("表示するNoを選択:", list(st.session_state.session_data.keys()))
        data = st.session_state.session_data[selected_no]
        
        st.subheader("2. データの確認・修正")
        # ヘッダー情報
        h_df = pd.DataFrame(list(data["header"].items()), columns=["項目", "値"])
        edited_h = st.data_editor(h_df, hide_index=True, use_container_width=True, key=f"h_edit_{selected_no}")
        
        # 数値テーブル
        st.subheader("3. タイム・タイヤ詳細")
        t_df = pd.DataFrame(data["table"])
        edited_t = st.data_editor(t_df, hide_index=True, height=450, use_container_width=True, key=f"t_edit_{selected_no}")
        
        st.subheader("4. フィードバック")
        data["feedback"] = st.text_area("内容", data["feedback"], key=f"f_edit_{selected_no}")

        # 保存用反映
        if st.button("修正内容を反映して確定"):
            data["header"] = dict(edited_h.values)
            data["table"] = edited_t.to_dict('records')
            st.toast("データを確定しました。")

# --- 5. Excel出力 ---
if st.session_state.session_data:
    st.divider()
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine='xlsxwriter') as writer:
        for no, d in st.session_state.session_data.items():
            # シート名エラーの修正箇所
            sheet_name = f"No_{no}".replace("-", "_").replace(".", "_")[:30]
            # ヘッダー
            pd.DataFrame(list(d["header"].items())).to_excel(writer, sheet_name=sheet_name, index=False, header=False)
            # テーブル
            pd.DataFrame(d["table"]).to_excel(writer, sheet_name=sheet_name, startrow=len(d["header"])+2, index=False)
    
    st.download_button("📈 全シートを一括ダウンロード (Excel)", buf.getvalue(), "RaceLog_Output.xlsx")
