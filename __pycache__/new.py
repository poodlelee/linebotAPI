import os
import time
import json
import linebot
import requests
import random
import ssl
from flask import Flask, flash, request, redirect, url_for, abort, jsonify
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import (
    MessageEvent,
    AudioMessage,
    TextMessage,
    ImageMessage,
    TextSendMessage,
    AudioSendMessage,
    FileMessage,
    VideoSendMessage,
    ImageSendMessage,
    TemplateSendMessage, 
    ButtonsTemplate, 
    URITemplateAction,
    MessageTemplateAction,
    CarouselTemplate, 
    CarouselColumn,
    ImageCarouselTemplate, 
    ImageCarouselColumn,
    URIAction
)

import webuiapi

from pydub import AudioSegment
from gradio_client import Client

import hashlib
import shutil
import fitz
from PIL import Image, ImageDraw, ImageFont
from urllib.parse import quote
import opencc
converter = opencc.OpenCC('s2t')

from googleapiclient.discovery import build
from bs4 import BeautifulSoup
#from transformers import AutoTokenizer, AutoModelForSeq2SeqLM
import base64
#from werkzeug.utils import secure_filename

import pytesseract
import re
import html
import mimetypes
import configparser
configSys = configparser.ConfigParser()
configUsr = configparser.ConfigParser()
# 讀取現有的 system.ini 檔案
configSys.read(f'config/system.ini')

import warnings
warnings.filterwarnings("ignore")

serverPort = configSys.get('net', 'port')#30303

app = Flask(__name__)

line_bot_api = LineBotApi(configSys.get('line', 'token'))
line_handler = WebhookHandler(configSys.get('line', 'scret'))

#working_status = True
working_list = []

#特殊字詞取代
with open('_newTongWenTang.json', 'r', encoding='utf-8') as json_file:
    CN2TW_dict = json.load(json_file)
def CN2TW(answer):
    #print(CN2TW_dict)
    for key, value in CN2TW_dict.items():
        answer = answer.replace(key, value)
    return answer

#特殊字取代 並且轉繁體中文    
def text2result(text):
    if text == '':
        return text
        
    return CN2TW(converter.convert(html.unescape(text.replace("'","、").replace('"','\"').replace('"',"“"))))
    
#image疊上text
def imageANDtext(image, text, ff = True):
    text_border_color = (0, 0, 0)  # 黑色
    text_border_width = 5

    # 定义文字颜色（根据图像的颜色来调整）
    text_color = image.getpixel((0, 0))  # 获取左上角的像素颜色

    # 定义文字透明度
    text_opacity = 128  # 0为完全透明，255为不透明

    # 选择字体和字号
    font = ImageFont.truetype('NotoSansTC-Black.ttf', 72)

    # 创建一个与图像相同大小的图像对象，作为文字的背景
    text_background = Image.new('RGBA', image.size, (255, 255, 255, 0))

    # 创建一个可绘制的图像对象
    draw = ImageDraw.Draw(text_background)

    # 计算文本的位置（例如，在图像顶部居中）
    text_width, text_height = draw.textsize(text, font)
    image_width, image_height = image.size
    if text_width > image_width:
        font = ImageFont.truetype('NotoSansTC-Black.ttf', 48)
        text_width, text_height = draw.textsize(text, font)
        image_width, image_height = image.size
        
    if ff:
        # 获取图像的尺寸
        image_width, image_height = image.size

        # 获取四个位置的颜色信息
        top_left_color = image.getpixel((0, 0))
        top_right_color = image.getpixel((image_width - 1, 0))
        bottom_left_color = image.getpixel((0, image_height - 1))
        bottom_right_color = image.getpixel((image_width - 1, image_height - 1))

        # 定义颜色阈值来判断颜色相似性
        color_threshold = 50

        # 判断颜色相似性并推测位置
        if abs(top_left_color[0] - top_right_color[0]) > color_threshold:
            horizontal_position = "Center"
            x = (image_width - text_width) // 2
        else:
            if top_left_color[0] > 128:
                horizontal_position = "Left"
                x = (image_width*2/10 - text_width) // 2
            else:
                horizontal_position = "Right"
                x = (image_width*6/10 - text_width) // 2

        if abs(top_left_color[0] - bottom_left_color[0]) > color_threshold:
            vertical_position = "Center"
            y = image_height*2/5 
        else:
            if top_left_color[0] > 128:
                vertical_position = "Top"
                y = image_height*1/5  # 距离顶部的距离
            else:
                vertical_position = "Bottom"
                y = image_height*3/5  # 距离顶部的距离  
        if x < 0:
            x = 10
        print("大概位置：{} {}".format(vertical_position, horizontal_position))
    else:
        x = (image_width*24/25 - text_width) // 2
        y = image_height*24/25  # 距离顶部的距离
        font = ImageFont.truetype('NotoSansTC-Black.ttf', 32)
        text_opacity = 255
        
    try:
        text_color = (255, 255, 255)#image.getpixel((x, y))
        print(x,y)
    except:
        x = (image_width*10/25 + text_width) // 2
        y = image_height*10/25  # 距离顶部的距离
        text_color = image.getpixel((x, y))
        
    # 在文字背景上绘制边框
    draw.text((x - text_border_width, y), text, font=font, fill=text_border_color)
    draw.text((x + text_border_width, y), text, font=font, fill=text_border_color)
    draw.text((x, y - text_border_width), text, font=font, fill=text_border_color)
    draw.text((x, y + text_border_width), text, font=font, fill=text_border_color)


    # 在文字背景上绘制文字
    draw.text((x, y), text, font=font, fill=(text_color[0], text_color[1], text_color[2], text_opacity))

    # 将文字背景与原图像合并
    result_image = Image.alpha_composite(image.convert('RGBA'), text_background)
    
    return result_image


def convert_pdf_to_image(pdf_path, image_path):
    extendFileName = file_extension = os.path.splitext(pdf_path)[1]
    extendFileName = extendFileName.lstrip(".")
    print(extendFileName)
    
    if os.path.exists(image_path):
        return image_path
    
    extendFileName = pdf_path.split('.')[1]
    app.logger.info(extendFileName)
    if  extendFileName == 'doc' or extendFileName == 'docx':
        shutil.copy(f"images/file_icon_text_doc.png", image_path)
        return image_path
    elif extendFileName == 'xls' or extendFileName == 'xlsx':
        shutil.copy(f"images/file_icon_text_xls.png", image_path)
        return image_path
    elif extendFileName == 'txt':
        shutil.copy(f"images/file_icon_text_txt.png", image_path)
        return image_path  
    elif extendFileName == 'ppt' or extendFileName == 'pptx':   
        shutil.copy(f"images/file_icon_text_ppt.png", image_path)
        return image_path 
    elif extendFileName == 'csv':
        shutil.copy(f"images/file_icon_text_csv.png", image_path)
        return image_path     
    elif extendFileName == 'pdf':    
        # 打開PDF檔案
        pdf_document = fitz.open(pdf_path)
        
        # 讀取第一頁
        first_page = pdf_document[0]
        
        # 設定截圖參數（DPI為截圖的解析度）
        zoom_x = configSys.get('pdf2img', 'zoom_x')  # 選擇一個適合的比例
        zoom_y = configSys.get('pdf2img', 'zoom_y')
        mat = fitz.Matrix(zoom_x, zoom_y)
        
        # 進行截圖並存成PNG
        pix = first_page.get_pixmap(matrix=mat)
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        img.save(image_path)  # 直接儲存，不需要指定 format
        
        # 關閉PDF檔案
        pdf_document.close()
        
        return image_path
    else:
        shutil.copy(f"images/thumbnail_file_icon_text.jpg", image_path)
        return image_path
        
