from lib.config import *
from sys import stderr
import concurrent.futures
import urllib.request, urllib.parse, json, socket
import lib.multipart as multipart
from lib.styles import STYLES

def setWebhook():
	url = webhooks['telegram'] + 'setWebhook'
	params = {}
	params['url'] = config_telegramOutgoingWebhook
	#params['url'] = '' # unsubscribe
	params['allowed_updates'] = json.dumps(['message', 'edited_message', 'callback_query'])
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
	data = {'timeout': poll_timeout, 'allowed_updates': ['message', 'edited_message', 'callback_query']}
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

def answerCallbackQuery(callback_query_id, text=None, alert=False):
	"""Acknowledge a button press so Telegram stops showing the loading spinner.
	text appears as a brief toast, or as a pop-up the user must dismiss if alert is True."""
	url = webhooks['telegram'] + "answerCallbackQuery"
	data = {'callback_query_id': callback_query_id}
	if text:
		data['text'] = text
		data['show_alert'] = alert
	req = urllib.request.Request(url, json.dumps(data).encode('utf-8'), {'Content-type': 'application/json'}, method='POST')
	try:
		urllib.request.urlopen(req, timeout=config_http_timeout)
	except (urllib.error.HTTPError, urllib.error.URLError, socket.timeout) as e:
		print("Failure executing request:", url, str(e), file=stderr)
		return False

def sendChatAction(chat_id, action='typing'):
	"""Show 'typing...' in the chat. Telegram clears it after about 5 seconds."""
	url = webhooks['telegram'] + "sendChatAction"
	data = json.dumps({'chat_id': chat_id, 'action': action}).encode('utf-8')
	req = urllib.request.Request(url, data, {'Content-type': 'application/json'}, method='POST')
	try:
		urllib.request.urlopen(req, timeout=config_http_timeout)
	except (urllib.error.HTTPError, urllib.error.URLError, socket.timeout):
		pass # purely cosmetic

def imageKeyboard(command, style='', pending=None):
	"""Buttons under an image. callback_data is '<action>:<command>:<style>'.
	'g' goes to that style: the image we already made for it if there is one, otherwise a new one.
	'r' (Remix) always makes a new image in the current style. Both replace the image in place.
	The style being shown gets Telegram's native blue 'primary' button style.
	pending=(action, style) shows the keyboard while that button's image is being made: it gets an hourglass and
	the native green 'success' style, nothing else is highlighted, and every button just says "still working"."""
	def button(text, style_key, selected=False, action='g'):
		b = {'text': text, 'callback_data': f'{action}:{command}:{style_key}'}
		if pending:
			b['callback_data'] = 'n:-:' # busy: see parseTelegramCallback
			if pending == (action, style_key):
				b['text'] = '\u23F3 ' + text.replace('\U0001F504 ', '') # the hourglass replaces the refresh icon
				b['style'] = 'success'
		elif selected:
			b['style'] = 'primary' # needs a Telegram client from Feb 2026 or later; older ones show it unstyled
		return b
	styles = [button(label, key, key == style) for key, (label, _) in STYLES.items()]
	rows = [styles[i:i + 3] for i in range(0, len(styles), 3)]
	first_row = [button('\U0001F504 Remix', style, action='r')]
	if style or (pending and pending == ('g', '')): # a way back to the image before any style was applied
		first_row.append(button('\u21A9 Original', ''))
	return {'inline_keyboard': [first_row] + rows}

def editButtons(chat_id, message_id, reply_markup):
	"""Change just the buttons under one of our photo messages, leaving the image and caption alone. Returns True on success."""
	url = webhooks['telegram'] + "editMessageReplyMarkup"
	fields = {'chat_id': chat_id, 'message_id': int(message_id), 'reply_markup': reply_markup}
	req = urllib.request.Request(url, json.dumps(fields).encode('utf-8'), {'Content-type': 'application/json'}, method='POST')
	try:
		urllib.request.urlopen(req, timeout=config_http_timeout)
	except (urllib.error.HTTPError, urllib.error.URLError, socket.timeout) as e:
		detail = ''
		if isinstance(e, urllib.error.HTTPError):
			try:
				detail = e.read().decode()[:300]
			except Exception:
				pass
			e.close()
		print(f"Telegram editMessageReplyMarkup failed for chat {chat_id} message {message_id}:", str(e), detail, file=stderr)
		return False
	return True

def editPhoto(chat_id, message_id, photo, caption, reply_markup=None):
	"""Replace the image, caption and buttons of one of our messages in place.
	photo is image bytes, a URL or a Telegram file_id. Returns {'message_id', 'file_id'} on success, False on failure."""
	url = webhooks['telegram'] + "editMessageMedia"
	media = {'type': 'photo', 'caption': caption}
	if isinstance(photo, bytes):
		media['media'] = 'attach://photo'
		fields = {'chat_id': chat_id, 'message_id': message_id, 'media': json.dumps(media)}
		if reply_markup: # editing the image without sending the buttons again would remove them
			fields['reply_markup'] = json.dumps(reply_markup)
		ext, mime = multipart.image_type(photo)
		content_type, data = multipart.encode(fields, {'photo': ('image.' + ext, mime, photo)})
		headers = {'Content-type': content_type}
	else:
		media['media'] = photo
		fields = {'chat_id': chat_id, 'message_id': int(message_id), 'media': media}
		if reply_markup:
			fields['reply_markup'] = reply_markup
		data = json.dumps(fields).encode('utf-8')
		headers = {'Content-type': 'application/json'}
	req = urllib.request.Request(url, data, headers, method='POST')
	try:
		r = urllib.request.urlopen(req, timeout=config_http_timeout)
	except (urllib.error.HTTPError, urllib.error.URLError, socket.timeout) as e:
		detail = ''
		if isinstance(e, urllib.error.HTTPError):
			try:
				detail = e.read().decode()[:300] # Telegram says why, e.g. "message is not modified"
			except Exception:
				pass
			e.close()
		print(f"Telegram editMessageMedia failed for chat {chat_id} message {message_id}:", str(e), detail, file=stderr)
		return False
	print("200 OK Telegram editMessageMedia", caption)
	return photoInfo(r)

