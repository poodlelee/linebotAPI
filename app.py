import os
import time
import requests
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import (
    MessageEvent, AudioMessage, TextSendMessage, AudioSendMessage
)

app = Flask(__name__)

# Configuration
LINE_CHANNEL_ACCESS_TOKEN = 'w4627SjiixmfjJ7LNg6U8q9L8Nh+NXgaN4ELtQ9FkxjO8oO0aVdT8L9J9eGT/qNM9IrLMzjcngjmCtPy+Qa70dxtU0e4e8F6NA6hwbIM3lppgmzwNMiC257n6Eq8eLt+buQ8lSfFFNQF1AJvRZGRIgdB04t89/1O/w1cDnyilFU='
LINE_CHANNEL_SECRET = '1d982942ffefc23710b07c6abc050cb1'
STT_API_URL = 'http://180.218.16.187:30303/recognition_long_audio'
TTS_API_URL = 'YOUR_TTS_API_URL'
SERVER_PORT = 10000

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
line_handler = WebhookHandler(LINE_CHANNEL_SECRET)

def get_text_from_audio(audio_path):
    # Prepare the payload and files for the STT API
    payload = {'doStyle': '0'}
    files = [
        ('audio', (os.path.basename(audio_path), open(audio_path, 'rb'), 'audio/mpeg'))
    ]
    headers = {}
    
    # Send the request to the STT API
    response = requests.post(STT_API_URL, headers=headers, data=payload, files=files)
    data = response.json()
    
    # Extract and return the transcription result
    return data.get('result', '無法辨識音訊')

def get_audio_from_text(text):
    params = {'content': text}
    response = requests.post(TTS_API_URL, data=params)
    audio_path = f'static/{int(time.time())}.mp3'
    with open(audio_path, 'wb') as f:
        f.write(response.content)
    return audio_path

@app.route("/webhook", methods=["POST"])
def callback():
    signature = request.headers["X-Line-Signature"]
    body = request.get_data(as_text=True)
    try:
        line_handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return "OK"

@app.route('/')
def home():
    return 'Hello World!'

@line_handler.add(MessageEvent, message=AudioMessage)
def handle_audio_message(event):
    user_id = event.source.user_id
    message_content = line_bot_api.get_message_content(event.message.id)
    audio_path = f'static/{int(time.time())}.mp3'
    
    with open(audio_path, 'wb') as fd:
        for chunk in message_content.iter_content():
            fd.write(chunk)
    
    text = get_text_from_audio(audio_path)
    reply_audio_path = get_audio_from_text(text)
    
    if os.path.exists(reply_audio_path):
        line_bot_api.reply_message(
            event.reply_token,
            [
                TextSendMessage(text=text),
                AudioSendMessage(
                    original_content_url=f'https://your-server.com/{reply_audio_path}',
                    duration=330
                )
            ]
        )
    else:
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="處理音訊時出錯")
        )

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=SERVER_PORT)