def extract_images_from_pdf(pdf_path, image_folder):
    path_parts = image_folder.split("/")
    # 如果你想獲取路徑部分中的目錄，你可以使用以下方式
    path = "/".join(path_parts[:-1])
    path = f'{path}/images'
    if not os.path.exists(path):
        # 如果路径不存在，使用os.makedirs创建它
        os.makedirs(path)
        
    # 打开PDF文件
    pdf_document = fitz.open(pdf_path)

    # 遍历PDF的每一页
    for page_number in range(len(pdf_document)):
        page = pdf_document.load_page(page_number)
        xrefs = page.get_images(full=True)

        # 遍历每一个图像
        for i, xref in enumerate(xrefs):
            base_image = pdf_document.extract_image(xref[0])
            image_data = base_image["image"]

            # 将图像数据保存为PNG文件
            with open(f"{path}/{page_number}_{i + 1}.png", "wb") as image_file:
                image_file.write(image_data)

    # 關閉PDF文件
    pdf_document.close()

class STATUS:
    def __init__(self) -> None:
        self.TTSurl = configSys.get('TTS', 'TTSurl')#"http://61.66.218.102:30305/getTTSfromText"
        self.STTurl = configSys.get('STT', 'STTurl')#"http://180.218.16.187:30303/recognition_long_audio"
        self.CHATurl = configSys.get('GLM', 'CHATurl')#"https://linebot.iservmeta.org:30300/getGLM" #"http://180.218.16.187:30302/"
        self.streamOut = configSys.get('GLM', 'streamOut')#False
        self.onlineSearch = configSys.get('GLM', 'onlineSearch')#False          
            

        self.SDurl = configSys.get('SD', 'TXT2IMGurl')

        # 建立YouTube Data API物件
        self.youtube = build('youtube', 'v3', developerKey=configSys.get('youtube', 'developerKey'))#'AIzaSyDFErkO6W4XrXj4kAGwG8TeoqUEkNy9Vpw  ')
        self.BAD_RECORD_TEXT = configSys.get('statusTEXT', 'BAD_RECORD_TEXT')#" 錄音狀況不佳，請再重新發送"
        
        self.GOOD_FILE_TYPE = ("pdf", "doc", "txt", "csv", "pptx", "xlsx", "docx", "json")
        self.outputPathPNG = ''
        self.TTS_P_GENDER = configSys.get('TTS', 'TTS_P_GENDER')#1
        self.TTS_P_TONE = configSys.get('TTS', 'TTS_P_TONE')#0
        self.TTS_P_SPEED = configSys.get('TTS', 'TTS_P_SPEED')#20
        

        #self.tokenizer = AutoTokenizer.from_pretrained("Helsinki-NLP/opus-mt-zh-en")
        #self.model = AutoModelForSeq2SeqLM.from_pretrained("Helsinki-NLP/opus-mt-zh-en")
        
        self.MessageKeywords = ['早安','午安','晚安','達玲','倪甄','文豪','星豪','西北歌王']#,'颱風','台風','臺風','檢索','旅遊','搜尋']
        self.MessageKeywordsQ = ['早安 古典音樂','午安 古典音樂','晚安 古典音樂','達玲 台語歌曲','倪甄 歌曲','文豪主唱 星豪','星豪唱片','西北歌王 小玲 星豪']#,'颱風動態','台風動態','臺風動態','!!@@##','!!@@##','!!@@##']
        self.KM_id = 'all'
        self._3Dpic = ''

    def set_config_to_ini(self, user_id: str) -> None:
        if os.path.exists(f'static/{user_id}/config.ini'):
            # 刪除檔案
            os.remove(f'static/{user_id}/config.ini')
            app.logger.info(f"static/{user_id}/config.ini 檔案已刪除")
        else:
            app.logger.error("static/{user_id}/config.ini 檔案不存在")
        
        # 將參數寫入 config.ini 檔案
        folder_path = f'static/{user_id}/'

        # 檢查目錄是否存在，若不存在則建立目錄
        if not os.path.exists(folder_path):
            os.makedirs(folder_path)
            
        # 開啟檔案並寫入
        with open(f'static/{user_id}/config.ini', 'w+') as configfile:
            configUsr.write(configfile)
        app.logger.info(f"static/{user_id}/config.ini 檔案已寫入")

    def get_config_from_ini(self, user_id: str) -> None:
        # 讀取現有的 config.ini 檔案
        configUsr.read(f'static/{user_id}/config.ini')

    def check_record_is_good(self, text: str) -> bool:
        if text == self.BAD_RECORD_TEXT:
            return False
        else:
            return True

    def check_file_is_good(self, file_name: str) -> bool:
        if file_name.endswith(self.GOOD_FILE_TYPE):
            return True
        else:
            return False

    def get_reply_text(self, user_id: str, query: str) -> str:
        # 取得 Line Bot 的頻道資訊
        bot_info = line_bot_api.get_bot_info()
        
        # 獲取 Line Bot 的名稱
        bot_name = bot_info.display_name

        headers = {}

        chatbot_params = {
            "user_id": user_id,
            "question":query
        } 
        chatbot_response = requests.post(self.CHATurl, headers=headers, data=chatbot_params)

        reply_text = self.get_lineID_to_lineDisplayName(user_id) + ' ' +converter.convert(chatbot_response.json()['answer'])
        reply_text = reply_text.replace('AI語言模型',f'{bot_name}').replace('ChatGLM2-6B',f'{bot_name}').replace('ChatGLM',f'{bot_name}').replace('清華大學KEG實驗室和智譜AI公司','阿夢兄').replace('清華大學 KEG 實驗室和智譜 AI 公司','阿夢兄').replace('2023 年共同訓練','2023年7月建置').replace('語言模型','語意理解機制').replace('信息','資訊').replace('GLM2-6B',f'{bot_name}').replace('2022 年共同訓練','2023年7月建置')
        return reply_text    

    def get_audio_tts_output_path(self, user_id: str, reply_text: str) -> str:
        try:
            audio_tts_output_path = f"static/{user_id}/output_{time.time()}.mp3"
            print(f'====> {reply_text}')
            if '😃\n' in reply_text:
                reply_text = reply_text.split('😃\n')[1]
                #print(reply_text)
            tts_params = {
                "content": str(reply_text),
                "gender": configSys.get('TTS', 'TTS_P_GENDER'), #self.TTS_P_GENDER,
                "tone": configSys.get('TTS', 'TTS_P_TONE'), #self.TTS_P_TONE,
                "speed": configSys.get('TTS', 'TTS_P_SPEED'), #self.TTS_P_SPEED,
            }
            audio_tts_response = requests.request("POST", self.TTSurl, data=tts_params)
            os.makedirs(os.path.dirname(audio_tts_output_path), exist_ok=True)
            with open(audio_tts_output_path, "wb") as fd:
                for chunk in audio_tts_response:
                    fd.write(chunk)
        except Exception as e:
            print(str(e))
        return audio_tts_output_path

    def get_user_audio_input_path(
        self, user_id: str, user_send_audio: linebot.models.responses.Content
    ) -> str:
        audio_input_path = f"static/{user_id}/input_{time.time()}.mp3"
        os.makedirs(os.path.dirname(audio_input_path), exist_ok=True)
        with open(audio_input_path, "wb") as fd:
            for chunk in user_send_audio.iter_content():
                fd.write(chunk)
        return audio_input_path

    def get_user_audio_output_path(self, user_id: str) -> str:
        audio_output_path = f"static/{user_id}/input_{time.time()}.mp3"
        return audio_output_path

    def get_text_from_audio_path(self, user_id: str, audio_path: str) -> str:
        data = {"doStyle": configSys.get('STT', 'doStyle')}#0}
        files = {"audio": open(audio_path, "rb")}
        stt_response = requests.request("POST", self.STTurl, files=files, data=data)
        #print(stt_response)
        #print(stt_response.text)
        try:
            text = eval(stt_response.content.decode("utf-8"))["result"]
        except Exception as e:
            print(e)
            text = self.BAD_RECORD_TEXT
        return text

    def get_user_file_input_path(
        self,
        user_id: str,
        user_send_file: linebot.models.responses.Content,
        user_send_file_name: str,
    ) -> str:
        file_input_path = f"static/{user_id}/{user_send_file_name}"
        os.makedirs(os.path.dirname(file_input_path), exist_ok=True)
        with open(file_input_path, "wb") as f:
            for chunk in user_send_file.iter_content():
                f.write(chunk)
        return file_input_path

    def get_text_from_file(self, file_path: str) -> str:
        text = textract.process(file_path).decode("utf-8")
        return text

    def save_text_to_txt(self, user_id:str, text:str) -> str:
        txt_file_path = f"static/{user_id}/{time.time()}.txt"
        with open(txt_file_path, "w") as f:
            f.write(text)
        return txt_file_path
     
    def get_lineID_to_lineDisplayName(self, user_id: str) -> str:
        try:
            # 使用Line Bot API取得使用者的Profile資訊
            profile = line_bot_api.get_profile(user_id)
            # 獲取使用者的Line名字
            display_name = f'😃{profile.display_name}😃\n'
        except:
            display_name = f'😃夥伴😃\n'
        return display_name
        
    def get_txtTrans(self, text: str) -> str:
        print(f'========>{text}')
        if bool(re.match(r"^[a-zA-Z\s,!?.;]*$", text)):
            return text
    
        url = "https://linebot.iservmeta.org:30300/getGLM"

        payload = {'question': f'請將「{text}」翻譯成英文'}
        files=[

        ]
        headers = {}

        response = requests.request("POST", url, headers=headers, data=payload, files=files)

        print(response.json()['answer'])
        #batch = self.tokenizer(text, return_tensors="pt")
        #translation = self.model.generate(**batch)
        #result = self.tokenizer.batch_decode(translation, skip_special_tokens=True)
        #txt="".join(result)
        txt = response.json()['answer'][1:-2]
        print(txt)
        return txt

    def save_encoded_image(self, user_id:str, b64_image: str, output_path: str):
        """
        Save the given image to the given output path.
        """
        picSavePath = f'static/{user_id}/{output_path}'
        with open(picSavePath, "wb") as image_file:
            image_file.write(base64.b64decode(b64_image))

    def get_SD_pic(self, user_id:str, userInput: str) -> str:
        # create API client
        api = webuiapi.WebUIApi()
        # create API client with custom host, port
        api = webuiapi.WebUIApi(host='180.218.16.187', port=30302)
        
        api.set_auth('username', 'password')
        outputPath= str(int(time.time()))
        outputPathPNG = outputPath + '.png'
        prompt = []
        promptTmp = userInput.split(' ')[1:]
        #for tmp in promptTmp:
        #    print(tmp)
        #    prompt.append(self.get_txtTrans(tmp))
        #prompt = ','.join(prompt)
        #prompt = prompt.replace('.','')
        promptTmp = ' '.join(promptTmp)
        print(promptTmp)
        try:
            if '/' in promptTmp:
                # 找到第一個 / 的位置
                start_idx = promptTmp.find('/')
                # 找到第二個 / 的位置
                end_idx = promptTmp.find('/', start_idx + 1)

                # 如果找到了兩個 /，就擷取之間的文字
                if start_idx != -1 and end_idx != -1:
                    extracted_text = promptTmp[start_idx + 1:end_idx]
                    # 從原始字符串中刪除被擷取的文字
                    promptTmp = promptTmp.replace('/' + extracted_text + '/', '')

                print("擷取的文字：", extracted_text)
                print("剩餘的字串：", promptTmp)
            else:
                extracted_text = ''
                
            if '_' in promptTmp:
                # 找到第一個 _ 的位置
                start_idx = promptTmp.find('_')
                # 找到第二個 _ 的位置
                end_idx = promptTmp.find('_', start_idx + 1)

                # 如果找到了兩個 _，就擷取之間的文字
                if start_idx != -1 and end_idx != -1:
                    extracted_text_maker = promptTmp[start_idx + 1:end_idx]
                    # 從原始字符串中刪除被擷取的文字
                    promptTmp = promptTmp.replace('_' + extracted_text_maker + '_', '')
            else:
                if '😃夥伴' in status.get_lineID_to_lineDisplayName(user_id):
                    extracted_text_maker = f'尚未將{configSys.get("system", "name")}加入好友'
                else:
                    extracted_text_maker = status.get_lineID_to_lineDisplayName(user_id).replace('😃','').replace(' ','_')#configSys.get('system', 'name')
                    
            try:
                print("擷取的文字：", extracted_text_maker)
            except:
                extracted_text_maker = '阿夢兄'
            print("剩餘的字串：", promptTmp)    
        except:
            promptTmp = '日本 櫻花 富士山'
            extracted_text = '''語法有誤
            txt2image /文字內容/ 畫圖咒語'''
            extracted_text_maker = '阿夢兄'
            
    

        prompt = self.get_txtTrans(promptTmp.replace('_',' ').replace('\n',', '))
        print(prompt)
        
        result1 = api.txt2img(prompt = prompt + ',best quality, ultra high res, high detailed,8K,HDR,(best quality:1.4),(masterpiece:1.4),digital painting of Vallaria',
                            negative_prompt = "paintings, sketches, (worst quality:2), (low quality:2), (normal quality:2), lowres, normal quality, ((monochrome)), ((grayscale)), skin spots, acnes, skin blemishes, age spot, glans, EasyNegative, paintings, sketches, (worst quality:2), (low quality:2), (normal quality:2), lowres, ((monochrome)), ((grayscale)), skin spots, acnes, skin blemishes, age spot, glans,extra fingers,fewer fingers,strange fingers,bad hand,signature, watermark, username, blurry, bad feet,bad leg, duplicate, extra limb, ugly, disgusting, poorly drawn hands, missing limb, floating limbs, disconnected limbs, malformed hands, blurry,mutated hands and fingers,, EasyNegative, paintings, sketches, (worst quality:2), (low quality:2), (normal quality:2), lowres, ((monochrome)), ((grayscale)), skin spots, acnes, skin blemishes, age spot, glans,extra fingers,fewer fingers,strange fingers,bad hand,signature, watermark, username, blurry, bad feet,bad leg,(nude:1.3),(depth_of_field:1.8),(DOF:1.8),(blur:1.8),motion_blur,caustics,bokeh,overexposure,blurry_background,blurry_foreground,simple_background,NSFW,nsfw,nipple,nude,",
                            seed = -1,
                            styles=["Watercolor Effect ", "Dreamy or Ethereal Style", "Glowing or Halo Effect"],#anime
                    cfg_scale=8,
                    sampler_index='DDIM',
                            steps=80,
                            #width= 512,
                            #height= 512,
                            #restore_faces= True,
                            #seed_resize_from_h= 4,
                            #seed_resize_from_w= 4,
                              enable_hr=True,
                              hr_scale=3,
                              hr_upscaler=webuiapi.HiResUpscaler.Latent,
                              hr_second_pass_steps=20,
                            hr_resize_x=1080,
                            hr_resize_y=1080,
                              denoising_strength=0.45,

        )
        #unit1 = webuiapi.ControlNetUnit(input_image=result1.image, module='canny', model='control_sd15_canny [fef5e48e]')
        #unit2 = webuiapi.ControlNetUnit(input_image=result1.image, module='depth', model='control_sd15_depth [fef5e48e]', weight=0.5)
        #unit3 = webuiapi.ControlNetUnit(input_image=result1.image, module='shuffle', model='control_v11e_sd15_shuffle [526bfdae]', weight=0.9)
        
        #r2 = api.img2img(prompt = prompt,
        #            images=[result1.image], 
        #            width=1024,
        #            height=1024,
        #            controlnet_units=[unit1, unit2],
        #            sampler_name="Euler a",
        #            cfg_scale=9,
        #)
        result_image = imageANDtext(result1.image, extracted_text)

        result_image = imageANDtext(result_image, f'Made By {extracted_text_maker}', False)        
        picSavePath = f'static/{user_id}/{outputPathPNG}'
        #r2.image.save(picSavePath)
        result_image.save(picSavePath)
        
        #data = {
        #    'prompt': prompt,
        #    'negative_prompt': "EasyNegative, paintings, sketches, (worst quality:2), (low quality:2), (normal quality:2), lowres, ((monochrome)), ((grayscale)), skin spots, acnes, skin blemishes, age spot, glans,extra fingers,fewer fingers,strange fingers,bad hand,signature, watermark, username, blurry, bad feet,bad leg, duplicate, extra limb, ugly, disgusting, poorly drawn hands, missing limb, floating limbs, disconnected limbs, malformed hands, blurry,mutated hands and fingers,, EasyNegative, paintings, sketches, (worst quality:2), (low quality:2), (normal quality:2), lowres, ((monochrome)), ((grayscale)), skin spots, acnes, skin blemishes, age spot, glans,extra fingers,fewer fingers,strange fingers,bad hand,signature, watermark, username, blurry, bad feet,bad leg,(nude:1.3),(depth_of_field:1.8),(DOF:1.8),(blur:1.8),motion_blur,caustics,bokeh,overexposure,blurry_background,blurry_foreground,simple_background,NSFW,nsfw,nipple,nude,",
        #    'sampler_index': 'DPM++ SDE Karras',
        #    'seed': -1,
        #    'steps': 28,
        #    'width': 512,
        #    'height': 512,
        #    'cfg_scale': 9,
        #    "batch_size": 1,
        #    "restore_faces": "true",
        #    "denoising_strength": 0.02,
        #    "seed_resize_from_h": 4,
        #    "seed_resize_from_w": 4
        #}       
        #response = requests.post(self.SDurl, data=json.dumps(data), timeout=3600)
        #self.save_encoded_image(user_id, response.json()['images'][0], outputPathPNG)
        
        return outputPathPNG
        
    def get_youtube_result(self, user_message: str) -> list:
        # 使用YouTube Data API進行搜尋
        search_response = self.youtube.search().list(
            q=user_message,
            part='id,snippet',
            maxResults=10,
            type='video'
        ).execute()
        
        result = []
        my_list = [0,1,2]
        random.shuffle(my_list)
        my_list.extend([3,4,5])
        for idx in my_list:
            result.append([search_response['items'][idx]['snippet']['title'], f"https://www.youtube.com/watch?v={search_response['items'][idx]['id']['videoId']}", search_response['items'][idx]['snippet']['thumbnails']['medium']['url']])
        return result

    def contains_chinese_english_digits(slef, text: str) -> bool:
        pattern = re.compile(r'[\u4e00-\u9fa5a-zA-Z0-9]+')
        match = pattern.search(text)
        return bool(match)
 
    def get3Dvideo(self, outputPathMP3, _3Dpic):
        file_path = outputPathMP3
        pic_path = _3Dpic
        print(file_path, pic_path)
        
        client = Client(self._3Durl)    

        result = client.predict(
                        pic_path,	# str (filepath or URL to image) in 'Source image' Image component
                        file_path,	# str (filepath or URL to file) in 'Input audio' Audio component
                        "full",	# str  in 'preprocess' Radio component
                        True,	# bool  in 'Still Mode (fewer hand motion, works with preprocess `full`)' Checkbox component
                        False,	# bool  in 'GFPGAN as Face enhancer' Checkbox component
                        1,	# int | float (numeric value between 0 and 10) in 'batch size in generation' Slider component
                        256,	# str  in 'face model resolution' Radio component
                        0,	# int | float (numeric value between 0 and 46) in 'Pose style' Slider component
                        fn_index=1
        )
        
        video_path = result
        # 定義 A 資料夾路徑和 B 資料夾路徑
        folder_a = video_path
        folder_b = ''

        # 定義檔案 C 的檔案名稱
        file_c = outputPathMP3.split('.')[0] + '.mp4'

        # 組合完整的檔案路徑
        #file_a = os.path.join(folder_a, '')
        file_b = os.path.join(folder_b, file_c)

        # 複製檔案
        shutil.copyfile(folder_a, file_b)
        file_path = file_b

        print(result)
        return (file_b,pic_path)
    def chkMessageKeywords(self, user_id: str, userInput):
        message = []
        indexes = []
        for index, substr in enumerate(self.MessageKeywords):
            if substr in userInput:
                indexes.append(index)
        for index in indexes:
            if self.MessageKeywordsQ[index] == '!!@@##':
                youtubeResult = status.get_youtube_result(userInput)
            else:
                youtubeResult = status.get_youtube_result(self.MessageKeywordsQ[index])
            columnsList = []
            for idx, tmp in enumerate(youtubeResult):
                columnsList.append(CarouselColumn(
                        thumbnail_image_url=tmp[2],
                        title=f'{self.MessageKeywords[index]} 推薦影片 {idx+1}',
                        text=tmp[0].replace('[無廣告版]','').replace('「無廣告版」','')[:60],
                        actions=[
                            URITemplateAction(
                                label='點我 開始撥放',
                                uri=tmp[1]
                            )
                        ]
                    ))
            carousel_template = CarouselTemplate(
                columns=columnsList
            )
            message.append(TemplateSendMessage(alt_text='選擇YouTube影片', template=carousel_template))               
        return message
        
        
