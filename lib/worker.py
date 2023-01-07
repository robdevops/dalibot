#!/usr/bin/python3

import io
import time
from sys import stderr
import threading
import urllib.request, socket

from lib.config import *
import lib.telegram as telegram
import lib.openai as openai

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
            if not image_url:
                message = "error fetching image from Telegram"
                error_to_telegram(chat_id, message, message_id)
                return
            success, cropped, image_data = prepare_image(image_url)
            if not success:
                message = image_data
                error_to_telegram(chat_id, message, message_id)
                return
            print("Uploading image to OpenAI")
            if debug:
                size='256x256'
                variations=2
            else:
                size='1024x1024'
                variations=4
            success, image_url = openai.imagesVariations(image_data, size, variations)
            if success:
                print("Sending result to Telegram")
                if cropped:
                    message = message + "\nNote: I centre-cropped your non-square image before sending it to OpenAI"
                if isinstance(image_url, list):
                    telegram.sendMediaGroup(chat_id, image_url, message)
                else:
                    telegram.sendPhoto(chat_id, image_url, message)
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
                if debug:
                    size='256x256'
                else:
                    size='1024x1024'
                success, image_url = openai.imagesGenerations(message, size, 1)
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
    return

def download_file(image_url):
    try:
        r = urllib.request.urlopen(image_url, timeout=config_http_timeout)
    except Exception as e:
        print(str(e), file=stderr)
    if r.code == 200:
        print(r.code, "downloaded file for archiving")
        image_data = io.BytesIO(r.read())
    else:
        print(r.code, "while downloading file for archiving")
    return image_data

def bytesio_to_file(image_bytesio, filename):
    try:
        with open(filename, "wb") as f:
            f.write(image_bytesio.getbuffer())
    except Exception as e:
        print(str(e), file=stderr)
    else:
        print("Saved", filename)
    return

def prepare_image(image_url):
    try:
        from PIL import Image
    except ModuleNotFoundError:
        message = "This feature requires the pillow library to be installed"
        print(message, file=stderr)
        return False, False, message
    except ImportError as e:
        message = "Pillow import error: " + str(e) + " check Python version and CPU architecture match the build environment"
        print(message, file=stderr)
        return False, False, message
    print("Opening image")
    try:
        im = Image.open(urllib.request.urlopen(image_url, timeout=config_http_timeout))
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
        im = im_cropped
        #im = im_backup = im_cropped
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
        # im = im_backup.resize((int(new_width), int(new_height)))
        # resize successively to increase speed
        im = im.resize((int(new_width), int(new_height)))
        with io.BytesIO() as byte_stream:
            im.save(byte_stream, format='PNG')
            image_bytesio = byte_stream.getvalue()
    print("Final size:", str(im.size), "px;", f"{len(image_bytesio):,} bytes")
    return True, cropped, image_bytesio

def url_to_file(url, filename):
    image_bytesio = download_file(url)
    bytesio_to_file(image_bytesio, filename)
    return

def error_to_telegram(chat_id, message, message_id):
    print("Sending error to Telegram")
    telegram.sendMessage(chat_id, message, message_id)
    return
