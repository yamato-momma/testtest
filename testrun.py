import streamlit as st
import pandas as pd
from google.cloud import vision
from google.oauth2 import service_account
import io
import json
import re

# --- 1. ページ設定とデザイン ---
st.set_page_config(page_title="RaceLog Pro v2", layout="wide", page_icon="🏎️")

st.markdown("""
    <style>
    .stApp { background-color: #f0f2f6; }
    .stTabs [data-baseweb="tab-list"] { gap: 24px; }
    .stTabs [data-baseweb="tab"] { height: 50px; font-weight: bold; }
    .data-card { background-color: white; padding: 20px; border-radius: 10px; margin-bottom: 10px; border-top: 5px solid #1e3a8a; }
    </style>
    """, unsafe_allow_html=True)

st.title("🏎️ RaceLog Pro: 高精度データ抽出")

# --- 2. セッション状態の初期化 ---
if 'all_sessions' not in st.session_state:
    st.session_state.all_sessions = {} # { "No_01-01": { "header": {...}, "table": df } }

# --- 3. Google Cloud 認証 ---
if "gcp_service_account" in st.secrets:
    info = json.loads(st.secrets["gcp_service_account"])
    credentials = service_account.Credentials.from_service_account_info(info)
    client = vision.ImageAnnotatorClient(credentials=credentials)
else:
    st.error("GCP Secretsが設定されていません。")
    st.stop()

# --- 4. 解析関数 (座標ベース) ---
def analyze_race_sheet(image_content):
    image = vision.Image(content=image_content)
    response = client.document_text_detection(image=image)
    
    # 読み取った全テキスト（デバッグ用）
    full_text = response.full_text_annotation.text
    
    # --- 簡易的な正規表現による抽出 (精度向上版) ---
    def find_val(pattern, text):
        match = re.search(pattern, text)
        return match.group(1).strip() if match else ""

    # ヘッダー情報の抽出
    header = {
        "No": find_val(r"No\.?\s?([\d-]+)", full_text),
        "種目": find_val(r"種目\n?([^\n]+)", full_text),
        "ドライバー": find_val(r"ドライバー\n?([^\n]+)", full_text),
        "走行場所": find_val(r"走行場所\n?([^\n]+)", full_text),
        "記録": find_val(r"記録\n?([^\n]+)", full_text),
        "天気": find_val(r"天気\n?([^\n]+)", full_text),
        "気温": find_val(r"気温\n?([^\n]+)", full_text),
        "湿度": find_val(r"湿度\n?([^\n]+)", full_text),
        "路面状態": find_val(r"路面状態\n?([^\n]+)", full_text),
        "路面温度": find_val(r"路面温度\n?([^\n]+)", full_text),
        "開始時刻": find_val(r"開始時刻\n?([\d:]+)", full_text),
        "終了時刻": find_val(r"終了時刻\n?([\d:]+)", full_text),
        "走行時間": find_val(r"走行時間\n?([^\n]+)", full_text),
        "セッティング": find_val(r"セッティング\n?([^\n]+)", full_text),
        "フィードバック": find_val(r"ドライバーフィードバック\n?([\s\S]+)$", full_text)
    }

    # 表データの抽出 (Lap 1-33)
    # ラップタイムらしき「XX.XX」の形式をすべて抽出
    times = re.findall(r"\d{2}\.\d{2}", full_text)
    
    # 数値らしきものをリスト化 (タイヤ内圧や温度用)
    all_numbers = re.findall(r"\b\d{2,3}\b", full_text)

    # 33行分の空の表を作成
    rows = []
    for i in range(1, 34):
        rows.append({
            "Lap": i, "Time": times[i-1] if i <= len(times) else "",
            "内圧(前)FL": "", "内圧(前)FR": "", "内圧(前)RL": "", "内圧(前)RR": "",
            "内圧(後)FL": "", "内圧(後)FR": "", "内圧(後)RL": "", "内圧(後)RR": "",
            "表面温度(前)FL": "", "表面温度(前)FR": "", "表面温度(前)RL": "", "表面温度(前)RR": "",
            "表面温度(後)FL": "", "表面温度(後)FR": "", "表面温度(後)RL": "", "表面温度(後)RR": "",
            "ディスク(前)FL": "", "ディスク(前)FR": "", "ディスク(前)RL": "", "ディスク(前)RR": "",
            "ディスク(後)FL": "", "ディスク(後)FR": "", "ディスク(後)RL": "", "ディスク(後)RR": "",
            "HV(前)": "", "HV(後)": "", "LV(前)": "", "LV(後)": ""
        })
    
    return header, pd.DataFrame(rows)

# --- 5. メイン画面 ---
tab1, tab2 = st.tabs(["📤 読み取り", "📊 走行会まとめ・出力"])

with tab1:
    up_col, res_col = st.columns([1, 1])
    with up_col:
        uploaded_file = st.file_uploader("ログシートの写真をアップロード", type=["jpg", "jpeg", "png"])
        if uploaded_file:
            st.image(uploaded_file, use_container_width=True)

    with res_col:
        if uploaded_file:
            if st.button("🚀 AI解析を開始"):
                with st.spinner('手書き文字を構造化しています...'):
                    header, table_df = analyze_race_sheet(uploaded_file.read())
                    session_key = header["No"] if header["No"] else f"Untitled_{len(st.session_state.all_sessions)+1}"
                    st.session_state.all_sessions[session_key] = {"header": header, "table": table_df}
                    st.success(f"No.{session_key} を解析しました！")

# --- 6. データの修正と表示 ---
if st.session_state.all_sessions:
    current_no = st.selectbox("修正・確認するNoを選択", list(st.session_state.all_sessions.keys()))
    sess = st.session_state.all_sessions[current_no]

    with st.expander("📝 ヘッダー項目 (種目・環境など)", expanded=True):
        col_h1, col_h2, col_h3 = st.columns(3)
        h = sess["header"]
        h["種目"] = col_h1.text_input("種目", h["種目"])
        h["ドライバー"] = col_h2.text_input("ドライバー", h["ドライバー"])
        h["走行場所"] = col_h3.text_input("走行場所", h["走行場所"])
        h["天気"] = col_h1.text_input("天気", h["天気"])
        h["気温"] = col_h2.text_input("気温", h["気温"])
        h["湿度"] = col_h3.text_input("湿度", h["湿度"])
        h["路面状態"] = col_h1.text_input("路面状態", h["路面状態"])
        h["路面温度"] = col_h2.text_input("路面温度", h["路面温度"])
        h["走行時間"] = col_h3.text_input("走行時間", h["走行時間"])
        h["フィードバック"] = st.text_area("ドライバーフィードバック", h["フィードバック"])

    st.subheader("🏎️ ラップ・タイヤ・電圧データ")
    sess["table"] = st.data_editor(sess["table"], num_rows="dynamic")

# --- 7. Excel出力 ---
with tab2:
    if st.session_state.all_sessions:
        event_name = st.text_input("走行会ファイル名", "Race_Event_2026")
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            for no, content in st.session_state.all_sessions.items():
                # ヘッダーとテーブルを1つのシートにまとめる
                h_df = pd.DataFrame(list(content["header"].items()), columns=["項目", "値"])
                h_df.to_excel(writer, sheet_name=f"No_{no}", startrow=0, index=False)
                content["table"].to_excel(writer, sheet_name=f"No_{no}", startrow=len(h_df)+2, index=False)
        
        st.download_button(
            label="📈 全データをExcelで一括ダウンロード",
            data=output.getvalue(),
            file_name=f"{event_name}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