# domain root
@app.route("/")
def home():
    return "Hello, World!"


@app.route("/webhook", methods=["POST"])
def callback():
    # get X-Line-Signature header value
    signature = request.headers["X-Line-Signature"]
    # get request body as text
    body = request.get_data(as_text=True)
    app.logger.info("Request body: " + body)
    # handle webhook body
    try:
        line_handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return "OK"



@line_handler.add(MessageEvent, message=AudioMessage)
def handle_AudioMessage(event):
    if event.message.type != "audio":
        return
    user_id = event.source.user_id
    if not os.path.exists(f'static/{user_id}/config.ini'):
        status.set_config_to_ini(user_id)
        
    status.get_config_from_ini(user_id)
    
    try:
        audio_input_path = status.get_user_audio_input_path(
            user_id=user_id,
            user_send_audio=line_bot_api.get_message_content(event.message.id),
        )
        audio_output_path = status.get_user_audio_output_path(user_id=user_id)
        print(f"get audio: {audio_input_path}")

        text = status.get_text_from_audio_path(
            user_id=user_id, audio_path=audio_input_path
        )
        print(f"get text: {text}")
        reply_text = Q2assistant(event, text)
        #if not status.check_record_is_good(text=text):
        #    message = [TextSendMessage(text=text)]
        #    line_bot_api.reply_message(event.reply_token, message)
        #    return
        #reply_text = status.get_reply_text(user_id=status.get_lineID_to_lineDisplayName(user_id), query=text)
        audio_tts_output_path = status.get_audio_tts_output_path(
            user_id=user_id, reply_text=reply_text
        )
        print(f"get reply_text: {reply_text}")
        if os.path.exists(audio_tts_output_path):
            message = [
                TextSendMessage(text=text2result(str(reply_text))),  # 傳文字
                AudioSendMessage(
                    original_content_url=ngrok_url + "/" + audio_tts_output_path,
                    duration=330 * len(reply_text),
                ),
            ]
            line_bot_api.reply_message(event.reply_token, message)
        else:
            print("File not found.")
    except Exception as e:
        print(e)
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="error"))
    return "OK"

