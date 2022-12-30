#!/usr/bin/python3

from gevent import pywsgi
import json, re
import threading
import logging, logging.handlers
from sys import stderr

from lib.config import *
import lib.telegram as telegram
import lib.worker as worker

def main(environ, start_response):
    syslog = logging.getLogger('name')
    syslog.setLevel(logging.DEBUG)
    handler = logging.handlers.SysLogHandler(address = '/dev/log')
    formatter = logging.Formatter('dalibot: %(message)s')
    handler.setFormatter(formatter)
    syslog.addHandler(handler)

    def log(message, loglevel):
        if loglevel == 'critical':
            print(message, file=stderr)
            syslog.error(message)
        elif loglevel == 'warning':
            print(message, file=stderr)
            syslog.warning(message)
        elif loglevel == 'info':
            print(message)
            syslog.info(message)
        elif loglevel == 'debug':
            print(message)
            syslog.debug(message)
        else:
            print(message)

    def print_body(inbound):
        try:
            print(f"inbound {uri}", json.dumps(inbound, indent=4), file=stderr)
        except Exception as e:
            print(e, "raw body: ", inbound, file=stderr)

    def print_headers(environ):
        for item in sorted(environ.items()):
            print(item, file=stderr)

    file_id=False
    request_body = environ['wsgi.input'].read()
    user=''
    userRealName=''

    # prepare response
    status = '200 OK'
    headers = [('Content-type', 'application/json')]
    start_response(status, headers)

    # process request
    uri = environ['PATH_INFO']
    inbound = json.loads(request_body)
    if debug:
        print_headers(environ)
        print_body(inbound)
    if uri == '/telegram':
        service = 'telegram'
        botName = '@' + telegram.getMe()['username']
        if 'HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN' not in environ:
            print_headers()
            print("Fatal:", service, "authorisation header not present", file=stderr)
            return [b'<h1>Unauthorized</h1>']
        elif environ['HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN'] != config_telegramOutgoingToken:
            print_headers()
            print("Fatal: Telegram authorisation header is present but incorrect. Expected:", config_telegramOutgoingToken, file=stderr)
            return [b'<h1>Unauthorized</h1>']
        if "message" not in inbound:
            return [b'Unsupported']
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
                    return [b'<h1>Unauthorized</h1>']
            file_id=False
            if "text" in inbound["message"]:
                message = inbound["message"]["text"]
                print(f"[Telegram]:", user, message)
            elif "photo" in inbound["message"]:
                message = ''
                if "caption" in inbound["message"]:
                    message = inbound["message"]["caption"]
                photo = inbound["message"]["photo"][-1]
                file_id = photo["file_id"]
                print(f"[Telegram photo]:", user, file_id, message)
            elif "document" in inbound["message"]:
                mime_type = inbound["message"]["document"]["mime_type"]
                if not mime_type.startswith('image/'):
                    return [b'<h1>Unhandled</h1>']
                    print(f"[Telegram document unhandled mime_type]:", user, file_id, mime_type, message)
                message = ''
                if "caption" in inbound["message"]:
                    message = inbound["message"]["caption"]
                file_id = inbound["message"]["document"]["file_id"]
            else:
                print(f"[{service}]: unhandled message without text/photo/document", file=stderr)
                return [b'<h1>Unhandled</h1>']
                print(f"[Telegram document]:", user, file_id, message)
    elif uri == '/slack':
        service = 'slack'
        if 'token' not in inbound:
            print_body(inbound)
            print("Fatal:", service, "authorisation header not present", file=stderr)
            return [b'<h1>Unauthorized</h1>']
        elif inbound['token'] != config_slackOutgoingToken:
            print_body(inbound)
            print("Fatal:", service, "authorisation is present but incorrect. Expected:", config_slackOutgoingToken, file=stderr)
            return [b'<h1>Unauthorized</h1>']
        if 'type' in inbound:
            if inbound['type'] == 'url_verification':
                response = json.dumps({"challenge": inbound["challenge"]})
                print("Incoming verificarion challenge. Replying with", response)
                response = bytes(response, "utf-8")
                return [response]
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
                print(f"[{service}]: unhandled 'type'", file=stderr)
                return [b'<h1>Unhandled</h1>']
        else:
            print(f"[{service}]: unhandled: no 'type'", file=stderr)
            return [b'Unhandled']
    else:
        print("Unknown URI", uri, file=stderr)
        status = "404 Not Found"
        start_response(status, headers)
        return [b'<h1>404</h1>']

    def runWorker():
        worker.process_request(service, chat_id, user, message, botName, userRealName, chat_type, message_id, file_id)

    # process in a background thread so we don't keep the requesting client waiting
    t = threading.Thread(target=runWorker)
    t.start()

    # Return an empty response to the client
    return [b'']

if __name__ == '__main__':
    httpd = pywsgi.WSGIServer((config_ip, config_port), main)
    if debug:
        print("Debugging mode is on")
        httpd.secure_repr = False
    print(f'Listening on http://{config_ip}:{config_port}', file=stderr)
    # to start the server asynchronously, call server.start()
    # we use blocking serve_forever() here because we have no other jobs
    httpd.serve_forever()
