import streamlit as st
import pandas as pd
from google.cloud import vision
from google.oauth2 import service_account
import io
import json

# --- 1. デザインの強制固定（視認性最優先） ---
st.set_page_config(page_title="RaceLog Pro v5", layout="wide")

st.markdown("""
    <style>
    /* 全体背景と文字色を強制 */
    .stApp { background-color: #ffffff !important; color: #000000 !important; }
    
    /* 入力欄の文字を黒に固定 */
    input, textarea, [data-baseweb="input"] {
        background-color: #f0f2f6 !important;
        color: #000000 !important;
        border: 1px solid #1e3a8a !important;
    }
    
    /* ラベルやタイトルの色 */
    h1, h2, h3, label, p, span { color: #1e3a8a !important; font-weight: bold !important; }

    /* データエディタの視認性 */
    .stDataEditor div { color: #000000 !important; }
    
    /* ボタン */
    .stButton>button {
        background-color: #1e3a8a !important;
        color: #ffffff !important;
        width: 100%;
    }
    </style>
    """, unsafe_allow_html=True)

# --- 2. Google Cloud 認証 ---
if "gcp_service_account" in st.secrets:
    info = json.loads(st.secrets["gcp_service_account"])
    credentials = service_account.Credentials.from_service_account_info(info)
    client = vision.ImageAnnotatorClient(credentials=credentials)
else:
    st.error("GCPサービスアカウントキーが設定されていません。")
    st.stop()

if 'all_data' not in st.session_state:
    st.session_state.all_data = {}

# --- 3. 座標解析エンジン（テンプレ準拠） ---
def extract_by_ratio(texts, x_range, y_range, img_w, img_h):
    """ 指定された比率範囲内の文字を抽出 """
    results = []
    for text in texts[1:]:
        box = text.bounding_poly.vertices
        cx = sum([v.x for v in box]) / 4 / img_w
        cy = sum([v.y for v in box]) / 4 / img_h
        if x_range[0] <= cx <= x_range[1] and y_range[0] <= cy <= y_range[1]:
            results.append(text.description)
    return "".join(results)

def analyze_race_sheet(content):
    image = vision.Image(content=content)
    response = client.document_text_detection(image=image)
    texts = response.text_annotations
    if not texts: return None, None

    # 画像サイズ取得
    full_box = texts[0].bounding_poly.vertices
    img_w, img_h = full_box[1].x, full_box[2].y

    # ヘッダー解析（テンプレの配置に基づき、少し広めのバッファを持たせて抽出）
    h = {
        "No": extract_by_ratio(texts, [0.80, 0.98], [0.10, 0.16], img_w, img_h),
        "種目": extract_by_ratio(texts, [0.20, 0.40], [0.15, 0.22], img_w, img_h),
        "ドライバー": extract_by_ratio(texts, [0.45, 0.60], [0.15, 0.22], img_w, img_h),
        "走行場所": extract_by_ratio(texts, [0.65, 0.80], [0.15, 0.22], img_w, img_h),
        "天気": extract_by_ratio(texts, [0.20, 0.25], [0.22, 0.30], img_w, img_h),
        "気温": extract_by_ratio(texts, [0.25, 0.35], [0.22, 0.30], img_w, img_h),
        "湿度": extract_by_ratio(texts, [0.35, 0.45], [0.22, 0.30], img_w, img_h),
        "路面状態": extract_by_ratio(texts, [0.45, 0.55], [0.22, 0.30], img_w, img_h),
        "路面温度": extract_by_ratio(texts, [0.55, 0.65], [0.22, 0.30], img_w, img_h),
        "走行時間": extract_by_ratio(texts, [0.85, 0.98], [0.22, 0.30], img_w, img_h),
        "フィードバック": extract_by_ratio(texts, [0.20, 0.95], [0.80, 0.95], img_w, img_h)
    }

    # テーブル（33行分）
    rows = []
    for i in range(33):
        y_start = 0.42 + (i * 0.0125) # 行の間隔
        y_end = y_start + 0.0125
        rows.append({
            "Lap": i + 1,
            "Time": extract_by_ratio(texts, [0.40, 0.55], [y_start, y_end], img_w, img_h),
            "内圧FL": extract_by_ratio(texts, [0.58, 0.63], [y_start, y_end], img_w, img_h),
            "内圧FR": extract_by_ratio(texts, [0.63, 0.68], [y_start, y_end], img_w, img_h),
            "HV電圧": extract_by_ratio(texts, [0.80, 0.90], [y_start, y_end], img_w, img_h)
        })
    
    return h, pd.DataFrame(rows)

# --- 4. メイン画面 ---
st.title("🏎️ RaceLog Pro: 高精度・正常表示版")

col1, col2 = st.columns([1, 1])

with col1:
    st.subheader("1. 走行データ画像を選択")
    uploaded = st.file_uploader("", type=["jpg", "png", "jpeg"])
    if uploaded:
        st.image(uploaded, use_container_width=True)
        if st.button("AI解析を実行"):
            with st.spinner("テンプレ解析中..."):
                h, t = analyze_race_sheet(uploaded.read())
                key = h["No"] if h["No"] else f"Untitled_{len(st.session_state.all_data)}"
                st.session_state.all_data[key] = {"header": h, "table": t}

with col2:
    if st.session_state.all_data:
        current_no = st.selectbox("確認中のセッションNo:", list(st.session_state.all_data.keys()))
        data = st.session_state.all_data[current_no]
        
        st.subheader("2. 読み取り結果（修正可能）")
        for k, v in data["header"].items():
            data["header"][k] = st.text_input(k, v)
        
        st.subheader("3. タイヤ・ラップ詳細")
        data["table"] = st.data_editor(data["table"], hide_index=True)

        # Excel出力
        if st.button("このデータをExcelに保存"):
            buf = io.BytesIO()
            with pd.ExcelWriter(buf, engine='xlsxwriter') as writer:
                # テンプレに合わせ、1枚のシートにヘッダーとテーブルを書き込む
                pd.DataFrame([data["header"]]).to_excel(writer, sheet_name=f"No_{current_no}")
                data["table"].to_excel(writer, sheet_name=f"No_{current_no}", startrow=3)
            st.download_button("Excelファイルをダウンロード", buf.getvalue(), f"RaceLog_{current_no}.xlsx")