def Q2assistant(event, Qtext = ''):
    if event.message.type != "audio":
        Qtext = event.message.text
    else:
        Qtext = Qtext
    
    
    max_context = 2048
    max_generations = 128
    
    if status.onlineSearch == 'True' or status.onlineSearch == True:
        Qtext = Qtext + '\n我的位置在台灣使用繁體中文，不允許有其他位置的資訊，只限使用中文回答\n'
        max_context = 4096
        max_generations = 1300
    user_id = event.source.user_id
    print(f"get text: {Qtext}")
    if '小助手' in Qtext:
        prompt = Qtext.replace('小助手','').replace('助手','')
        status.get_config_from_ini(user_id)
        try:
            url = configSys.get('GLM', 'QAurl')#"https://linebot.iservmeta.org:30300/getQA"

            payload = {'id': status.KM_id,
                'question': prompt,
                'user_id': user_id,
                'temperature': '0',
                'top_p': '0.1',
                'n_choices': '1',
                'max_context': max_context,
                'max_generations': max_generations,
                'presence_penalty': '-2',
                'frequency_penalty': '-2',
                'logit_bias': '',
                'systemPrompt': configSys.get('GLM', 'systemPrompt'),
                'userPrompt': configSys.get('GLM', 'userPrompt'),
                'onlineSearch': status.onlineSearch,
                'streamOut': status.streamOut                
            }
            print(f'KM param : {payload}')
            files=[

            ]
            headers = {}

            response = requests.request("POST", url, headers=headers, data=payload, files=files)

            #print(response.text)  
 
            reply_summary = converter.convert(response.json()['summary'])
            
            text_ref = converter.convert('、'.join( eval(response.json()['ref'])))
            
            # 建立 CarouselTemplate 中的 CarouselColumn
            columns = []
            md5_hash = hashlib.md5()            
            
            try:
                for value in eval(response.json()["ref"]):
                    filename = value
                    md5_hash.update(filename.encode("utf-8"))
                    pathName = md5_hash.hexdigest()
                    shutil.copy(f"static/{user_id}/{pathName}/{filename}", f"static/{user_id}/{pathName}/{pathName}.pdf")
                    file_path = f'static/{user_id}/{pathName}/' + fileName.split('.')[0] + '.txt'

                    try:
                        with open(file_path, "r", encoding = 'utf=8') as file:
                            content = file.read()
                            # 將內容轉換成字串（如果是文字檔案的話）
                            #content_str = content.decode("utf-8")  # 假設使用 UTF-8 編碼
                    except:
                        content_str = "尚無資訊"
    
                    columns.append(CarouselColumn(
                        thumbnail_image_url=ngrok_url + "/" + convert_pdf_to_image(f"static/{user_id}/{pathName}/{filename}", f"static/{user_id}/{pathName}/{pathName}.png"),  # 可以是任意的縮略圖 URL
                        title=filename,
                        text = f'{content[:50]} ...',
                        actions=[
                            URITemplateAction(
                                label="點擊下載",
                                uri=ngrok_url + "/" + f"static/{user_id}/{pathName}.pdf"
                            )
                        ]
                    ))

                # 建立 CarouselTemplate
                carousel_template = CarouselTemplate(columns=columns)
                message.append(TemplateSendMessage(alt_text="參考資料", template=carousel_template))
            except Exception as e:
                print(e)
                
            reply_text = status.get_lineID_to_lineDisplayName(user_id) + ' ' +converter.convert(response.json()['answer']) + '\n\n參考文件：\n' + text_ref +  '\n\n' + reply_summary    
      
        except Exception as e:
            print(e)
            line_bot_api.reply_message(event.reply_token, TextMessage(text='無知識庫，請上傳知識庫檔案'))
            return
        
        reply_text = reply_text.replace('計算機','電腦').replace('軟件','軟體').replace('信息','資訊').replace('ChatGLM2-6B','小助手').replace('網絡','網路').replace('服務器','伺服器').replace('掛機','連線').replace('數碼','數位').replace('硬件','硬體').replace('視頻','視訊').replace('屏幕','螢幕').replace('U盤','隨身碟').replace('數據庫','資料庫')

    else:
        try:
            url = configSys.get('GLM', 'CHATurl')#"https://linebot.iservmeta.org:30300/getGLM"

            payload = {'question': Qtext, 'onlineSearch': status.onlineSearch, 'streamOut': status.streamOut}
            files=[

            ]
            headers = {}
            print(f'KM param : {payload}')
            response = requests.request("POST", url, headers=headers, data=payload, files=files)
        except Exception as e:
            print(e)
            line_bot_api.reply_message(event.reply_token, TextMessage(text='我累了，稍候再回覆!'))
            return
        try:
            reply_text = status.get_lineID_to_lineDisplayName(user_id) + ' ' + converter.convert(response.json()['answer'])
        except:
            reply_text = f'😃夥伴😃\n' + ' ' + converter.convert(response.json()['answer'])
        print(reply_text)
    return text2result(reply_text)
    
