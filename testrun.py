import streamlit as st
import pandas as pd
from google.cloud import vision
from google.oauth2 import service_account
import io
import json

# --- ページ設定とデザイン ---
st.set_page_config(page_title="RaceLog Pro", layout="wide")

# スタイリッシュなCSS
st.markdown("""
    <style>
    .main { background-color: #f5f7f9; }
    .stButton>button { width: 100%; border-radius: 5px; height: 3em; background-color: #007bff; color: white; }
    .reportview-container .main .block-container { padding-top: 2rem; }
    h1 { color: #1e3a8a; border-left: 5px solid #1e3a8a; padding-left: 10px; }
    </style>
    """, unsafe_allow_stdio=True)

st.title("🏎️ RaceLog Pro: 走行データ解析")

# --- セッション状態の初期化 (走行会データを貯める用) ---
if 'all_data' not in st.session_state:
    st.session_state.all_data = {} # { "No_1": df, "No_2": df }

# --- Google Cloud 認証 ---
if "gcp_service_account" in st.secrets:
    info = json.loads(st.secrets["gcp_service_account"])
    credentials = service_account.Credentials.from_service_account_info(info)
    client = vision.ImageAnnotatorClient(credentials=credentials)
else:
    st.error("GCP Secretsが設定されていません。")
    st.stop()

# --- サイドパネル (設定) ---
with st.sidebar:
    st.header("⚙️ 設定")
    event_name = st.text_input("走行会名称", "2024_走行会")
    if st.button("全データをリセット"):
        st.session_state.all_data = {}
        st.rerun()

# --- メイン画面 ---
tab1, tab2 = st.tabs(["📤 データ読み取り", "📊 蓄積データ確認・出力"])

with tab1:
    col1, col2 = st.columns([1, 1])
    
    with col1:
        uploaded_file = st.file_uploader("ログシートの画像をアップロード", type=["jpg", "jpeg", "png"])
        if uploaded_file:
            st.image(uploaded_file, caption="解析対象", use_container_width=True)

    with col2:
        if uploaded_file:
            if st.button("AI解析を実行"):
                with st.spinner('高度なレイアウト解析中...'):
                    content = uploaded_file.read()
                    image = vision.Image(content=content)
                    response = client.document_text_detection(image=image)
                    
                    # --- データの抽出ロジック (簡易版) ---
                    # 本来は座標(bounding_box)で判定しますが、ここではデモ用にテキスト解析を行います
                    all_text = response.full_text_annotation.text
                    lines = all_text.split('\n')
                    
                    # Noの抽出
                    sheet_no = "Unknown"
                    for line in lines:
                        if "No" in line:
                            sheet_no = line.replace("No", "").strip()

                    # 表データの作成 (送付画像の項目に準拠)
                    # ここで読み取った値を辞書にまとめます
                    # ※ 実際の運用では座標による高精度なパースが必要になります
                    items = ["Lap Time", "内圧(FL/FR)", "内圧(RL/RR)", "表面温度", "ディスク温度", "HV/LV電圧"]
                    data_rows = []
                    for i in range(1, 11): # 10周分
                        data_rows.append({
                            "Lap": i,
                            "Lap Time": "", "内圧_FL": "", "内圧_FR": "", "内圧_RL": "", "内圧_RR": "",
                            "表面温度": "", "ディスク温度": "", "HV電圧": "", "LV電圧": ""
                        })
                    
                    current_df = pd.DataFrame(data_rows)
                    
                    # セッションに保存
                    st.session_state.all_data[f"No_{sheet_no}"] = current_df
                    st.success(f"No.{sheet_no} のデータを解析し、一時保存しました。")
                    st.data_editor(current_df) # 画面上で修正可能に

with tab2:
    if st.session_state.all_data:
        st.write(f"現在 **{len(st.session_state.all_data)}枚** のシートを保持しています。")
        
        # Excel書き出しロジック
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            for sheet_name, df in st.session_state.all_data.items():
                df.to_excel(writer, sheet_name=sheet_name, index=False)
        
        st.download_button(
            label="📈 走行会まとめExcelをダウンロード",
            data=output.getvalue(),
            file_name=f"{event_name}_results.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        
        # プレビュー表示
        for name, df in st.session_state.all_data.items():
            with st.expander(f"詳細確認: {name}"):
                st.dataframe(df)
    else:
        st.info("データがまだありません。タブ1から画像をアップロードしてください。")
