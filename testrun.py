import streamlit as st
import pandas as pd
from google.cloud import vision
from google.oauth2 import service_account
import io
import json

# --- 設定 ---
st.set_page_config(page_title="走行データ変換くん", layout="wide")
st.title("🏎️ 走行データシート ➔ Excel変換")

# Google Cloud Visionの認証設定
# StreamlitのSecrets機能（後述）から読み込む設定にしています
if "gcp_service_account" in st.secrets:
    info = json.loads(st.secrets["gcp_service_account"])
    credentials = service_account.Credentials.from_service_account_info(info)
    client = vision.ImageAnnotatorClient(credentials=credentials)
else:
    st.warning("Google Cloudの認証情報が設定されていません。")
    st.stop()

# --- ファイルアップロード ---
uploaded_file = st.file_uploader("ログシートの画像をアップロードしてください", type=["jpg", "jpeg", "png"])

if uploaded_file is not None:
    st.image(uploaded_file, caption="アップロード画像", width=400)
    
    if st.button("解析開始"):
        with st.spinner('AIが読み取り中...'):
            content = uploaded_file.read()
            image = vision.Image(content=content)
            
            # OCR実行（手書きに強いドキュメントモード）
            response = client.document_text_detection(image=image)
            text_data = response.full_text_annotation.text

            # 簡易的なデータ抽出（本来は座標指定が必要ですが、まずは全テキストを抽出）
            # ここで定型フォーマットに合わせた加工ロジックを入れます
            lines = text_data.split('\n')
            
            st.subheader("読み取り結果（プレビュー）")
            st.text_area("抽出されたテキスト", text_data, height=200)

            # Excel作成
            df = pd.DataFrame({"項目": ["抽出データ"], "内容": [text_data]})
            
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                df.to_excel(writer, index=False, sheet_name='Sheet1')
            
            st.success("解析完了！")
            st.download_button(
                label="Excelファイルをダウンロード",
                data=output.getvalue(),
                file_name="race_data.xlsx",
                mime="application/vnd.ms-excel"
            )