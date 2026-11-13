#!/usr/bin/python3

import os
from lib.config import *

# Webhook mode (a listening web server) is needed for serverless platforms, Slack,
# or self-hosted with telegramOutgoingWebhook set. Otherwise self-hosted uses
# Telegram long polling, which needs no web server and no extra modules.
webhook_mode = bool(config_telegramOutgoingWebhook or config_slackOutgoingWebhook)
if os.environ.get("AWS_LAMBDA_FUNCTION_NAME") is None and 'GCF_BLOCK_RUNTIME' not in os.environ:
	if webhook_mode:
		print("We are running self-hosted (webhook mode)!")
		import gevent.monkey
		gevent.monkey.patch_all()
		from gevent import pywsgi
	else:
		print("We are running self-hosted (Telegram long polling)!")
elif 'CNB_STACK_ID' in os.environ and 'google' in os.environ.get("CNB_STACK_ID"):
	print("We are running as a Google Cloud Function!")
else:
	print("We are running as a Lambda Function!")

import json
import re
import time
from sys import stderr
from urllib.parse import urlparse

import lib.worker as worker
from lib.worker import mentions_bot
import lib.openrouter as openrouter
import lib.store as store
import lib.deadline as deadline
store.check()
from lib.styles import STYLES
if config_telegramBotToken:
	import lib.telegram as telegram
	botName = telegram.botName

import threading
#import multiprocessing

def lambda_handler(event, context):
	deadline.start(context) # so slow waits give up before Lambda kills us
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

def startWorker(service, chat_id, user, message, botName, userRealName, chat_type, message_id, file_id, style=None, edit_message_id=None, button=None):
	def runWorker():
		worker.process_request(service, chat_id, user, message, botName, userRealName, chat_type, message_id, file_id, style, edit_message_id, button)

	# process in a background thread so we don't keep the requesting client waiting
	t = threading.Thread(target=runWorker)
	t.start()
	return t

def money(amount):
	return f'${amount:,.4f}' if amount < 1 else f'${amount:,.2f}'

def replyCredits(chat_id, user_id, message_id):
	"""/credits (also /tokens, /usage, /cost): what OpenRouter says the bot has spent today, this week and this month.
	If TELEGRAM_ALLOWED_USER_IDS lists user ids, only those users may ask. With "all", or no list, anyone who can talk to the bot can."""
	if not config_telegramAllowAll and config_telegramAllowedUserIDs and user_id not in config_telegramAllowedUserIDs:
		print(user_id, "is not allowed to see spend. Ignoring.", file=stderr)
		telegram.sendMessage(chat_id, "Sorry, only approved users can see usage.", message_id)
		return
	ok, spent = openrouter.spend()
	if not ok:
		telegram.sendMessage(chat_id, "Couldn't get usage from OpenRouter: " + spent, message_id)
		return
	telegram.sendMessage(chat_id, "OpenRouter spend\ntoday: " + money(spent['today']) + "\nweek: " + money(spent['week']) + "\nmonth: " + money(spent['month']), message_id)

def imageFileId(msg):
	"""The Telegram file_id of the picture in a message (largest size of a photo, or an image sent as a file), if any."""
	if msg.get("photo"):
		return msg["photo"][-1]["file_id"]
	document = msg.get("document") or {}
	if document.get("mime_type", "").startswith("image/"):
		return document["file_id"]