@line_handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    #global working_status
    global working_list
    if event.message.type != "text":
        return
    user_id = event.source.user_id
    
    if not os.path.exists(f'static/{user_id}/config.ini'):
        status.set_config_to_ini(user_id)
    
    if event.message.text == "說話":
        #working_status = True
        if user_id in working_list:
            working_list.remove(user_id)
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text = status.get_lineID_to_lineDisplayName(user_id) + "我可以說話囉，歡迎來跟我互動 ^_^ "))
        return

    if event.message.text == "閉嘴":
        #working_status = False
        if '😃夥伴😃' in status.get_lineID_to_lineDisplayName(user_id):
            TextSendMessage(text="您不是我的好友，無法叫我閉嘴!!"))
            return
        working_list.append(user_id)
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text = status.get_lineID_to_lineDisplayName(user_id) + "好的，我乖乖閉嘴 > <，如果想要我繼續說話，請跟我說 「說話」 > <"))
        return
        
    if user_id in working_list:    
        return
    
    #刪除 id的知識庫
    if '_deleteKM_' in event.message.text:
        deleteKM_id = event.message.text.replace('_deleteKM_: ','')
        url = configSys.get('GLM', 'DELEurl')

        payload = {'user_id': user_id, 'id': deleteKM_id}
        files=[

        ]
        headers = {}
        response = requests.request("POST", url, headers=headers, data=payload, files=files)
 
        if response.json()['status'] == 'OK':
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f'知識庫 {deleteKM_id} 刪除成功\n可使用_fileList_進行確認'))
        else:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f'知識庫 {deleteKM_id} 刪除失敗\n{response.json()["status"]}'))
        return
        
    #使用 id的知識庫    
    if '_useKM_' in event.message.text:
        status.KM_id = event.message.text.replace('_useKM_: ','')
        app.logger.info(f'設定知識庫 {status.KM_id}')
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f'完成知識庫 {status.KM_id} 設定'))
        return

    #列出 所有知識庫
    if '_fileList_' in event.message.text:
        if event.message.text == '_fileList_':
            url = configSys.get('GLM', 'INFOurl')# "https://linebot.iservmeta.org:30300/getPDFinfo"

            payload = {'user_id': user_id}
            files=[

            ]
            headers = {}
            response = requests.request("POST", url, headers=headers, data=payload, files=files)
     
            fileResult = response.json()['answer']
            app.logger.info(f'所有知識庫：{fileResult}')
            if response.json()['status'] == 'Error':
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text=response.json()['detail'] + '，請上傳知識庫檔案'))
                return
            if len(response.json()['answer'])<=0:
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text= '無知識庫' + '，請上傳知識庫檔案'))
                return            

            message = []

            md5_hash = hashlib.md5()
            


            templates = []
            for i in range(0, len(response.json()["answer"].items()), 9):
                # 建立 CarouselTemplate 中的 CarouselColumn
                columns = []
                #新增 all的選項
                columns.append(CarouselColumn(
                    thumbnail_image_url = configSys.get('line', 'thumbnail_image_url'),#"https://ez2tv.myds.me/bobi.png",  # 可以是任意的縮略圖 URL
                    title='使用全部知識庫',
                    text="使用曾經上傳過的檔案，作為知識庫",
                    actions=[
                        MessageTemplateAction(
                            label=f'使用全部知識庫',
                            text=f'_useKM_: all',
                        ),                        
                        MessageTemplateAction(
                            label=' ',
                            text=' ',
                        ),
                        URITemplateAction(
                            label=f" ",
                            uri = configSys.get('line', 'thumbnail_image_url')#"https://ez2tv.myds.me/bobi.png"
                        )
                    ]
                ))                
                
                chunk = list(response.json()["answer"].items())[i:i + 9]
                for key, value in chunk:#response.json()["answer"].items():
                    
                    document_id = key
                    filename = value[0]
                    md5_hash.update(filename.encode("utf-8"))
                    pathName = md5_hash.hexdigest()
                    shutil.copy(f"static/{user_id}/{pathName}/{filename}", f"static/{user_id}/{pathName}/{pathName}.pdf")
                    file_path = f'static/{user_id}/{pathName}/' + filename.split('.')[0] + '.txt'
                    
                    try:
                        with open(file_path, "r", encoding = 'utf-8') as file:
                            content = file.read()
                            # 將內容轉換成字串（如果是文字檔案的話）
                            #content_str = content.decode("utf-8")  # 假設使用 UTF-8 編碼
                    except Exception as e:
                        print(e)
                        content_str = f"尚無資訊 {str(e)}"
                    try:    
                        columns.append(CarouselColumn(
                            thumbnail_image_url=ngrok_url + "/" + convert_pdf_to_image(f"static/{user_id}/{pathName}/{filename}", f"static/{user_id}/{pathName}/{pathName}.png"),  # 可以是任意的縮略圖 URL
                            title=filename,
                            text = f'{content[:50]} ...',
                            actions=[
                                MessageTemplateAction(
                                    label=f'使用此知識庫',
                                    text=f'_useKM_: {key}',
                                ),
                                MessageTemplateAction(
                                    label=f'刪除此知識庫',
                                    text=f'_deleteKM_: {key}',
                                ),
                                URITemplateAction(
                                    label=f"下載此知識庫",
                                    uri=ngrok_url + "/" + f"static/{user_id}/{pathName}.pdf"
                                )
                            ]
                        ))
                    except:
                        pass
                # 建立 CarouselTemplate
                carousel_template = CarouselTemplate(columns=columns)
                templates.append(TemplateSendMessage(alt_text="知識庫列表", template=carousel_template))
            


            # 將 CarouselTemplate 送出給 Line Bot API
            line_bot_api.reply_message(
                event.reply_token,
                templates[-5:]) 
            return
    
    
    if '_is3D_' in event.message.text:
        if status._is3D_ == 'True':
            status._is3D_ = 'False'
        else:
            status._is3D_ = 'True'
            
        status.set_config_to_ini(user_id)
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"3D Figure {status._is3D_}"))
        return

    if '_newKM_' in event.message.text:
        if status.onlineSearch == 'True':
            status.onlineSearch = 'False'
        else:
            status.onlineSearch = 'True'
            
        status.set_config_to_ini(user_id)
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"newKM: {status.onlineSearch}"))
        return        
    
    if '_gender_' in event.message.text:
        if status._gender_ == '0':
            status._gender_ = '1'
        else:
            status._gender_ = '1'
            
        status.set_config_to_ini(user_id)
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"Figure gender {status._gender_}"))
        return
        
    if 'txt2image' in event.message.text:
        print(event.message.text)
        status.outputPathPNG = status.get_SD_pic(user_id, event.message.text)
        message = [
            ImageSendMessage(
            original_content_url=ngrok_url+ f"/static/{user_id}/{status.outputPathPNG}",
            preview_image_url=ngrok_url+ f"/static/{user_id}/{status.outputPathPNG}"
        )]
        #status._3Dpic = f"static/{user_id}/{status.outputPathPNG}"
        status.set_config_to_ini(user_id)
        line_bot_api.reply_message(event.reply_token, message)
        return
        
    message = []
    message.extend(status.chkMessageKeywords(user_id, event.message.text))

   
