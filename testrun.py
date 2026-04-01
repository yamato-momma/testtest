import streamlit as st
import pandas as pd
from google.cloud import vision
from google.oauth2 import service_account
import io
import json
import re

# --- 1. ページ設定とデザイン (スタイリッシュなUI) ---
st.set_page_config(page_title="RaceLog Pro", layout="wide", page_icon="🏎️")

st.markdown("""
    <style>
    .stApp { background-color: #f8f9fa; }
    .stButton>button { 
        width: 100%; border-radius: 8px; height: 3.5em; 
        background-color: #1e3a8a; color: white; font-weight: bold;
        transition: 0.3s;
    }
    .stButton>button:hover { background-color: #3b82f6; border: none; }
    .status-box { 
        padding: 20px; border-radius: 10px; border-left: 8px solid #1e3a8a;
        background-color: white; box-shadow: 0 2px 4px rgba(0,0,0,0.05);
    }
    h1 { color: #1e3a8a; font-family: 'Helvetica Neue', sans-serif; }
    </style>
    """, unsafe_allow_html=True)

st.title("🏎️ RaceLog Pro")
st.caption("手書き走行データシート ➔ マルチシートExcel変換")

# --- 2. セッション状態の初期化 (走行会データを貯める) ---
if 'all_data' not in st.session_state:
    st.session_state.all_data = {} # { "No_01": df, "No_02": df }

# --- 3. Google Cloud 認証 ---
if "gcp_service_account" in st.secrets:
    try:
        info = json.loads(st.secrets["gcp_service_account"])
        credentials = service_account.Credentials.from_service_account_info(info)
        client = vision.ImageAnnotatorClient(credentials=credentials)
    except Exception as e:
        st.error(f"認証情報の形式が正しくありません: {e}")
        st.stop()
else:
    st.error("Secretsに 'gcp_service_account' が設定されていません。")
    st.stop()

# --- 4. サイドバー設定 ---
with st.sidebar:
    st.header("⚙️ システム設定")
    event_name = st.text_input("走行会・イベント名", "2026_Circuit_Run")
    st.divider()
    if st.button("🔴 全データをリセット"):
        st.session_state.all_data = {}
        st.rerun()

# --- 5. メイン機能 (タブ分け) ---
tab1, tab2 = st.tabs(["📤 アップロード・解析", "📊 蓄積データ・エクスポート"])

with tab1:
    col_up, col_res = st.columns([1, 1])
    
    with col_up:
        uploaded_file = st.file_uploader("ログシートの写真をアップロード", type=["jpg", "jpeg", "png"])
        if uploaded_file:
            st.image(uploaded_file, caption="スキャン中...", use_container_width=True)

    with col_res:
        if uploaded_file:
            if st.button("✨ AI解析を実行"):
                with st.spinner('手書き文字を構造化しています...'):
                    content = uploaded_file.read()
                    image = vision.Image(content=content)
                    
                    # Google Vision API 呼び出し
                    response = client.document_text_detection(image=image)
                    full_text = response.full_text_annotation.text
                    
                    # --- データ抽出ロジック ---
                    # 右上のNoを抽出 (例: No.01-01 -> 01-01)
                    no_match = re.search(r"No\.?\s?([\d-]+)", full_text)
                    sheet_no = no_match.group(1) if no_match else f"Unknown_{len(st.session_state.all_data)+1}"
                    
                    # ラップタイムの抽出 (数字.数字 のパターンを探す)
                    times = re.findall(r"\b\d{2}\.\d{2}\b", full_text)
                    
                    # 表の雛形作成 (画像の項目を網羅)
                    data = []
                    for i in range(1, 34): # 最大33ラップ想定
                        t = times[i-1] if i <= len(times) else ""
                        data.append({
                            "Lap": i, "Time": t, 
                            "内圧_FL": "", "内圧_FR": "", "内圧_RL": "", "内圧_RR": "",
                            "表面温度_FL": "", "表面温度_FR": "", "表面温度_RL": "", "表面温度_RR": "",
                            "HV電圧": "", "LV電圧": ""
                        })
                    
                    new_df = pd.DataFrame(data)
                    st.session_state.all_data[sheet_no] = new_df
                    st.success(f"シート No.{sheet_no} を認識しました！")

            # 個別データの編集
            for s_no in st.session_state.all_data.keys():
                if st.checkbox(f"No.{s_no} のデータを手動修正する"):
                    st.session_state.all_data[s_no] = st.data_editor(st.session_state.all_data[s_no], key=f"editor_{s_no}")

with tab2:
    if st.session_state.all_data:
        st.subheader(f"📅 {event_name} まとめ")
        st.write(f"現在の保存済みシート: {', '.join(st.session_state.all_data.keys())}")
        
        # Excel作成 (マルチシート)
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            for s_no, df in st.session_state.all_data.items():
                df.to_excel(writer, sheet_name=f"No_{s_no}", index=False)
        
        st.download_button(
            label="📥 全シートをまとめてExcelダウンロード",
            data=output.getvalue(),
            file_name=f"{event_name}_RaceLog.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        
        # プレビュー
        selected_no = st.selectbox("プレビューするNoを選択", options=list(st.session_state.all_data.keys()))
        st.dataframe(st.session_state.all_data[selected_no], use_container_width=True)
    else:
        st.info("まだ解析データがありません。タブ1から画像をアップロードしてください。")
