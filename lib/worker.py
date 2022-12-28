#!/usr/bin/python3

import time
import requests

from lib.config import *
import lib.telegram as telegram

import io
import openai
from PIL import Image

def process_request(service, chat_id, user, message, botName, userRealName, chat_type, message_id, file_id=False):
    now = int(time.time())
    if file_id:
        print("detected inbound photo")
        if message.startswith(botName) or message.startswith('/dream') or chat_type == 'private':
            message = message.replace(botName, '').replace('/dream', '').strip()
            if len(message):
                message = 'variation of ' + message
            print("downloading from telegram")
            image_url = telegram.getFileURL(file_id)
            cropped, image_data = crop_square(image_url)
            print("Sending image to OpenAI")
            success, image_url = image_variation(image_data)
            if success:
                print("Sending result to Telegram")
                if cropped:
                    message = message + "\nNote: I centre-cropped your non-square image before sending it to OpenAI"
                telegram.sendMediaGroup(chat_id, image_url, message)
                if config_archive:
                    if isinstance(image_url, list):
                        version=1
                        for item in image_url:
                            filename = config_archive_dir + '/variation_' + str(now) + '_' + str(version) + '.png'
                            image_bytesio = download_file(item)
                            bytesio_to_file(image_bytesio, filename)
                            version=version+1
                    else:
                        filename = config_archive_dir + '/image_variation_' + str(now) + '.png'
                        image_bytesio = download_file(image_url)
                        bytesio_to_file(image_bytesio, filename)
            elif image_url:
                message = image_url
                print("Sending error to Telegram")
                telegram.sendMessage(chat_id, message, message_id)

    else:
        if message.startswith(botName) or message.startswith('/dream') or chat_type == 'private':
            message = message.replace(botName, '').replace('/dream', '').strip()
            if len(message.split()) > 2:
                print("Sending prompt to OpenAI")
                success, image_url = generate_image(message)
                if success:
                    print("Sending result to Telegram")
                    telegram.sendPhoto(chat_id, image_url, message)
                    if config_archive:
                        image_bytesio = download_file(image_url)
                        filename = config_archive_dir + '/image_' + str(now) + '.png'
                        bytesio_to_file(image_bytesio, filename)
                elif image_url:
                    message = image_url
                    print("Sending error to Telegram")
                    telegram.sendMessage(chat_id, message, message_id)
            else:
                print("Prompt was too short - ignoring")

def generate_image(message):
    if 'config_openai_organization' in globals():
        openai.organization = config_openai_organization
    openai.api_key = config_openai_api_key
    if debug:
        config_size="256x256"
    else:
        config_size="1024x1024"
    try:
        response = openai.Image.create(
        prompt=message,
        n=1,
        size=config_size
        )
        image_url = response['data'][0]['url']
        print(image_url)
    except openai.error.OpenAIError as e:
        print(e.http_status, e.error)
        return False, e.error['message']
    return True, image_url

def image_variation(image_data):
    if 'config_openai_organization' in globals():
        openai.organization = config_openai_organization
    openai.api_key = config_openai_api_key
    if debug:
        config_size="256x256"
    else:
        config_size="1024x1024"
    try:
        response = openai.Image.create_variation(
          image=image_data,
          n=4,
          size=config_size
        )
        url_list = []
        for item in response['data']:
            url_list.append(item['url'])
        #print(response)
    except openai.error.OpenAIError as e:
        print(e.http_status, e.error)
        return False, e.error
    return True, url_list

def download_file(image_url):
    r = requests.get(image_url)
    if r.status_code == 200:
        print(r.status_code, "downloaded file for archiving")
        image_data = io.BytesIO(r.content)
    else:
        print(r.status_code, "while downloading file for archiving")
    return image_data

def bytesio_to_file(image_bytesio, filename):
    with open(filename, "wb") as f:
        f.write(image_bytesio.getbuffer())
    print("Saved", filename)

def crop_square(image_url):
    cropped=False
    print("Opening image")
    im = Image.open(urllib.request.urlopen(image_url))
    width, height = im.size
    if width != height:
        print("Cropping to center while preserving shortest axis")
        crop = min(width, height)
        left = int(crop/2-crop/2)
        upper = int(crop/2-crop/2)
        right = left + crop
        lower = upper + crop
        im_cropped = im.crop((left, upper, right, lower))
        print("image cropped from " + str(im.size) + " to " + str(im_cropped.size))
        im = im_cropped
        cropped=True
    byte_stream = io.BytesIO()
    print("Saving as PNG")
    im.save(byte_stream, format='PNG')
    cropped_bytesio = byte_stream.getvalue()
    return cropped, cropped_bytesio