def parseTelegram(inbound):
	"""Extract what the worker needs from a Telegram update. Returns None if it should be ignored."""
	file_id = False
	user = userRealName = ''
	if "callback_query" in inbound:
		return parseTelegramCallback(inbound["callback_query"])
	# An edited message arrives as its own kind of update. We only react to an edit that tags the bot (or is a command),
	# so fixing a typo in an ordinary message does nothing.
	edited = "message" not in inbound and "edited_message" in inbound
	if "message" not in inbound and not edited:
		return
	msg = inbound["edited_message"] if edited else inbound["message"]
	message_id = str(msg["message_id"])
	chat_id = str(msg["chat"]["id"])
	user_id = str(msg["from"]["id"])
	chat_type = msg["chat"]["type"]
	if "username" in msg["from"]:
		user = '@' + msg["from"]["username"]
		userRealName = msg["from"]["first_name"]
	else:
		user = userRealName = '@' + msg["from"]["first_name"]
	if chat_type == "private": # Anyone can find and PM the bot so we need to be careful
		if telegram_user_allowed(user_id):
			print(user, userRealName, user_id, "is whitelisted for private message")
		else:
			print(user, userRealName, user_id, "is not whitelisted. Ignoring.", file=stderr)
			return
	if "text" in msg:
		message = msg["text"]
		print("[Telegram]:", user, message)
		command, prompt, addressed = worker.parse_command(message, botName)
		if edited and (not addressed or command in CREDITS_COMMANDS):
			print("[Telegram edit]: not addressed to the bot, ignoring")
			return
		if command in CREDITS_COMMANDS and (addressed or chat_type == "private"):
			replyCredits(chat_id, user_id, message_id)
			return
		# Tagging the bot (or sending a bare command) in reply to a picture asks for variations of that picture.
		# A command with a prompt, like "/dream a red fox", stays a text prompt even when it is a reply.
		replied_image = imageFileId(msg.get("reply_to_message") or {})
		if replied_image and addressed and (not prompt or mentions_bot(message, botName)):
			file_id = replied_image
			print("[Telegram reply to a picture]:", user, message)
	elif "photo" in msg:
		message = msg.get("caption", '')
		file_id = msg["photo"][-1]["file_id"]
		print("[Telegram photo]:", user, message)
		if edited and not worker.parse_command(message, botName)[2]:
			print("[Telegram edit]: not addressed to the bot, ignoring")
			return
	elif "document" in msg:
		mime_type = msg["document"]["mime_type"]
		message = msg.get("caption", '')
		if not mime_type.startswith('image/'):
			print("[Telegram document unhandled mime_type]:", user, mime_type, message)
			return
		file_id = msg["document"]["file_id"]
		print("[Telegram document]:", user, mime_type, message)
		if edited and not worker.parse_command(message, botName)[2]:
			print("[Telegram edit]: not addressed to the bot, ignoring")
			return
	else:
		print("[telegram]: unhandled message without text/photo/document")
		return
	return chat_id, user, userRealName, message, chat_type, message_id, file_id, None, None, None

def originalPrompt(msg):
	"""Recover the prompt a button's image was made from. The caption shows the prompt actually used
	(which may be cleaned up and styled), so prefer the user's original message that the image replies to."""
	original = msg.get("reply_to_message") or {}
	text = original.get("text") or original.get("caption")
	if text:
		command, prompt, addressed = worker.parse_command(text, botName)
		if addressed and prompt:
			return prompt
	# the original message is gone: undo what we added to the caption
	caption = re.sub(r"\n\nStyle: .*$", "", msg.get("caption") or "", flags=re.S) # captions from older versions
	for label, cue in STYLES.values():
		if caption.endswith(", " + cue):
			return caption[:-len(", " + cue)]
	return caption

def parseTelegramCallback(query):
	"""A press of a button under an image. callback_data is '<action>:<command>:<style>'.
	Every press replaces the image in place. 'g' goes to a style: if we already made that image it is shown
	straight away from the store (no model calls); otherwise, and for 'r' (Remix), a new one is generated."""
	if "message" not in query:
		return
	data = query.get("data", "")
	if data == "reload": # buttons on images sent before styles existed
		data = "r:" + config_telegramBotCommand + ":"
	parts = data.split(":")
	if parts[0] == "n": # a button on an image that is still being made
		telegram.answerCallbackQuery(query["id"], "Still painting, one moment\u2026")
		return
	if len(parts) != 3 or parts[0] not in ("g", "r") or parts[1] not in image_models or (parts[2] and parts[2] not in STYLES):
		return
	action, command, style = parts
	msg = query["message"]
	sender = query["from"]
	user_id = str(sender["id"])
	chat_type = msg["chat"]["type"]
	if chat_type == "private" and not telegram_user_allowed(user_id):
		print(user_id, "is not whitelisted. Ignoring.", file=stderr)
		telegram.answerCallbackQuery(query["id"])
		return
	chat_id, message_id = str(msg["chat"]["id"]), str(msg["message_id"])
	record = store.get(chat_id, message_id)
	label = STYLES[style][0] if style else "original"
	if record and action == "g":
		if record["current"] == (style or store.BASE):
			telegram.answerCallbackQuery(query["id"], f"Already showing the {label} image")
			return
		cached = record["images"].get(style or store.BASE)
		if cached:
			keyboard = telegram.imageKeyboard(command, style)
			if telegram.editPhoto(chat_id, message_id, cached["file_id"], cached["caption"], keyboard):
				telegram.answerCallbackQuery(query["id"], f"Showing the {label} image")
				store.set_current(chat_id, message_id, style)
				return
			# This message can't be edited (Telegram refused). The image is saved, so post it as a new message
			# and carry the history over, instead of paying for a new image.
			print("[Telegram button]: could not edit the message; posting the stored image as a new message", file=stderr)
			sent = telegram.sendPhoto(chat_id, cached["file_id"], cached["caption"], reply_markup=keyboard)
			if sent and sent["message_id"]:
				store.carry_over(chat_id, message_id, sent["message_id"], current=style)
				telegram.answerCallbackQuery(query["id"], f"Posted the {label} image as a new message")
				return
			print("[Telegram button]: could not post the stored image either, generating a new one", file=stderr)
	prompt = record["prompt"] if record else originalPrompt(msg)
	if not prompt:
		print("[Telegram button]: could not find the original prompt", file=stderr)
		telegram.answerCallbackQuery(query["id"], "Sorry, I can't find the original prompt for this image. Please send a new prompt.", alert=True)
		return
	telegram.answerCallbackQuery(query["id"], "Remixing..." if action == "r" else f"Painting in the style of {label}..." if style else "Generating...")
	user = '@' + sender["username"] if "username" in sender else '@' + sender["first_name"]
	userRealName = sender["first_name"]
	# reply to the original prompt message if it still exists
	reply_to = msg.get("reply_to_message", {}).get("message_id")
	reply_to_id = str(reply_to) if reply_to else None
	print("[Telegram button]:", user, command, style, prompt, f"(on message {message_id} in a {chat_type} chat {chat_id})")
	# what to show while this is generated, and what to put back if it fails
	before = (record["current"] if record else style if action == "r" else "").replace(store.BASE, "")
	button = {'action': action, 'target': style, 'style': before}
	return chat_id, user, userRealName, '/' + command + ' ' + prompt, chat_type, reply_to_id, False, style or None, message_id, button