##
    reply_text = Q2assistant(event, '')
            
    print(f"get reply_text: {reply_text}")
    audio_tts_output_path = status.get_audio_tts_output_path(
        user_id=user_id, reply_text=reply_text
    )
        
    if os.path.exists(audio_tts_output_path):
        try:  
            print(status._is3D_ , len(reply_text))
            if len(reply_text) <= 150 and status._is3D_ == 'True':
                status.TTS_P_GENDER = int(status._gender_)
                audio_tts_output_path = status.get_audio_tts_output_path(
                    user_id=user_id, reply_text=reply_text
                )
                try:
                    _3Dresult = status.get3Dvideo(audio_tts_output_path, status._3Dpic)
                except:
                    status._3Dpic = 'static/003.jpg'
                    status.set_config_to_ini(user_id)
                    _3Dresult = status.get3Dvideo(audio_tts_output_path, status._3Dpic)
                    
                message.append(VideoSendMessage(
                        original_content_url= ngrok_url + '/' + _3Dresult[0],
                        preview_image_url=ngrok_url + '/' + _3Dresult[1])         
                )                           
            else:
                message.append(AudioSendMessage(
                    original_content_url=ngrok_url + "/" + audio_tts_output_path,
                    duration=110 * len(reply_text),
                ))
        except Exception as e:
            print(e)
            message.append(AudioSendMessage(
                original_content_url=ngrok_url + "/" + audio_tts_output_path,
                duration=110 * len(reply_text),
            ))
        try:
            if '颱風動態' in event.message.text or '颱風' in event.message.text:
                #windy_link = 'https://www.windy.com/?25.050,121.532,5'
                #carousel_template = ImageCarouselTemplate(columns=[
                #    ImageCarouselColumn(image_url='https://embed.windy.com/embed2.html?lat=25.050&lon=121.532&detailLat=25.050&detailLon=121.532&width=650&height=450&zoom=5&level=surface&overlay=wind&product=ecmwf&menu=&message=&marker=&calendar=now&pressure=&type=map&location=coordinates&detail=&metricWind=default&metricTemp=default&radarRange=-1', action=URIAction(uri=windy_link))
                #])
                #message.append(TemplateSendMessage(alt_text='Windy Animation', template=carousel_template))

                    
            
            
                reply_text = reply_text + '\n\nhttps://www.windy.com/?25.050,121.532,5'
        except Exception as e:
            print(e)
            pass    
        message.append(TextSendMessage(text=text2result(str(reply_text))))

        line_bot_api.reply_message(event.reply_token, message)
        return
    else:
        print("File not found.")
        message.append(TextMessage(text=text2result(reply_text)))
        line_bot_api.reply_message(event.reply_token, message)
        #line_bot_api.reply_message(event.reply_token, TextMessage(text=reply_text))
        return