def sendPhoto(chat_id, photo_url, caption, message_id=None, reply_markup=None):
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
	if reply_markup:
		data['reply_markup'] = reply_markup
	if isinstance(photo_url, bytes):
		# image data rather than a URL: upload it
		del data['photo']
		data = {k: (json.dumps(v) if isinstance(v, dict) else str(v).lower() if isinstance(v, bool) else v) for k, v in data.items() if v is not None}
		ext, mime = multipart.image_type(photo_url)
		content_type, data = multipart.encode(data, {'photo': ('image.' + ext, mime, photo_url)})
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
		return photoInfo(r)
	else:
		print(r.code, "error Telegram sendPhoto", caption)
		return False

def photoInfo(response):
	"""The message id and the photo's file_id from a sendPhoto/editMessageMedia response.
	Always a (truthy) dict; the values are None if Telegram's answer was not what we expected."""
	try:
		message = json.load(response)['result']
		return {'message_id': str(message['message_id']), 'file_id': message['photo'][-1]['file_id']}
	except (ValueError, KeyError, IndexError, TypeError):
		return {'message_id': None, 'file_id': None}

ALBUM_MAX = 10 # Telegram albums hold 2 to 10 photos

def sendMediaGroup(chat_id, items, caption, message_id=None):
	"""Send photos as one album. items are URLs, file_ids or image bytes (uploaded). caption is either one text, which goes on
	the first photo (Telegram then shows it under the whole album), or a list with one caption per photo (Telegram then shows
	each caption only when that photo is opened). Albums can't carry buttons. Returns True if everything was sent."""
	items = list(items)
	captions = list(caption) if isinstance(caption, (list, tuple)) else [caption] + [''] * (len(items) - 1)
	captions += [''] * (len(items) - len(captions))
	if len(items) == 1:
		return bool(sendPhoto(chat_id, items[0], captions[0], message_id))
	if len(items) > ALBUM_MAX: # more than one album's worth: several albums
		return all([sendMediaGroup(chat_id, items[i:i + ALBUM_MAX], captions[i:i + ALBUM_MAX], message_id) for i in range(0, len(items), ALBUM_MAX)])
	media, files = [], {}
	for idx, item in enumerate(items):
		entry = {'type': 'photo'}
		if isinstance(item, bytes):
			name = f'photo{idx}'
			ext, mime = multipart.image_type(item)
			files[name] = (f'{name}.{ext}', mime, item)
			entry['media'] = 'attach://' + name
		else:
			entry['media'] = item
		if captions[idx]:
			entry['caption'] = captions[idx]
		media.append(entry)
	url = webhooks['telegram'] + "sendMediaGroup"
	fields = {'chat_id': chat_id, 'media': media, 'disable_notification': True, 'allow_sending_without_reply': True}
	if message_id:
		fields['reply_to_message_id'] = message_id
	if files:
		fields = {k: (json.dumps(v) if isinstance(v, list) else str(v).lower() if isinstance(v, bool) else v) for k, v in fields.items()}
		content_type, data = multipart.encode(fields, files)
		headers = {'Content-type': content_type}
	else:
		data = json.dumps(fields).encode('utf-8')
		headers = {'Content-type': 'application/json'}
	req = urllib.request.Request(url, data, headers, method='POST')
	try:
		urllib.request.urlopen(req, timeout=config_http_timeout)
	except (urllib.error.HTTPError, urllib.error.URLError, socket.timeout) as e:
		detail = ''
		if isinstance(e, urllib.error.HTTPError):
			try:
				detail = e.read().decode()[:300]
			except Exception:
				pass
			e.close()
		print("Telegram sendMediaGroup failed:", str(e), detail, file=stderr)
		return False
	print("200 OK Telegram sendMediaGroup", len(items), "photos;", captions[0])
	return True

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

def setMessageReaction(chat_id, message_id, emoji):
	"""Put an emoji reaction on a message: a quiet acknowledgement that adds nothing to the chat."""
	url = webhooks['telegram'] + "setMessageReaction"
	data = json.dumps({'chat_id': chat_id, 'message_id': int(message_id), 'reaction': [{'type': 'emoji', 'emoji': emoji}]}).encode('utf-8')
	req = urllib.request.Request(url, data, {'Content-type': 'application/json'}, method='POST')
	try:
		r = urllib.request.urlopen(req, timeout=config_http_timeout)
	except (urllib.error.HTTPError, urllib.error.URLError, socket.timeout) as e:
		print("Failure executing request:", url, data, str(e))
		return False
	return r.code == 200

def setMyCommands():
	url = webhooks['telegram'] + "setMyCommands"
	headers = {'Content-type': 'application/json'}
	commands = [{'command': config_telegramBotCommand, 'description': 'generate an image from at least three words'}]
	for name, (model, description) in image_models.items():
		if name != config_telegramBotCommand:
			commands.append({'command': name, 'description': 'same, using ' + description})
	for alias, name in COMMAND_ALIASES.items():
		commands.append({'command': alias, 'description': 'same as /' + name})
	commands.append({'command': CREDITS_COMMANDS[0], 'description': 'show what has been spent on OpenRouter: today, week, month'})
	data = {'commands': commands}
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
