from lib.config import *
from sys import stderr
import concurrent.futures
import urllib.request, urllib.parse, json, socket

def setWebhook():
    url = webhooks['telegram'] + 'setWebhook'
    params = {}
    params['url'] = config_telegramOutgoingWebhook
    #params['url'] = '' # unsubscribe
    params['allowed_updates'] = "message"
    params['drop_pending_updates'] = True
    params['secret_token'] = config_telegramOutgoingToken
    data = urllib.parse.urlencode(params).encode()
    req = urllib.request.Request(url, data, method='POST')
    try:
        r = urllib.request.urlopen(req, timeout=config_http_timeout)
    except (urllib.error.HTTPError, urllib.error.URLError, socket.timeout) as e:
        print("Failure executing request:", url, headers, data, str(e))
        return False
    print("Registering Telegram webhook:", r.read().decode(), file=stderr)

def getMe():
    url = webhooks['telegram'] + 'getMe'
    params = {"url": config_telegramOutgoingWebhook}
    data = urllib.parse.urlencode(params).encode()
    req = urllib.request.Request(url, data, method='POST')
    try:
        r = urllib.request.urlopen(req, timeout=config_http_timeout)
    except (urllib.error.HTTPError, urllib.error.URLError, socket.timeout) as e:
        print("Failure executing request:", url, headers, data, str(e))
        return False
    if r.code != 200:
        print(r.code, "error Telegram getMe")
        return False
    return json.load(r)['result']

def sendPhoto(chat_id, photo_url, caption, message_id=None):
    url = webhooks['telegram'] + "sendPhoto?chat_id=" + str(chat_id)
    headers = {'Content-type': 'application/json'}
    data = {
    'disable_notification': 'true',
    'chat_id': chat_id,
    'photo': photo_url,
    'caption': caption,
    "allow_sending_without_reply": True,
    "reply_to_message_id": message_id
    }
    data = json.dumps(data).encode('utf-8')
    req = urllib.request.Request(url, data, headers)
    try:
        r = urllib.request.urlopen(req, timeout=config_http_timeout)
    except (urllib.error.HTTPError, urllib.error.URLError, socket.timeout) as e:
        print("Failure executing request:", url, headers, data, str(e))
        return False
    if r.code == 200:
        print(r.code, "OK Telegram sendPhoto", caption)
    else:
        print(r.code, "error Telegram sendPhoto", caption)
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
    data = {
    'disable_notification': 'true',
    'chat_id': chat_id,
    'media': media,
    "allow_sending_without_reply": True,
    "reply_to_message_id": message_id
    }
    data = json.dumps(data).encode('utf-8')
    req = urllib.request.Request(url, data, headers, method='POST')
    try:
        r = urllib.request.urlopen(req, timeout=config_http_timeout)
    except (urllib.error.HTTPError, urllib.error.URLError, socket.timeout) as e:
        print("Failure executing request:", url, headers, data, str(e))
        return False
    if r.code == 200:
        print(r.code, "OK Telegram sendMediaGroup", caption)
    else:
        print(r.code, "error Telegram sendMediaGroup", caption)
        return False

def getFileURL(file_id):
    url = webhooks['telegram'] + "getFile"
    data = {'file_id': file_id}
    data = json.dumps(data).encode('utf-8')
    headers = {'Content-type': 'application/json'}
    req = urllib.request.Request(url, data, headers, method='POST')
    try:
        r = urllib.request.urlopen(req, timeout=config_http_timeout)
    except (urllib.error.HTTPError, urllib.error.URLError, socket.timeout) as e:
        print("Failure executing request:", url, data.decode(), str(e))
        return False
    if r.code != 200:
        print(r.code, "error Telegram getFileURL")
        return False
    data = json.load(r)
    file_path = data['result']['file_path']
    file_url = 'https://api.telegram.org/file/bot' + config_telegramBotToken + '/' + file_path
    print(file_id, file_path, file_url)
    return(file_url)

def sendMessage(chat_id, message, message_id=None):
    url = webhooks['telegram'] + "sendMessage?chat_id=" + str(chat_id)
    data = {'text': message,
    "parse_mode": "HTML",
    "disable_web_page_preview": True,
    "disable_notification": True,
    "allow_sending_without_reply": True,
    "reply_to_message_id": message_id
    }
    data = json.dumps(data).encode('utf-8')
    req = urllib.request.Request(url, data, method='POST')
    req.add_header('Content-type', 'application/json')
    try:
        r = urllib.request.urlopen(req, timeout=config_http_timeout)
    except (urllib.error.HTTPError, urllib.error.URLError, socket.timeout) as e:
        print("Failure executing request:", url, data, str(e))
        return False
    if r.code == 200:
        print(r.code, "OK Telegram sendMessage", message)
    else:
        print(r.code, "error Telegram sendMessage", message)
        return False

def setMyCommands():
    url = webhooks['telegram'] + "setMyCommands"
    headers = {'Content-type': 'application/json'}
    command = [{'command': config_telegramBotCommand, 'description': 'generate an image from at least three words'}]
    data = {'commands': command}
    data = json.dumps(data).encode('utf-8')
    req = urllib.request.Request(url, data, headers, method='POST')
    try:
        r = urllib.request.urlopen(req, timeout=config_http_timeout)
    except (urllib.error.HTTPError, urllib.error.URLError, socket.timeout) as e:
        print("Failure executing request:", url, data, str(e))
        return False
    if not r.code == 200:
        print(r.code, "error Telegram setMyCommands")
        return False
    print("Registering Telegram bot commands:", r.read().decode(), file=stderr)

if config_telegramBotToken:
    with concurrent.futures.ThreadPoolExecutor() as executor:
        executor.submit(setWebhook)
        executor.submit(setMyCommands)
        thread = executor.submit(getMe)
        botName = '@' + thread.result()['username']