def poll():
	"""Telegram long polling: no web server, domain or certificate required."""
	offset = None
	while True:
		updates = telegram.getUpdates(offset)
		if updates is None:
			time.sleep(5)
			continue
		for update in updates:
			offset = update['update_id'] + 1
			try:
				parsed = parseTelegram(update)
				if parsed:
					chat_id, user, userRealName, message, chat_type, message_id, file_id, style, edit_message_id, button = parsed
					startWorker('telegram', chat_id, user, message, botName, userRealName, chat_type, message_id, file_id, style, edit_message_id, button)
			except Exception as e:
				print("Error handling update:", repr(e), file=stderr)

def main(event):
	if debug:
		print(json.dumps(event, indent=4))
	inbound = event.get('body')
	uri = event.get('uri')
	if not inbound or not uri:
		# e.g. the Lambda console Test tab: nothing to process, but start-up has registered the webhook
		print("Ignoring invocation without a request body", file=stderr)
		return
	# triage request - the Great Big If
	file_id=False
	style=None
	edit_message_id=None
	button=None
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
			print("Telegram auth failed: the X-Telegram-Bot-Api-Secret-Token header doesn't match TELEGRAM_OUTGOING_TOKEN", file=stderr)
			return
		parsed = parseTelegram(inbound)
		if not parsed:
			return
		chat_id, user, userRealName, message, chat_type, message_id, file_id, style, edit_message_id, button = parsed
	# Slack
	elif config_slackOutgoingWebhook and uri == urlparse(config_slackOutgoingWebhook).path:
		service = 'slack'
		if 'token' not in inbound:
			print(json.dumps(event['body'], indent=4))
			print("Fatal:", "Slack auth absent", file=stderr)
			return
		elif inbound['token'] != config_slackOutgoingToken:
			print(json.dumps(event['body'], indent=4))
			print("Slack auth failed: the token doesn't match SLACK_OUTGOING_TOKEN", file=stderr)
			return
		if 'type' in inbound:
			if inbound['type'] == 'url_verification':
				response = json.dumps({"challenge": inbound["challenge"]})
				print("Incoming verificarion challenge. Replying with", response, file=stderr)
				return response
			if inbound['type'] == 'event_callback':
				message_id = str(inbound["event"]["ts"])
				message = inbound['event']['text']
				message = re.sub(r'<http://.*\|([\w\.]+)>', r'\g<1>', message) # <http://dub.ax|dub.ax> becomes dub.ax
				message = re.sub(r'<(@[\w\.]+)>', r'\g<1>', message) # <@QWERTY> becomes @QWERTY
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

	t = startWorker(service, chat_id, user, message, botName, userRealName, chat_type, message_id, file_id, style, edit_message_id, button)

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

		Therefore, Slack is unsupported in AWS with our current architecture.
		A second Lambda function with SNS might be a good solution.
		"""
		t.join()

	return

if __name__ == '__main__':
	#multiprocessing.set_start_method('spawn')
	if os.getuid() == 0:
		print("Running as superuser. This is not recommended.", file=stderr)
	if not webhook_mode:
		if not config_telegramBotToken:
			print("Set TELEGRAM_BOT_TOKEN in the environment", file=stderr)
			exit(1)
		try:
			poll()
		except KeyboardInterrupt:
			exit(0)
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
