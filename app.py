import os
import time
import configparser
from flask import Flask, request, abort, render_template, redirect, url_for, flash
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import (
    MessageEvent, AudioMessage, TextMessage, TextSendMessage, AudioSendMessage
)
import requests
import logging

app = Flask(__name__)
app.secret_key = 'os.urandom(24)'  # 用於未確定 key 前，先預設一組 key

# 設置Log記錄
logging.basicConfig(level=logging.INFO)

# Default configurations
config = configparser.ConfigParser()
CONFIG_FILE = 'config.ini'

if os.path.exists(CONFIG_FILE):
    config.read(CONFIG_FILE)
else:
    config['LINE'] = {
        'LINE_CHANNEL_ACCESS_TOKEN': '',    # 設定 LINE ACCESS_TOKEN
        'LINE_CHANNEL_SECRET': '',  # 設定 LINE CHANNEL SECRET
        'SERVER_URL': ''  # 設定 SERVER_URL 
    }
    with open(CONFIG_FILE, 'w') as configfile:
        config.write(configfile)

# 使用 get 方法提供默認值，避免 KeyError
LINE_CHANNEL_ACCESS_TOKEN = config.get('LINE', 'LINE_CHANNEL_ACCESS_TOKEN', fallback='')
LINE_CHANNEL_SECRET = config.get('LINE', 'LINE_CHANNEL_SECRET', fallback='')
SERVER_URL = config.get('LINE', 'SERVER_URL', fallback='')

STT_API_URL = 'http://180.218.16.187:30303/recognition_long_audio'
TTS_API_URL = 'http://180.218.16.187:30303/getTTSfromText'
LLM_API_URL = 'http://61.66.218.237:30304/getVLM'
SERVER_PORT = 10000 #免費空間 Render.com 預設 PORT

line_bot_api = None
line_handler = None

if LINE_CHANNEL_ACCESS_TOKEN and LINE_CHANNEL_SECRET:
    line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
    line_handler = WebhookHandler(LINE_CHANNEL_SECRET)

#語音轉文字 (需先架設好 Whisper Server)
def get_text_from_audio(audio_path):
    payload = {'doStyle': '0'}
    files = [
        ('audio', (os.path.basename(audio_path), open(audio_path, 'rb'), 'audio/mpeg'))
    ]
    headers = {}
    response = requests.post(STT_API_URL, headers=headers, data=payload, files=files)
    data = response.json()
    logging.info(f"STT=> {data}")
    return data.get('result', '無法辨識音訊')

#LLM語言模型 (需先架設好 LLM Server)
def get_response_from_llm(query):
    payload = {'query': query}
    files = []
    headers = {}
    response = requests.post(LLM_API_URL, headers=headers, data=payload, files=files)
    data = response.json()
    logging.info(f"LLM=> {data}")
    return data.get('result', '無法獲取回應')

#文字轉語音  (需先架設好 TTS Server)
def get_audio_from_text(text):
    payload = {
        'tone': '0',    #語音音高
        'speed': '0',   #語音速度
        'content': text,#語音內容
        'gender': '1'   #語音性別
    }
    headers = {}
    response = requests.post(TTS_API_URL, headers=headers, data=payload)
    audio_path = f'static/{int(time.time())}.mp3'
    with open(audio_path, 'wb') as f:
        f.write(response.content)
    return audio_path

@app.route("/", methods=["GET", "POST"])
def home():
    if request.method == "POST":
        token = request.form.get("LINE_CHANNEL_ACCESS_TOKEN")
        secret = request.form.get("LINE_CHANNEL_SECRET")
        server_url = request.form.get("SERVER_URL")
        
        config['LINE']['LINE_CHANNEL_ACCESS_TOKEN'] = token
        config['LINE']['LINE_CHANNEL_SECRET'] = secret
        config['LINE']['SERVER_URL'] = server_url
        
        with open(CONFIG_FILE, 'w') as configfile:
            config.write(configfile)
        
        global line_bot_api, line_handler, SERVER_URL
        line_bot_api = LineBotApi(token)
        line_handler = WebhookHandler(secret)
        SERVER_URL = server_url

        # 記錄LOG
        logging.info(f"LINE_CHANNEL_ACCESS_TOKEN: {token}")
        logging.info(f"LINE_CHANNEL_SECRET: {secret}")
        logging.info(f"SERVER_URL: {server_url}")

        # Dynamically add handlers after initialization
        add_line_handlers(line_handler)
        
        flash("設置成功，Line Bot 已啟動並且運作。")
        return redirect(url_for("home"))
    
    return '''
    <form method="post">
        LINE_CHANNEL_ACCESS_TOKEN: <input type="text" name="LINE_CHANNEL_ACCESS_TOKEN"><br>
        LINE_CHANNEL_SECRET: <input type="text" name="LINE_CHANNEL_SECRET"><br>
        SERVER_URL: <input type="text" name="SERVER_URL"><br>
        <input type="submit" value="Save">
    </form>
    '''

def add_line_handlers(handler):
    @handler.add(MessageEvent, message=AudioMessage)
    def handle_audio_message(event):
        message_content = line_bot_api.get_message_content(event.message.id)
        audio_path = f'static/{int(time.time())}.mp3'
        
        with open(audio_path, 'wb') as fd:
            for chunk in message_content.iter_content():
                fd.write(chunk)
        
        text = get_text_from_audio(audio_path)
        # 記錄LOG
        logging.info(f"STT: {text}")
        
        llm_response = get_response_from_llm(text)[0]['content']
        # 記錄LOG
        logging.info(f"LLM Reply: {llm_response}")
        
        reply_audio_path = get_audio_from_text(llm_response)
        # 記錄LOG
        logging.info(f"TTS: {reply_audio_path}")

        
        if os.path.exists(reply_audio_path):
            line_bot_api.reply_message(
                event.reply_token,
                [
                    TextSendMessage(text=llm_response),
                    AudioSendMessage(
                        original_content_url=f'{SERVER_URL}/{reply_audio_path}',
                        duration=330
                    )
                ]
            )
        else:
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="合成語音時錯誤，請檢查 TTS Server")
            )

    @handler.add(MessageEvent, message=TextMessage)
    def handle_text_message(event):
        text = event.message.text
        llm_response = get_response_from_llm(text)[0]['content']
        # 記錄LOG
        logging.info(f"LLM Reply: {llm_response}")
        
        reply_audio_path = get_audio_from_text(llm_response)
        # 記錄LOG
        logging.info(f"TTS: {reply_audio_path}")
        
        if os.path.exists(reply_audio_path):
            line_bot_api.reply_message(
                event.reply_token,
                [
                    TextSendMessage(text=llm_response),
                    AudioSendMessage(
                        original_content_url=f'{SERVER_URL}/{reply_audio_path}',
                        duration=330
                    )
                ]
            )
        else:
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="合成語音時錯誤，請檢查 TTS Server")
            )

@app.route("/webhook", methods=["POST"])
def callback():
    if not line_handler:
        abort(500, "LINE bot has not been configured.")
    
    signature = request.headers["X-Line-Signature"]
    body = request.get_data(as_text=True)
    
    try:
        line_handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return "OK"

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=SERVER_PORT)
