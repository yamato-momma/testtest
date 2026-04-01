import streamlit as st
import pandas as pd
from google.cloud import vision
from google.oauth2 import service_account
import io
import json

# --- 1. スタイリッシュ＆高視認性デザイン ---
st.set_page_config(page_title="RaceLog Pro v4", layout="wide")
st.markdown("""
    <style>
    .stApp { background-color: #f4f7f9 !important; }
    h1, h2, h3, label { color: #1e3a8a !important; font-family: 'Segoe UI', sans-serif; }
    .stTextInput>div>div>input { background-color: white !important; color: black !important; border: 1px solid #1e3a8a !important; }
    .stDataEditor { background-color: white !important; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
    .css-10trblm { color: black !important; } /* Streamlit文字色補正 */
    </style>
    """, unsafe_allow_html=True)

# --- 2. Google Cloud 認証 ---
if "gcp_service_account" in st.secrets:
    info = json.loads(st.secrets["gcp_service_account"])
    credentials = service_account.Credentials.from_service_account_info(info)
    client = vision.ImageAnnotatorClient(credentials=credentials)
else:
    st.error("Secretsが設定されていません。")
    st.stop()

if 'all_sessions' not in st.session_state:
    st.session_state.all_sessions = {}

# --- 3. テンプレに基づくエリア抽出ロジック ---
def get_text_in_region(texts, x_min, x_max, y_min, y_max, img_width, img_height):
    """
    画像の比率（0.0〜1.0）で指定された範囲内のテキストを結合して返す
    """
    found_texts = []
    for text in texts[1:]:
        box = text.bounding_poly.vertices
        # 中心点を計算
        cx = sum([v.x for v in box]) / 4 / img_width
        cy = sum([v.y for v in box]) / 4 / img_height
        
        if x_min <= cx <= x_max and y_min <= cy <= y_max:
            found_texts.append(text.description)
    
    return "".join(found_texts)

def process_race_sheet_v4(content):
    image = vision.Image(content=content)
    # 画像サイズを取得するために一度デコード（Vision APIのメタデータでも可能だが簡易化）
    response = client.document_text_detection(image=image)
    texts = response.text_annotations
    if not texts: return None, None

    # 画像の全体サイズ（正規化用）
    # ※Vision APIの最初の要素のbounding_polyから全体のサイズを推測
    full_box = texts[0].bounding_poly.vertices
    img_w = full_box[1].x
    img_h = full_box[2].y

    # --- テンプレのセル位置を画像上の比率にマッピング (調整値) ---
    # ここは実際の画像の余白に合わせて微調整が必要ですが、一般的な比率で設定
    h = {
        "種目": get_text_in_region(texts, 0.1, 0.4, 0.15, 0.22, img_w, img_h),
        "ドライバー": get_text_in_region(texts, 0.4, 0.6, 0.15, 0.22, img_w, img_h),
        "走行場所": get_text_in_region(texts, 0.6, 0.8, 0.15, 0.22, img_w, img_h),
        "記録": get_text_in_region(texts, 0.8, 0.95, 0.15, 0.22, img_w, img_h),
        "天気": get_text_in_region(texts, 0.1, 0.2, 0.25, 0.32, img_w, img_h),
        "気温": get_text_in_region(texts, 0.2, 0.3, 0.25, 0.32, img_w, img_h),
        "湿度": get_text_in_region(texts, 0.3, 0.4, 0.25, 0.32, img_w, img_h),
        "路面状態": get_text_in_region(texts, 0.4, 0.55, 0.25, 0.32, img_w, img_h),
        "路面温度": get_text_in_region(texts, 0.55, 0.65, 0.25, 0.32, img_w, img_h),
        "開始時刻": get_text_in_region(texts, 0.7, 0.85, 0.23, 0.27, img_w, img_h),
        "終了時刻": get_text_in_region(texts, 0.7, 0.85, 0.27, 0.31, img_w, img_h),
        "走行時間": get_text_in_region(texts, 0.85, 0.95, 0.25, 0.32, img_w, img_h),
        "セッティング": get_text_in_region(texts, 0.3, 0.6, 0.33, 0.38, img_w, img_h),
        "No": get_text_in_region(texts, 0.8, 0.98, 0.12, 0.16, img_w, img_h),
        "フィードバック": get_text_in_region(texts, 0.1, 0.9, 0.8, 0.95, img_w, img_h)
    }

    # テーブル（ラップタイム等）は行の高さから計算
    rows = []
    for i in range(1, 34):
        y_top = 0.42 + (i-1) * 0.012  # 1行あたりの高さを計算
        row = {
            "Lap": i,
            "Time": get_text_in_region(texts, 0.38, 0.52, y_top, y_top+0.012, img_w, img_h),
            "内圧FL": get_text_in_region(texts, 0.58, 0.63, y_top, y_top+0.012, img_w, img_h),
            "内圧FR": get_text_in_region(texts, 0.63, 0.68, y_top, y_top+0.012, img_w, img_h),
            # 以下、他の項目も同様のロジックで追加可能
        }
        rows.append(row)
    
    return h, pd.DataFrame(rows)

# --- 4. メインUI ---
st.title("🏎️ RaceLog Pro v4: テンプレ解析モード")

tab1, tab2 = st.tabs(["📤 解析", "📈 エクスポート"])

with tab1:
    col_l, col_r = st.columns([1, 1])
    with col_l:
        file = st.file_uploader("ログシート画像をアップロード", type=["jpg", "png", "jpeg"])
        if file:
            st.image(file, use_container_width=True)
            if st.button("AI高精度解析を実行"):
                h, t = process_race_sheet_v4(file.read())
                key = h["No"] if h["No"] else f"Session_{len(st.session_state.all_sessions)}"
                st.session_state.all_sessions[key] = {"header": h, "table": t}

    with col_r:
        if st.session_state.all_sessions:
            curr = st.selectbox("編集中のNo:", list(st.session_state.all_sessions.keys()))
            data = st.session_state.all_sessions[curr]
            
            # ヘッダー編集
            st.subheader("📋 ヘッダー情報 (修正可)")
            cols = st.columns(3)
            for i, (k, v) in enumerate(data["header"].items()):
                if k == "フィードバック": continue
                data["header"][k] = cols[i % 3].text_input(k, v)
            
            data["header"]["フィードバック"] = st.text_area("フィードバック", data["header"]["フィードバック"])
            
            st.subheader("⏱️ タイム・内圧データ")
            data["table"] = st.data_editor(data["table"], hide_index=True)

with tab2:
    if st.session_state.all_sessions:
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine='xlsxwriter') as writer:
            for no, d in st.session_state.all_sessions.items():
                pd.DataFrame([d["header"]]).to_excel(writer, sheet_name=f"No_{no}", index=False)
                d["table"].to_excel(writer, sheet_name=f"No_{no}", startrow=3, index=False)
        st.download_button("Excelダウンロード", buf.getvalue(), "Result.xlsx")
