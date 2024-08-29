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
app.secret_key = 'your_secret_key'  # 用于flash消息

# 设置日志记录
logging.basicConfig(level=logging.INFO)

# Default configurations
config = configparser.ConfigParser()
CONFIG_FILE = 'config.ini'

if os.path.exists(CONFIG_FILE):
    config.read(CONFIG_FILE)
else:
    config['LINE'] = {
        'LINE_CHANNEL_ACCESS_TOKEN': '',
        'LINE_CHANNEL_SECRET': '',
        'SERVER_URL': ''  # 确保在配置文件中存在 SERVER_URL 键
    }
    with open(CONFIG_FILE, 'w') as configfile:
        config.write(configfile)

# 使用 get 方法提供默认值，避免 KeyError
LINE_CHANNEL_ACCESS_TOKEN = config.get('LINE', 'LINE_CHANNEL_ACCESS_TOKEN', fallback='')
LINE_CHANNEL_SECRET = config.get('LINE', 'LINE_CHANNEL_SECRET', fallback='')
SERVER_URL = config.get('LINE', 'SERVER_URL', fallback='')

STT_API_URL = 'http://180.218.16.187:30303/recognition_long_audio'
TTS_API_URL = 'http://180.218.16.187:30303/getTTSfromText'
LLM_API_URL = 'http://61.66.218.237:30304/getVLM'
SERVER_PORT = 10000

line_bot_api = None
line_handler = None

if LINE_CHANNEL_ACCESS_TOKEN and LINE_CHANNEL_SECRET:
    line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
    line_handler = WebhookHandler(LINE_CHANNEL_SECRET)

def get_text_from_audio(audio_path):
    payload = {'doStyle': '0'}
    files = [
        ('audio', (os.path.basename(audio_path), open(audio_path, 'rb'), 'audio/mpeg'))
    ]
    headers = {}
    response = requests.post(STT_API_URL, headers=headers, data=payload, files=files)
    data = response.json()
    return data.get('result', '無法辨識音訊')

def get_response_from_llm(query):
    payload = {'query': query}
    files = []
    headers = {}
    response = requests.post(LLM_API_URL, headers=headers, data=payload, files=files)
    data = response.json()
    return data.get('result', '無法獲取回應')

def get_audio_from_text(text):
    payload = {
        'tone': '0',
        'speed': '0',
        'content': text,
        'gender': '1'
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

        # 记录日志
        logging.info(f"LINE_CHANNEL_ACCESS_TOKEN: {token}")
        logging.info(f"LINE_CHANNEL_SECRET: {secret}")
        logging.info(f"SERVER_URL: {server_url}")

        # Dynamically add handlers after initialization
        add_line_handlers(line_handler)
        
        flash("设置成功，Line Bot 已启动并运行。")
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
        llm_response = get_response_from_llm(text)[0]['content']
        reply_audio_path = get_audio_from_text(llm_response)
        
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
                TextSendMessage(text="處理音訊時出錯")
            )

    @handler.add(MessageEvent, message=TextMessage)
    def handle_text_message(event):
        text = event.message.text
        llm_response = get_response_from_llm(text)[0]['content']
        reply_audio_path = get_audio_from_text(llm_response)
        
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
                TextSendMessage(text="處理音訊時出錯")
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
