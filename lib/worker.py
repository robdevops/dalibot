#!/usr/bin/python3

import io
import openai
import requests
import time
from PIL import Image
from sys import stderr
import threading

from lib.config import *
import lib.telegram as telegram

def process_request(service, chat_id, user, message, botName, userRealName, chat_type, message_id, file_id=False):
    now = int(time.time())
    if file_id:
        print("Detected inbound photo")
        if message.startswith(botName) or message.startswith('/dream') or chat_type == 'private':
            message = message.replace(botName, '').replace('/dream', '').strip()
            if len(message):
                message = 'Variation of ' + message
            print("Downloading from telegram")
            image_url = telegram.getFileURL(file_id)
            success, cropped, image_data = prepare_image(image_url)
            if not success:
                message = image_data
                error_to_telegram(chat_id, message, message_id)
                return
            print("Sending image to OpenAI")
            success, image_url = image_variation(image_data)
            if success:
                print("Sending result to Telegram")
                if cropped:
                    message = message + "\nNote: I centre-cropped your non-square image before sending it to OpenAI"
                telegram.sendMediaGroup(chat_id, image_url, message)
                if config_archive:
                    if isinstance(image_url, list):
                        for idx, url in enumerate(image_url):
                            filename = config_archive_dir + '/variation_' + str(now) + '_' + str(idx+1) + '.png'
                            threading.Thread(target=url_to_file(url, filename)).start()
                        print("end of batch")
                    else:
                        filename = config_archive_dir + '/image_variation_' + str(now) + '.png'
                        image_bytesio = download_file(image_url)
                        bytesio_to_file(image_bytesio, filename)
            elif len(image_url):
                message = image_url
                error_to_telegram(chat_id, message, message_id)

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
                elif len(image_url):
                    message = image_url
                    error_to_telegram(chat_id, message, message_id)
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
    except openai.error.OpenAIError as e:
        print(e.http_status, e.error, file=stderr)
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
    except openai.error.OpenAIError as e:
        print(e.http_status, e.error, file=stderr)
        return False, e.error['message']
    return True, url_list

def download_file(image_url):
    r = requests.get(image_url, timeout=config_http_timeout)
    if r.status_code == 200:
        print(r.status_code, "downloaded file for archiving")
        image_data = io.BytesIO(r.content)
    else:
        print(r.status_code, "while downloading file for archiving")
    return image_data

def bytesio_to_file(image_bytesio, filename):
    try:
        with open(filename, "wb") as f:
            f.write(image_bytesio.getbuffer())
    except Exception as e:
        print(e, file=stderr)
    else:
        print("Saved", filename)

def prepare_image(image_url):
    print("Opening image")
    try:
        im = Image.open(requests.get(image_url, stream=True, timeout=config_http_timeout).raw)
    except Exception as e:
        message = "Error opening image: " + str(e)
        print(message, file=stderr)
        return False, False, message
    width, height = im.size
    cropped=False
    if width != height:
        print("Cropping to center while preserving shortest edge")
        crop = min(width, height)
        left = int(crop/2-crop/2)
        upper = int(crop/2-crop/2)
        right = left + crop
        lower = upper + crop
        im_cropped = im.crop((left, upper, right, lower))
        print("Cropped from " + str(im.size) + " to " + str(im_cropped.size))
        im = im_backup = im_cropped
        cropped=True
    print("Saving as PNG")
    with io.BytesIO() as byte_stream:
        im.save(byte_stream, format='PNG')
        image_bytesio = byte_stream.getvalue()
    while len(image_bytesio) > config_max_upload_size:
        filesize = len(image_bytesio)
        size_deviation = filesize / config_max_upload_size
        print("Resizing from {:,} px; {:,} bytes; factor: {:.3f}".format(im.size[0], filesize, size_deviation))
        new_width = new_height = im.size[0] / size_deviation**0.55
        # resize from original to preserve quality
        im = im_backup.resize((int(new_width), int(new_height)))
        with io.BytesIO() as byte_stream:
            im.save(byte_stream, format='PNG')
            image_bytesio = byte_stream.getvalue()
    print("Final size:", str(im.size), "px;", f"{len(image_bytesio):,} bytes")
    return True, cropped, image_bytesio

def url_to_file(url, filename):
    image_bytesio = download_file(url)
    bytesio_to_file(image_bytesio, filename)

def error_to_telegram(chat_id, message, message_id):
    print("Sending error to Telegram")
    telegram.sendMessage(chat_id, message, message_id)
