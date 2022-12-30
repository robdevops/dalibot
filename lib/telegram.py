import requests
from lib.config import *
import threading

def setWebhook():
    telegram_url = webhooks['telegram'] + 'setWebhook'
    params = {
        "url": config_telegramOutgoingWebhook, "allowed_updates": "message", 'secret_token': config_telegramOutgoingToken}
    #params = {"url": ''} # unsubscribe
    r = requests.post(
        telegram_url,
        params=params,
        timeout=config_http_timeout
    )
    print("Registering Telegram webhook:", r.text)

def getMe():
    telegram_url = webhooks['telegram'] + 'getMe'
    params = {"url": config_telegramOutgoingWebhook}
    r = requests.post(
        telegram_url,
        params=params,
        timeout=config_http_timeout
    )
    return r.json()['result']

def sendPhoto(chat_id, photo_url, caption, message_id=None):
    url = webhooks['telegram'] + "sendPhoto?chat_id=" + str(chat_id)
    headers = {'Content-type': 'application/json'}
    payload = {
    'disable_notification': 'true',
    'chat_id': chat_id,
    'photo': photo_url,
    'caption': caption,
    "allow_sending_without_reply": True,
    "reply_to_message_id": message_id
    }
    try:
        r = requests.post(url, headers=headers, json=payload, timeout=config_http_timeout)
    except:
        print("Failure executing request:", url, headers, payload)
        return False
    if r.status_code == 200:
        print(r.status_code, "OK outbound to Telegram")
    else:
        print(r.status_code, "error outbound to Telegram")
        return False

def sendMediaGroup(chat_id, url_list, caption, message_id=None):
    media = []
    for idx, openai_url in enumerate(url_list):
        if idx == 0:
            media.append({'type': 'photo', 'media': openai_url, 'caption': caption})
        else:
            media.append({'type': 'photo', 'media': openai_url})
    url = webhooks['telegram'] + "sendMediaGroup?chat_id=" + str(chat_id)
    headers = {'Content-type': 'application/json'}
    payload = {
    'disable_notification': 'true',
    'chat_id': chat_id,
    'media': media,
    "allow_sending_without_reply": True,
    "reply_to_message_id": message_id
    }
    try:
        r = requests.post(url, headers=headers, json=payload, timeout=config_http_timeout)
    except:
        print("Failure executing request:", url, headers, payload)
        return False
    if r.status_code == 200:
        print(r.status_code, "OK outbound to Telegram")
    else:
        print(r.status_code, "error outbound to Telegram")
        return False

def getFileURL(file_id):
    url = webhooks['telegram'] + "getFile"
    headers = {'Content-type': 'application/json'}
    payload = {'file_id': file_id }
    try:
        r = requests.post(url, headers=headers, json=payload, timeout=config_http_timeout)
    except:
        print("Failure executing request:", url, headers, payload)
        return False
    if r.status_code == 200:
        print(r.status_code, "OK outbound to Telegram")
    else:
        print(r.status_code, "error outbound to Telegram")
        return False
    data = r.json()
    file_path = data['result']['file_path']
    file_url = 'https://api.telegram.org/file/bot' + config_telegramBotToken + '/' + file_path
    return(file_url)

def sendMessage(chat_id, message, message_id=None):
    url = webhooks['telegram'] + "sendMessage?chat_id=" + str(chat_id)
    headers = {'Content-type': 'application/json'}
    payload = {'text': message,
    "parse_mode": "HTML",
    "disable_web_page_preview": True,
    "disable_notification": True,
    "allow_sending_without_reply": True,
    "reply_to_message_id": message_id
    }
    try:
        r = requests.post(url, headers=headers, json=payload, timeout=config_http_timeout)
    except:
        print("Failure executing request:", url, headers, payload)
        return False
    if r.status_code == 200:
        print(r.status_code, "OK outbound to Telegram")
    else:
        print(r.status_code, "error outbound to Telegram")
        return False

def setMyCommands():
    url = webhooks['telegram'] + "setMyCommands"
    headers = {'Content-type': 'application/json'}
    command = [{'command': 'dream', 'description': 'generate an image from at least three words'}]
    payload = {'commands': command}
    try:
        r = requests.post(url, headers=headers, json=payload, timeout=config_http_timeout)
    except:
        print("Failure executing request:", url, headers, payload)
        return False
    if not r.status_code == 200:
        print(r.status_code, "error outbound to Telegram")
        return False
    print("Registering Telegram bot commands:", r.text)

if config_telegramOutgoingToken and config_telegramOutgoingWebhook:
    try:
        threading.Thread(target=setWebhook).start()
        threading.Thread(target=setMyCommands).start()
    except ReadTimeout:
        print("Telegram timeout")
