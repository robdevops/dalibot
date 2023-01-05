#!/usr/bin/python3

import os
if os.environ.get("AWS_LAMBDA_FUNCTION_NAME") is None and 'GCF_BLOCK_RUNTIME' not in os.environ:
    print("We are running standalone!")
    import gevent.monkey
    gevent.monkey.patch_all()
    from gevent import pywsgi
elif 'CNB_STACK_ID' in os.environ and 'google' in os.environ.get("CNB_STACK_ID"):
    print("We are running as a Google Cloud Function!")
else:
    print("We are running as a Lambda Function!")

import json
import re
from sys import stderr
from urllib.parse import urlparse

from lib.config import *
import lib.worker as worker
if config_telegramBotToken:
    import lib.telegram as telegram
    botName = telegram.botName

import threading
#import multiprocessing

def lambda_handler(event, context):
    response = main(event)
    if response:
        return response
    else:
        return ''

def google_function_handler(request):
    import functions_framework
    import json
    response = hello_http(request)
    @functions_framework.http
    def hello_http(request):
        headers = {}
        for k, v in sorted(request.headers.items()):
            headers[k] = v
        uri = request.path
        body = request.get_json(silent=True)
        args = request.args
        event = { 'headers': headers, 'uri': uri, 'body': body, 'args': args}
        response = main(event)
    if response:
        return response
    else:
        return ''

def wsgi_handler(environ, start_response):
    headers = {}
    for h in sorted(environ.items()):
        if not h[0].startswith('wsgi.'):
            if h[0].startswith('HTTP_'):
                header = h[0].lstrip('HTTP_').replace('_', '-').title()
                headers[header] = h[1]
            else:
                headers[h[0]] = h[1]
    uri = environ['PATH_INFO']
    if 'CONTENT_TYPE' in environ and environ['CONTENT_TYPE'] == 'application/json':
        body = json.loads(environ['wsgi.input'].read())
    else:
        for item in event['headers'].getitems():
            print(item, file=stderr)
        print("ignoring non-json request", file=stderr)
        return b['']

    event = { 'headers': headers, 'uri': uri, 'body': body }
    status = '200 OK'
    headers = [('Content-type', 'application/json')]
    start_response(status, headers)
    response = main(event)
    if response:
        response = bytes(response, "utf-8")
        return [response]
    else:
        return [b'']

def main(event):
    if debug:
        print(json.dumps(event, indent=4))
    inbound = event['body']
    uri = event['uri']
    # triage request - the Great Big If
    file_id=False
    user=''
    userRealName=''

    # Telegram
    if config_telegramOutgoingWebhook and uri == urlparse(config_telegramOutgoingWebhook).path:
        service = 'telegram'
        global botName
        if 'X-Telegram-Bot-Api-Secret-Token' not in event['headers']:
            print("Telegram auth absent", file=stderr)
            return
        elif event['headers']['X-Telegram-Bot-Api-Secret-Token'] != config_telegramOutgoingToken:
            tauth_header = event['headers']['X-Telegram-Bot-Api-Secret-Token']
            print("Telegram auth expected:", config_telegramOutgoingToken, "got:", tauth_header, file=stderr)
            return
        if "message" not in inbound:
            return
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
                    return
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
                print(f"[Telegram photo]:", user, message)
                # under this condition we launch a worker thread
            elif "document" in inbound["message"]:
                mime_type = inbound["message"]["document"]["mime_type"]
                if not mime_type.startswith('image/'):
                    print(f"[Telegram document unhandled mime_type]:", user, file_id, mime_type, message)
                    return
                message = ''
                if "caption" in inbound["message"]:
                    message = inbound["message"]["caption"]
                file_id = inbound["message"]["document"]["file_id"]
                print(f"[Telegram document]:", user, mime_type, message)
                # under this condition we launch a worker thread
            else:
                print(f"[{service}]: unhandled message without text/photo/document")
                return
    # Slack
    elif config_slackOutgoingWebhook and uri == urlparse(config_slackOutgoingWebhook).path:
        service = 'slack'
        if 'token' not in inbound:
            print(json.dumps(event['body'], indent=4))
            print("Fatal:", "Slack auth absent", file=stderr)
            return
        elif inbound['token'] != config_slackOutgoingToken:
            print(json.dumps(event['body'], indent=4))
            print("Slack auth expected:", config_slackOutgoingToken, "got:", inbound['token'], file=stderr)
            return
        if 'type' in inbound:
            if inbound['type'] == 'url_verification':
                response = json.dumps({"challenge": inbound["challenge"]})
                print("Incoming verificarion challenge. Replying with", response, file=stderr)
                return response
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
                return
        else:
            print(f"[{service}]: unhandled: no 'type'")
            return
    else:
        print("Unknown URI", uri, file=stderr)
        return

    def runWorker():
        worker.process_request(service, chat_id, user, message, botName, userRealName, chat_type, message_id, file_id)

    # process in a background thread so we don't keep the requesting client waiting
    t = threading.Thread(target=runWorker)
    t.start()

    #p = multiprocessing.Process(target=worker.process_request, args=(service, chat_id, user, message, botName, userRealName, chat_type, message_id, file_id))
    #p.start()

    if os.environ.get("AWS_LAMBDA_FUNCTION_NAME") is not None:
        """
        lambda freezes the environment before the worker completes unless we wait here.
        This breaks the whole purpose of threading.
        Waiting causes the client to retry and duplicates to be recieved, unless
        we turn on async for the Amazon API Gateway by adding header X-Amz-Invocation-Type
        with value 'Event' (including quotes). This is not a final solution, because
        it breaks our ability to respond, as is required for Slack verification requests.
        """
        t.join()

    return

if __name__ == '__main__':
    #multiprocessing.set_start_method('spawn')
    if os.getuid() == 0:
        print("Running as superuser. This is not recommended.", file=stderr)
    httpd = pywsgi.WSGIServer((config_ip, config_port), wsgi_handler)
    if debug:
        print("Debugging mode is on", file=stderr)
        httpd.secure_repr = False
    print(f'Opening socket on http://{config_ip}:{config_port}', file=stderr)
    try:
        httpd.serve_forever()
    except OSError as e:
        print(e, file=stderr)
        exit(1)
