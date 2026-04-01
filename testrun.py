import streamlit as st
import pandas as pd
from google.cloud import vision
from google.oauth2 import service_account
import io
import json

# --- ページ設定 ---
st.set_page_config(page_title="RaceLog Pro v3", layout="wide")

# スタイリッシュなCSS
st.markdown("""
    <style>
    .stApp { background-color: #f4f7f6; }
    .stTabs [data-baseweb="tab-list"] { background-color: #1e3a8a; border-radius: 10px; padding: 5px; }
    .stTabs [data-baseweb="tab"] { color: white; }
    .data-card { background-color: white; padding: 15px; border-radius: 10px; border-top: 5px solid #1e3a8a; }
    </style>
    """, unsafe_allow_html=True)

# --- 認証設定 ---
if "gcp_service_account" in st.secrets:
    info = json.loads(st.secrets["gcp_service_account"])
    credentials = service_account.Credentials.from_service_account_info(info)
    client = vision.ImageAnnotatorClient(credentials=credentials)
else:
    st.error("GCP Secretsが設定されていません。")
    st.stop()

# --- セッション保持 ---
if 'all_sessions' not in st.session_state:
    st.session_state.all_sessions = {}

# --- 高度な座標解析エンジン ---
def get_text_near(texts, target_label, direction="below", threshold=150):
    """
    特定のラベル（例：'天気'）の近く（下または右）にあるテキストを抽出する
    """
    target_box = None
    for text in texts[1:]: # 0番目は全テキスト
        if target_label in text.description:
            target_box = text.bounding_poly.vertices
            break
    
    if not target_box:
        return ""

    # ラベルの下辺/右辺の座標
    base_x = (target_box[0].x + target_box[1].x) / 2
    base_y = (target_box[2].y + target_box[3].y) / 2

    candidates = []
    for text in texts[1:]:
        if target_label in text.description: continue
        box = text.bounding_poly.vertices
        center_x = (box[0].x + box[1].x) / 2
        center_y = (box[0].y + box[3].y) / 2
        
        # 「下」にあるものを探すロジック
        if direction == "below":
            if abs(center_x - base_x) < 100 and 0 < (center_y - base_y) < threshold:
                candidates.append((center_y, text.description))
    
    if candidates:
        # 最も近いものを返す
        candidates.sort()
        return candidates[0][1]
    return ""

def process_image(image_content):
    image = vision.Image(content=image_content)
    response = client.document_text_detection(image=image)
    texts = response.text_annotations
    
    if not texts:
        return None, None

    # 1. ヘッダー情報の取得（座標ベース）
    header_keys = [
        "種目", "ドライバー", "走行場所", "記録", "天気", "気温", "湿度", 
        "路面状態", "路面温度", "開始時刻", "終了時刻", "走行時間", "セッティング"
    ]
    header_data = {k: get_text_near(texts, k) for k in header_keys}
    header_data["No"] = get_text_near(texts, "No", threshold=100)
    header_data["フィードバック"] = get_text_near(texts, "ドライバーフィードバック", threshold=500)

    # 2. テーブルデータの作成
    rows = []
    # OCR結果から数字とその座標をリスト化
    all_words = []
    for text in texts[1:]:
        desc = text.description
        box = text.bounding_poly.vertices
        center_x = (box[0].x + box[1].x) / 2
        center_y = (box[0].y + box[3].y) / 2
        all_words.append({'text': desc, 'x': center_x, 'y': center_y})

    for i in range(1, 34):
        # 各行の基準点を「Lap番号」の座標から推測（簡易実装）
        row_data = {
            "Lap": i, "Time": "", "内圧(FL)": "", "内圧(FR)": "", "内圧(RL)": "", "内圧(RR)": "",
            "表面温(FL)": "", "表面温(FR)": "", "表面温(RL)": "", "表面温(RR)": "",
            "ディスク(FL)": "", "ディスク(FR)": "", "ディスク(RL)": "", "ディスク(RR)": ""
        }
        # ここで特定のY座標範囲にある数字をTime列などに割り振る（微調整が必要）
        rows.append(row_data)

    return header_data, pd.DataFrame(rows)

# --- UI構築 ---
st.title("🏎️ RaceLog Pro v3")

tab1, tab2 = st.tabs(["📤 読み取り", "📊 保存データ管理"])

with tab1:
    col_l, col_r = st.columns([1, 1])
    with col_l:
        file = st.file_uploader("ログシート画像をアップ", type=["jpg", "png"])
        if file:
            st.image(file, use_container_width=True)
            if st.button("🚀 解析実行"):
                h, t = process_image(file.read())
                if h:
                    key = h["No"] if h["No"] else f"Temp_{len(st.session_state.all_sessions)}"
                    st.session_state.all_sessions[key] = {"header": h, "table": t}
                    st.rerun()

    if st.session_state.all_sessions:
        with col_r:
            selected_key = st.selectbox("確認・修正対象", list(st.session_state.all_sessions.keys()))
            data = st.session_state.all_sessions[selected_key]
            
            st.subheader("📝 基本情報（タイトル下の値を抽出）")
            for k, v in data["header"].items():
                data["header"][k] = st.text_input(k, v)
            
            st.subheader("📊 詳細データ")
            data["table"] = st.data_editor(data["table"], height=400)

with tab2:
    if st.session_state.all_sessions:
        ev_name = st.text_input("イベント名", "Race_Log_2026")
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine='xlsxwriter') as writer:
            for k, v in st.session_state.all_sessions.items():
                # 1シートにヘッダーとテーブルを縦に並べる
                df_h = pd.DataFrame(list(v["header"].items()), columns=["項目", "値"])
                df_h.to_excel(writer, sheet_name=f"No_{k}", index=False)
                v["table"].to_excel(writer, sheet_name=f"No_{k}", startrow=len(df_h)+2, index=False)
        
        st.download_button("📈 Excelダウンロード", buf.getvalue(), f"{ev_name}.xlsx")
