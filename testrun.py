import streamlit as st
import pandas as pd
from google.cloud import vision
from google.oauth2 import service_account
import io
import json

# --- 1. ページ設定と視認性重視のデザイン ---
st.set_page_config(page_title="RaceLog Pro v3.1", layout="wide")

# CSSで色を強制固定（白背景に白文字を防ぐ）
st.markdown("""
    <style>
    /* 全体の背景色 */
    .stApp { background-color: #f0f2f6 !important; }
    
    /* 文字色を黒・濃紺に固定 */
    h1, h2, h3, p, span, label { color: #1e3a8a !important; font-weight: bold !important; }
    
    /* 入力エリアのスタイル */
    .stTextInput>div>div>input, .stTextArea>div>div>textarea {
        background-color: white !important;
        color: #333 !important;
        border: 1px solid #1e3a8a !important;
    }

    /* ボタンのデザイン */
    .stButton>button {
        background-color: #1e3a8a !important;
        color: white !important;
        border-radius: 5px;
        padding: 0.5rem 2rem;
        font-weight: bold;
    }

    /* データエディタ（表）の背景 */
    .stDataEditor { background-color: white !important; border-radius: 10px; }
    
    /* カード風のコンテナ */
    .data-card {
        background-color: #ffffff;
        padding: 20px;
        border-radius: 10px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        margin-bottom: 20px;
    }
    </style>
    """, unsafe_allow_html=True)

# --- 2. 認証設定 ---
if "gcp_service_account" in st.secrets:
    info = json.loads(st.secrets["gcp_service_account"])
    credentials = service_account.Credentials.from_service_account_info(info)
    client = vision.ImageAnnotatorClient(credentials=credentials)
else:
    st.error("Secretsの設定（gcp_service_account）が見つかりません。")
    st.stop()

if 'all_sessions' not in st.session_state:
    st.session_state.all_sessions = {}

# --- 3. 解析ロジック (タイトルの下を探す) ---
def get_text_under_label(texts, label, y_range=150):
    target_box = None
    for text in texts[1:]:
        if label in text.description:
            target_box = text.bounding_poly.vertices
            break
    if not target_box: return ""

    lx = (target_box[0].x + target_box[1].x) / 2
    ly = (target_box[2].y + target_box[3].y) / 2
    
    candidates = []
    for text in texts[1:]:
        if label in text.description: continue
        box = text.bounding_poly.vertices
        cx = (box[0].x + box[1].x) / 2
        cy = (box[0].y + box[3].y) / 2
        
        # 横方向のズレが少なく、かつ一定距離「下」にあるもの
        if abs(cx - lx) < 120 and 5 < (cy - ly) < y_range:
            candidates.append((cy, text.description))
    
    if candidates:
        candidates.sort() # 最も近いものを選択
        return candidates[0][1]
    return ""

def process_race_image(content):
    image = vision.Image(content=content)
    response = client.document_text_detection(image=image)
    texts = response.text_annotations
    if not texts: return None, None

    # ヘッダー項目の抽出
    keys = ["種目", "ドライバー", "走行場所", "記録", "天気", "気温", "湿度", "路面状態", "路面温度", "開始時刻", "終了時刻", "走行時間", "セッティング"]
    h = {k: get_text_under_label(texts, k) for k in keys}
    h["No"] = get_text_under_label(texts, "No", y_range=80)
    h["フィードバック"] = get_text_under_label(texts, "ドライバーフィードバック", y_range=500)

    # テーブルの空枠作成（33行）
    cols = ["Lap", "Time", "内圧FL", "内圧FR", "内圧RL", "内圧RR", "表面温FL", "表面温FR", "表面温RL", "表面温RR", "ディスクFL", "ディスクFR", "ディスクRL", "ディスクRR", "HV前", "HV後", "LV前", "LV後"]
    df = pd.DataFrame(columns=cols)
    for i in range(1, 34):
        df.loc[i-1] = [i] + [""] * (len(cols)-1)
    
    return h, df

# --- 4. メインUI ---
st.title("🏎️ RaceLog Pro v3.1")

tab1, tab2 = st.tabs(["📥 読み取りと修正", "📊 まとめと書き出し"])

with tab1:
    col_l, col_r = st.columns([1, 1])
    
    with col_l:
        st.subheader("1. 画像アップロード")
        file = st.file_uploader("ログシートを選択", type=["jpg", "png", "jpeg"])
        if file:
            st.image(file, use_container_width=True)
            if st.button("AI解析を実行"):
                with st.spinner("位置情報を解析中..."):
                    h, t = process_race_image(file.read())
                    key = h["No"] if h["No"] else f"Untitled_{len(st.session_state.all_sessions)}"
                    st.session_state.all_sessions[key] = {"header": h, "table": t}
                    st.rerun()

    with col_r:
        if st.session_state.all_sessions:
            current_no = st.selectbox("確認・編集中のNo:", list(st.session_state.all_sessions.keys()))
            sess = st.session_state.all_sessions[current_no]
            
            st.subheader("2. 抽出結果の確認（タイトル下の値）")
            # 2カラムでヘッダーを表示
            h_col1, h_col2 = st.columns(2)
            for i, (k, v) in enumerate(sess["header"].items()):
                if k == "フィードバック": continue
                target_col = h_col1 if i % 2 == 0 else h_col2
                sess["header"][k] = target_col.text_input(k, v)
            
            sess["header"]["フィードバック"] = st.text_area("ドライバーフィードバック", sess["header"]["フィードバック"])

            st.subheader("3. タイヤ・ラップデータ（表）")
            sess["table"] = st.data_editor(sess["table"], hide_index=True)

with tab2:
    if st.session_state.all_sessions:
        st.subheader("走行会データのエクスポート")
        filename = st.text_input("保存ファイル名", "Circuit_Event_Result")
        
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine='xlsxwriter') as writer:
            for no, data in st.session_state.all_sessions.items():
                # ヘッダーを縦に並べる
                df_h = pd.DataFrame(list(data["header"].items()), columns=["項目", "値"])
                sheet_name = f"Sheet_{no}".replace("-", "_")[:31]
                df_h.to_excel(writer, sheet_name=sheet_name, index=False)
                # テーブルをその下に配置
                data["table"].to_excel(writer, sheet_name=sheet_name, startrow=len(df_h)+2, index=False)
        
        st.download_button("📈 Excelを一括ダウンロード", buf.getvalue(), f"{filename}.xlsx")
    else:
        st.info("解析済みのデータはありません。")