@line_handler.add(MessageEvent, message=FileMessage)
def handle_file_message(event):
    if event.message.type != "file":
        return
    user_id = event.source.user_id
    if not os.path.exists(f'static/{user_id}/config.ini'):
        status.set_config_to_ini(user_id)
    
    status.get_config_from_ini(user_id)
    
    message_content = line_bot_api.get_message_content(event.message.id)
    fileName = event.message.file_name
    md5_hash = hashlib.md5()  
    md5_hash.update(fileName.encode("utf-8"))
    pathName = md5_hash.hexdigest()
    
    if not os.path.exists(f'static/{user_id}/{pathName}/'):
        # 如果路径不存在，使用os.makedirs创建它
        os.makedirs(f'static/{user_id}/{pathName}/')
    #存檔
    with open(f'static/{user_id}/{pathName}/' + fileName, "wb") as f:
        for chunk in message_content.iter_content():
            f.write(chunk)
    
    url = configSys.get('GLM', 'UPLDurl') #"https://linebot.iservmeta.org:30300/uploadPDF"

    payload = {'user_id': user_id}
    
    mime_type, _ = mimetypes.guess_type(f'static/{user_id}/{pathName}/' + fileName)
    if mime_type:
        files = [
            ('file', (fileName, open(f'static/{user_id}/{pathName}/' + fileName, 'rb'), mime_type))
        ]
        extract_images_from_pdf(f'static/{user_id}/{pathName}/' + fileName, f'static/{user_id}/{pathName}/123.png')
    else:
        files=[
            ('file', (fileName, open(f'static/{user_id}/{pathName}/' + fileName, 'rb'), 'application/pdf'))
        ]
        extract_images_from_pdf(f'static/{user_id}/{pathName}/' + fileName, f'static/{user_id}/{pathName}/123.png')
    headers = {}
    response = requests.request("POST", url, headers=headers, data=payload, files=files)

    #print(response.text)    
    
    reply_text = response.text + '\n\n上傳成功，您可以使用 _fileList_ 進行查詢曾經上傳過的檔案'
    
    #-----------------------
    
    try:
        url = configSys.get('GLM', 'QAurl')
        payload = {'id': response.json()['uploads'][0]['id'],
            'question': configSys.get('GLM', 'summaryPrompt'),
            'user_id': user_id,
            'temperature': '0',
            'top_p': '0.7',
            'n_choices': '10',
            'max_context': '2048',
            'max_generations': '1024',
            'presence_penalty': '-1.8',
            'frequency_penalty': '0.2',
            'logit_bias': '',
            'systemPrompt': configSys.get('GLM', 'systemPrompt'),
            'userPrompt': configSys.get('GLM', 'userPrompt'),
            'onlineSearch': status.onlineSearch,
            'streamOut': status.onlineSearch
        }
        app.logger.info(f'KM param : {payload}')
        files=[

        ]
        headers = {}
        response = requests.request("POST", url, headers=headers, data=payload, files=files)
        app.logger.info(f'response status: {response.status_code}')
        
        
        if response.status_code == 500:
            try:
                url = configSys.get('GLM', 'QAurl')
                payload = {'id': response.json()['uploads'][0]['id'],
                    'question': configSys.get('GLM', 'summaryPrompt'),
                    'user_id': user_id,
                    'temperature': '0',
                    'top_p': '0.7',
                    'n_choices': '10',
                    'max_context': '2048',
                    'max_generations': '1024',
                    'presence_penalty': '-1.8',
                    'frequency_penalty': '0.2',
                    'logit_bias': '',
                    'systemPrompt': configSys.get('GLM', 'systemPrompt'),
                    'userPrompt': configSys.get('GLM', 'userPrompt'),
                    'twoColumn': True,
                }
                app.logger.info(f'KM param : {payload}')
                files=[

                ]
                headers = {}
                response = requests.request("POST", url, headers=headers, data=payload, files=files)          
            except Exception as e:
                app.logger.error(f'error {str(e)}')
    except:
        payload = {'id': response.json()['uploads'][0]['id'],
            'question': configSys.get('GLM', 'summaryPrompt'),
            'user_id': user_id,
            'temperature': '0',
            'top_p': '0.7',
            'n_choices': '10',
            'max_context': '2048',
            'max_generations': '1024',
            'presence_penalty': '-1.8',
            'frequency_penalty': '0.2',
            'logit_bias': '',
            'systemPrompt': configSys.get('GLM', 'systemPrompt'),
            'userPrompt': configSys.get('GLM', 'userPrompt'),
            'twoColumn': True,
        }
        app.logger.info(f'KM param : {payload}')
        files=[

        ]
        headers = {}

        response = requests.request("POST", url, headers=headers, data=payload, files=files)    
    
    
    app.logger.info(response.text)  

    reply_summary = converter.convert(response.json()['answer'])
    with open(f'static/{user_id}/' + fileName.split('.')[0] + '.txt', "w", encoding = 'utf-8') as file:
        file.write(reply_summary) 
    
    
    message = [
        TextSendMessage(text=text2result(reply_text+f'\n\n摘要：{str(reply_summary)}'))
    ]
    line_bot_api.reply_message(event.reply_token, message)
    return

