#!/usr/bin/python3

import gevent.monkey
gevent.monkey.patch_all()
from gevent import pywsgi
import json, re, os
import threading
from sys import stderr
from urllib.parse import urlparse

from lib.config import *
import lib.worker as worker
if config_telegramBotToken:
    import lib.telegram as telegram
    botName = telegram.botName

def main(environ, start_response):
    def print_body():
        try:
            print(f"inbound {uri}", json.dumps(json.loads(request_body), indent=4), file=stderr)
        except Exception as e:
            print(e, "raw body: ", request_body, file=stderr)

    def print_headers():
        for item in sorted(environ.items()):
            print(item, file=stderr)

    uri = environ['PATH_INFO']
    request_body = environ['wsgi.input'].read()
    if 'CONTENT_TYPE' in environ and environ['CONTENT_TYPE'] == 'application/json':
        inbound = json.loads(request_body)

    # prepare response headers
    status = '200 OK'
    headers = [('Content-type', 'application/json')]
    start_response(status, headers)

    if debug:
        print_headers()
        print_body()

    # triage request - the Great Big If
    file_id=False
    user=''
    userRealName=''

    # Telegram
    if config_telegramOutgoingWebhook and uri == urlparse(config_telegramOutgoingWebhook).path:
        service = 'telegram'
        global botName
        if 'HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN' not in environ:
            print_headers()
            print("Fatal:", "Telegram auth absent", file=stderr)
            return [b'']
        elif environ['HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN'] != config_telegramOutgoingToken:
            tauth_header = environ['HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN']
            print_headers()
            print("Telegram auth expected:", config_telegramOutgoingToken, "got:", tauth_header, file=stderr)
            return [b'']
        if "message" not in inbound:
            return [b'']
        else:
            message_id = str(inbound["message"]["message_id"])
            chat_id = str(inbound["message"]["chat"]["id"])
            user_id = str(inbound["message"]["from"]["id"])
            chat_type = inbound["message"]["chat"]["type"]
            if "username" in inbound["message"]["from"]:
                user = '@' + inbound["message"]["from"]["username"]
                userRealName = inbound["message"]["from"]["first_name"]
            else:
                user = userRealName = '@' + inbound["message"]["from"]["first_name"]
            if chat_type == "private": # Anyone can find and PM the bot so we need to be careful
                if user_id in config_telegramAllowedUserIDs:
                    print(user, userRealName, user_id, "is whitelisted for private message")
                else:
                    print(user, userRealName, user_id, "is not whitelisted. Ignoring.", file=stderr)
                    return [b'']
            if "text" in inbound["message"]:
                message = inbound["message"]["text"]
                print(f"[Telegram]:", user, message)
                # under this condition we launch a worker thread
            elif "photo" in inbound["message"]:
                message = ''
                if "caption" in inbound["message"]:
                    message = inbound["message"]["caption"]
                photo = inbound["message"]["photo"][-1]
                file_id = photo["file_id"]
                print(f"[Telegram photo]:", user, file_id, message)
                # under this condition we launch a worker thread
            elif "document" in inbound["message"]:
                mime_type = inbound["message"]["document"]["mime_type"]
                if not mime_type.startswith('image/'):
                    print(f"[Telegram document unhandled mime_type]:", user, file_id, mime_type, message)
                    return [b'']
                message = ''
                if "caption" in inbound["message"]:
                    message = inbound["message"]["caption"]
                file_id = inbound["message"]["document"]["file_id"]
                print(f"[Telegram document]:", user, file_id, mime_type, message)
                # under this condition we launch a worker thread
            else:
                print(f"[{service}]: unhandled message without text/photo/document")
                return [b'']
    # Slack
    elif config_slackOutgoingWebhook and uri == urlparse(config_slackOutgoingWebhook).path:
        service = 'slack'
        if 'token' not in inbound:
            print_body()
            print("Fatal:", "Slack auth absent", file=stderr)
            return [b'']
        elif inbound['token'] != config_slackOutgoingToken:
            print_body()
            print("Slack auth expected:", config_slackOutgoingToken, "got:", inbound['token'], file=stderr)
            return [b'']
        if 'type' in inbound:
            if inbound['type'] == 'url_verification':
                response = json.dumps({"challenge": inbound["challenge"]})
                print("Incoming verificarion challenge. Replying with", response, file=stderr)
                response = bytes(response, "utf-8")
                return [b'']
            if inbound['type'] == 'event_callback':
                message_id = str(inbound["event"]["ts"])
                message = inbound['event']['text']
                message = re.sub(r'<http://.*\|([\w\.]+)>', '\g<1>', message) # <http://dub.ax|dub.ax> becomes dub.ax
                message = re.sub(r'<(@[\w\.]+)>', '\g<1>', message) # <@QWERTY> becomes @QWERTY
                user = '<@' + inbound['event']['user'] + '>' # ZXCVBN becomes <@ZXCVBN>
                botName = '@' + inbound['authorizations'][0]['user_id'] # QWERTY becomes @QWERTY
                chat_id = inbound['event']['channel']
                print(f"[{service}]:", service, user, message)
                # under this condition we launch a worker thread
            else:
                print(f"[{service}]: unhandled 'type'")
                return [b'']
        else:
            print(f"[{service}]: unhandled: no 'type'")
            return [b'']
    else:
        print("Unknown URI", uri, file=stderr)
        status = "404 Not Found"
        start_response(status, headers)
        return [b'']

    def runWorker():
        worker.process_request(service, chat_id, user, message, botName, userRealName, chat_type, message_id, file_id)

    # process in a background thread so we don't keep the requesting client waiting
    t = threading.Thread(target=runWorker)
    t.start()

    # Meanwhile, return an empty response to the client
    return [b'']

if __name__ == '__main__':
    if os.getuid() == 0:
        print("Running as superuser. This is not recommended.", file=stderr)
    httpd = pywsgi.WSGIServer((config_ip, config_port), main)
    if debug:
        print("Debugging mode is on", file=stderr)
        httpd.secure_repr = False
    print(f'Opening socket on http://{config_ip}:{config_port}', file=stderr)
    try:
        httpd.serve_forever()
    except OSError as e:
        print(e, file=stderr)
        exit(1)
