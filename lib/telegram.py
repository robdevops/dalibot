from lib.config import *
from sys import stderr
import concurrent.futures
import urllib.request, urllib.parse, json, socket
import lib.multipart as multipart

def setWebhook():
	url = webhooks['telegram'] + 'setWebhook'
	params = {}
	params['url'] = config_telegramOutgoingWebhook
	#params['url'] = '' # unsubscribe
	params['allowed_updates'] = json.dumps(['message', 'callback_query'])
	params['drop_pending_updates'] = True
	params['secret_token'] = config_telegramOutgoingToken
	data = urllib.parse.urlencode(params).encode()
	req = urllib.request.Request(url, data, method='POST')
	try:
		r = urllib.request.urlopen(req, timeout=config_http_timeout)
	except (urllib.error.HTTPError, urllib.error.URLError, socket.timeout) as e:
		print("Failure executing request:", url, data, str(e))
		return False
	print("Registering Telegram webhook:", r.read().decode(), file=stderr)

def deleteWebhook():
	# Telegram refuses getUpdates while a webhook is registered
	url = webhooks['telegram'] + 'deleteWebhook'
	req = urllib.request.Request(url, b'', method='POST')
	try:
		r = urllib.request.urlopen(req, timeout=config_http_timeout)
	except (urllib.error.HTTPError, urllib.error.URLError, socket.timeout) as e:
		print("Failure executing request:", url, str(e))
		return False
	print("Removing Telegram webhook (long polling mode):", r.read().decode(), file=stderr)

def getUpdates(offset=None, poll_timeout=50):
	"""Long poll for new messages. Returns a list (possibly empty), or None on error."""
	url = webhooks['telegram'] + 'getUpdates'
	data = {'timeout': poll_timeout, 'allowed_updates': ['message', 'callback_query']}
	if offset is not None:
		data['offset'] = offset
	req = urllib.request.Request(url, json.dumps(data).encode(), {'Content-type': 'application/json'}, method='POST')
	try:
		r = urllib.request.urlopen(req, timeout=poll_timeout + config_http_timeout)
		return json.load(r)['result']
	except (urllib.error.HTTPError, urllib.error.URLError, socket.timeout, ValueError, KeyError) as e:
		print("Failure executing request:", url, str(e), file=stderr)
		return None

def getMe():
	url = webhooks['telegram'] + 'getMe'
	params = {"url": config_telegramOutgoingWebhook}
	data = urllib.parse.urlencode(params).encode()
	req = urllib.request.Request(url, data, method='POST')
	try:
		r = urllib.request.urlopen(req, timeout=config_http_timeout)
	except (urllib.error.HTTPError, urllib.error.URLError, socket.timeout) as e:
		print("Failure executing request:", url, data, str(e))
		return False
	if r.code != 200:
		print(r.code, "error Telegram getMe")
		return False
	return json.load(r)['result']

def answerCallbackQuery(callback_query_id, text=None):
	"""Acknowledge a button press so Telegram stops showing the loading spinner."""
	url = webhooks['telegram'] + "answerCallbackQuery"
	data = {'callback_query_id': callback_query_id}
	if text:
		data['text'] = text
	req = urllib.request.Request(url, json.dumps(data).encode('utf-8'), {'Content-type': 'application/json'}, method='POST')
	try:
		urllib.request.urlopen(req, timeout=config_http_timeout)
	except (urllib.error.HTTPError, urllib.error.URLError, socket.timeout) as e:
		print("Failure executing request:", url, str(e), file=stderr)
		return False

def sendPhoto(chat_id, photo_url, caption, message_id=None, reload_button=False):
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
	if reload_button:
		# the caption is the prompt, so a press can regenerate without us storing anything
		data['reply_markup'] = {'inline_keyboard': [[{'text': '\U0001F504 Reload', 'callback_data': 'reload'}]]}
	if isinstance(photo_url, bytes):
		# image data rather than a URL: upload it
		del data['photo']
		data = {k: (json.dumps(v) if isinstance(v, dict) else str(v).lower() if isinstance(v, bool) else v) for k, v in data.items() if v is not None}
		content_type, data = multipart.encode(data, {'photo': ('image.png', 'image/png', photo_url)})
		headers = {'Content-type': content_type}
	else:
		data = json.dumps(data).encode('utf-8')
	req = urllib.request.Request(url, data, headers)
	try:
		r = urllib.request.urlopen(req, timeout=config_http_timeout)
	except (urllib.error.HTTPError, urllib.error.URLError, socket.timeout) as e:
		print("Failure executing request:", url, str(e))
		return False
	if r.code == 200:
		print(r.code, "OK Telegram sendPhoto", caption)
	else:
		print(r.code, "error Telegram sendPhoto", caption)
		return False

def sendMediaGroup(chat_id, url_list, caption, message_id=None):
	if any(isinstance(item, bytes) for item in url_list):
		# albums can't carry uploaded bytes in a JSON request: send them one by one
		for idx, item in enumerate(url_list):
			sendPhoto(chat_id, item, caption if idx == 0 else '', message_id)
		return
	media = []
	for idx, openai_url in enumerate(url_list):
		if idx == 0:
			media.append({'type': 'photo', 'media': openai_url, 'caption': caption})
		else:
			media.append({'type': 'photo', 'media': openai_url})
	url = webhooks['telegram'] + "sendMediaGroup?chat_id=" + str(chat_id)
	data = {
	'disable_notification': 'true',
	'chat_id': chat_id,
	'media': media,
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
		executor.submit(setWebhook if config_telegramOutgoingWebhook else deleteWebhook)
		executor.submit(setMyCommands)
		thread = executor.submit(getMe)
		botName = '@' + thread.result()['username']