@line_handler.add(MessageEvent, message=ImageMessage)
def handle_ImageMessage(event):
    user_id = event.source.user_id
    if not os.path.exists(f'static/{user_id}/config.ini'):
        status.set_config_to_ini(user_id)
    
    status.get_config_from_ini(user_id)
    
    if event.message.type == "image":
        outputPath= str(int(time.time()))
        outputPathPNG = outputPath + '.png'
        outputPathMP3 = outputPath + '.mp3'
        SendImage = line_bot_api.get_message_content(event.message.id)
        path = f'static/{user_id}/' + outputPathPNG
        with open(path, 'wb') as fd:
            for chenk in SendImage.iter_content():
                fd.write(chenk)
        try:
            client = Client(status.IMG2TXTurl)
            client = Client(configSys.get('SD', 'IMG2TXTurl'))# "https://openflamingo-openflamingo.hf.space/")
            result = client.predict(
                            path,	# str (filepath or URL to image) in 'parameter_79' Image component
                            True,	# bool  in 'I have read and agree to the terms and conditions' Checkbox component
                            "https://ez2tv.myds.me/274287.jpg",	# str (filepath or URL to image) in 'parameter_71' Image component
                            "This is a good morning picture. In the picture, there is a smiling cat greeting everyone, and the content of the text is to say hello to everyone in good faith.",	# str  in 'Demonstration sample 1' Textbox component
                            "https://ez2tv.myds.me/S__45981936.jpg",	# str (filepath or URL to image) in 'parameter_75' Image component
                            "This is a picture of blessings. There are two children in the picture and they are smiling brightly. The content of the text is to wish everyone.",	# str  in 'Demonstration sample 2' Textbox component
                            fn_index=4
            )
 
            reply_text = converter.convert(status.get_txtTransT(result.replace('Output: ','')))
            print(reply_text)
            
            url = configSys.get('GLM', 'CHATurl')#"https://linebot.iservmeta.org:30300/getGLM"

            payload = {'question': f'請以「{reply_text}」為主題，寫一首五言絕句\n'}
            files=[

            ]
            headers = {}

            response = requests.request("POST", url, headers=headers, data=payload, files=files)

            reply_text = converter.convert(response.json()['answer'])
            message = [
                TextSendMessage( #傳文字
                text = status.get_lineID_to_lineDisplayName(user_id) + '這圖意謂...\n\n' + str(reply_text)+'\n\n'+reply_text
                ),
                #AudioSendMessage(
                #original_content_url = ngrok_url + '/' + audio_tts_output_path,
                #duration=330*len(reply_text))
                ]
            #message.extend(status.chkMessageKeywords(user_id, reply_text))   
            line_bot_api.reply_message(event.reply_token, message)   
            return        
        except:       
            try:
                #OCR
                TTSgender = 0
                OCR_start_time_ = time.time()
                img = Image.open(path)
                OCRtext = pytesseract.image_to_string(img, lang='chi_tra+eng')
                if status.contains_chinese_english_digits(OCRtext):
                    print(OCRtext)
                else:
                    OCRtext = ''
                print(f'處理OCR中 ....')
                if OCRtext != '':
                    OCRtext = OCRtext.replace("'",'"').replace('‘','').replace('’','').replace("′","")
                    print(f'辨識出文字 {OCRtext}')
                    OCR_end_time_ = time.time()
                    
                    reply_text = status.get_reply_text(user_id=user_id, query=OCRtext)
                    print(f"get reply_text: {reply_text}")                
                    line_bot_api.reply_message(event.reply_token, TextMessage(text=reply_text))        
                    return
                    
                    try:   
                        print(status._is3D_)
                        if len(reply_text) <= 150 and status._is3D_ == 'True':   
                            status.TTS_P_GENDER = int(status._gender_)
                            audio_tts_output_path = status.get_audio_tts_output_path(
                                user_id=user_id, reply_text=reply_text
                            )
                            try:
                                _3Dresult = status.get3Dvideo(audio_tts_output_path, status._3Dpic)
                            except:
                                status._3Dpic = 'static/003.jpg'
                                status.set_config_to_ini(user_id)
                                _3Dresult = status.get3Dvideo(audio_tts_output_path, status._3Dpic)
                            if os.path.exists(audio_tts_output_path):
                                message = [
                                    TextSendMessage( #傳文字
                                    text = str(reply_text)
                                    ),
                                    VideoSendMessage(
                                        original_content_url= ngrok_url + '/' + _3Dresult[0],
                                        preview_image_url=ngrok_url + '/' + _3Dresult[1])
                                    ]
                                message.extend(status.chkMessageKeywords(user_id, reply_text))    
                                line_bot_api.reply_message(event.reply_token, message)
                                return
                            else:
                                print('File not found.') 
                                                        
                        else:
                            status.TTS_P_GENDER = 1
                            audio_tts_output_path = status.get_audio_tts_output_path(
                                user_id=user_id, reply_text=reply_text
                            )
                            if os.path.exists(audio_tts_output_path):
                                message = [
                                    TextSendMessage( #傳文字
                                    text = str(reply_text)
                                    ),
                                    AudioSendMessage(
                                    original_content_url = ngrok_url + '/' + audio_tts_output_path,
                                    duration=330*len(reply_text))]
                                message.extend(status.chkMessageKeywords(user_id, reply_text))   
                                line_bot_api.reply_message(event.reply_token, message)   
                                return
                            else:
                                print('File not found.')           
                        
                        
                        
                        line_bot_api.reply_message(event.reply_token, TextMessage(text=reply_text))        
                        return
                    except Exception as e:
                        print(e)
                        return
                        
                        
                        line_bot_api.reply_message(event.reply_token,TextSendMessage(text=reply_text))
                        return   
                else:
                    #status._3Dpic = path
                    status.set_config_to_ini(user_id)
                    # create API client
                    api = webuiapi.WebUIApi()
                    # create API client with custom host, port
                    api = webuiapi.WebUIApi(host='180.218.16.187', port=30302)
                    api.set_auth('username', 'password')
                    
                    unit1 = webuiapi.ControlNetUnit(input_image=img, module='canny', model='control_sd15_canny [fef5e48e]')
                    unit2 = webuiapi.ControlNetUnit(input_image=img, module='depth', model='control_sd15_depth [fef5e48e]', weight=0.5)
                    unit3 = webuiapi.ControlNetUnit(input_image=img, module='shuffle', model='control_v11e_sd15_shuffle [526bfdae]', weight=0.5)

                    imgg = Image.open(path)
                    wwidth, hheight = imgg.size

                    wwidth, hheight = int(wwidth*1.5), int(hheight*1.5)
                    myMax = 800
                    if hheight > myMax:
                        ratio = hheight / myMax
                        wwidth = int(wwidth /ratio)
                        hheight = int(hheight / ratio)
                    if wwidth > myMax:
                        ratio = wwidth / myMax
                        wwidth = int(wwidth /ratio)
                        hheight = int(hheight / ratio)
                    print(f'width: {wwidth}\nheight: {hheight}')
                    
                    r2 = api.img2img(prompt = 'Morning,Pretty girl,Sun,The beach, high detailed,8K,HDR,(best quality:1.4),(masterpiece:1.4),digital painting of Vallaria',
                                images=[img], 
                                width=wwidth,
                                height=hheight,
                                controlnet_units=[unit1, unit2, unit3],
                                sampler_name="DPM++ SDE Karras",
                                cfg_scale=9,
                                seed = -1,
                                steps = 48,
                                restore_faces = True,
                                denoising_strength = 0.36,
                               )
                            
                    picSavePath = f'static/{user_id}/{outputPathPNG}'
                    r2.image.save(picSavePath)
                    
                    message = [
                        ImageSendMessage(
                        original_content_url=ngrok_url + '/' + picSavePath,
                        preview_image_url=ngrok_url + '/' + picSavePath
                    )]
                    
                    status.set_config_to_ini(user_id)
                    line_bot_api.reply_message(event.reply_token, message)
                    #line_bot_api.reply_message(event.reply_token,TextSendMessage(text='收到圖了'))
                    return
            except Exception as e:
                print(f'error : {e}')


    
if __name__ == "__main__":
    ngrok_url = f"https://linebot.iservmeta.org:{serverPort}"
    ssl_cert_file = 'ssl/certificate.crt'
    ssl_ca_bundle_file = 'ssl/ca_bundle.crt'
    ssl_key_file = 'ssl/private.key'
    
    context = ssl.SSLContext(ssl.PROTOCOL_TLSv1_2)
    context.load_cert_chain(ssl_cert_file, ssl_key_file)
    context.load_verify_locations(ssl_ca_bundle_file)
    status = STATUS()
    app.run(
        host="0.0.0.0", port=serverPort, ssl_context=context
    )
