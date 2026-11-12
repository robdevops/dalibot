#!/usr/bin/python3

import io
import re
import time
from sys import stderr
import threading
import urllib.request, socket

from lib.config import *
import lib.telegram as telegram
import lib.openrouter as openrouter
from lib.multipart import image_type
from lib.styles import STYLES, with_style

def parse_command(message, botName):
	"""Work out which model a message asks for. Returns (command, prompt, addressed).
	'/flux a cat' -> ('flux', 'a cat', True); '@bot a cat' -> (default command, 'a cat', True)."""
	text = message.strip()
	m = re.match(r'^/(\w+)(@\w+)?\s*(.*)$', text, re.S)
	if m and m.group(1).lower() in image_models:
		if m.group(2) and botName and m.group(2).lower() != botName.lower():
			return config_telegramBotCommand, text, False # addressed to a different bot
		return m.group(1).lower(), m.group(3).strip(), True
	if botName and text.startswith(botName):
		return config_telegramBotCommand, text[len(botName):].strip(), True
	return config_telegramBotCommand, text, False

class Typing:
	"""Keeps Telegram's 'typing...' indicator showing while we wait for the image model."""
	def __init__(self, service, chat_id):
		self.enabled = service == 'telegram'
		self.chat_id = chat_id
		self.stopped = threading.Event()

	def start(self):
		if self.enabled:
			threading.Thread(target=self._run, daemon=True).start()

	def _run(self):
		# the indicator lasts about 5 seconds, so refresh it until we are done
		while not self.stopped.is_set():
			telegram.sendChatAction(self.chat_id)
			self.stopped.wait(4)

	def stop(self):
		self.stopped.set()

def process_request(service, chat_id, user, message, botName, userRealName, chat_type, message_id, file_id=False, style=None, edit_message_id=None):
	typing = Typing(service, chat_id)
	try:
		_process_request(typing, service, chat_id, user, message, botName, userRealName, chat_type, message_id, file_id, style, edit_message_id)
	finally:
		typing.stop()

def _process_request(typing, service, chat_id, user, message, botName, userRealName, chat_type, message_id, file_id, style, edit_message_id):
	now = int(time.time())
	command, prompt, addressed = parse_command(message, botName)
	model = image_models[command][0]
	if file_id:
		print("Detected inbound photo")
		if addressed or chat_type == 'private':
			typing.start()
			message = prompt
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
			print("Uploading image to OpenRouter")
			variations = 2 if debug else 4
			prompt = message if message else 'Create a variation of this image'
			success, image_url = openrouter.variations(image_data, prompt, variations, model)
			if success:
				print("Sending result to Telegram")
				if cropped:
					message = message + "\nNote: I centre-cropped your non-square image before sending it to the image model"
				if isinstance(image_url, list):
					telegram.sendMediaGroup(chat_id, image_url, message)
				else:
					telegram.sendPhoto(chat_id, image_url, message)
				if config_archive:
					if isinstance(image_url, list):
						for idx, url in enumerate(image_url):
							filename = config_archive_dir + '/variation_' + str(now) + '_' + str(idx+1) + '.' + image_type(url)[0]
							threading.Thread(target=url_to_file(url, filename)).start()
						print("end of batch")
					else:
						filename = config_archive_dir + '/image_variation_' + str(now) + '.' + image_type(image_url)[0]
						image_bytesio = download_file(image_url)
						bytesio_to_file(image_bytesio, filename)
			elif len(image_url):
				message = image_url
				error_to_telegram(chat_id, message, message_id)

	else:
		if addressed or chat_type == 'private':
			message = prompt # the prompt as the user wrote it; it is also the caption, so buttons can regenerate from it
			is_button = bool(style or edit_message_id)
			if len(message.split()) >= MIN_PROMPT_WORDS or is_button:
				typing.start()
				if len(message.split()) < MIN_PROMPT_WORDS: # only reachable from a button press
					# a button press on a very short prompt: have the text model flesh it out so it still works
					message = openrouter.expand(message, MIN_PROMPT_WORDS)
					print("Expanded short prompt:", message)
				print("Sending prompt to OpenRouter:", model, style or "")
				styled = message
				if style in STYLES:
					# a cheap text model removes words that fight the style; we then append a short style phrase
					cue = STYLES[style][1]
					styled = with_style(openrouter.remix(message, cue) or message, style, fix=openrouter.fix_style)
					print("Styled prompt:", styled)
				success, image_url = openrouter.generate(styled, model)
				if success:
					print("Sending result to Telegram")
					caption = styled # show the prompt that was actually used
					keyboard = telegram.imageKeyboard(command, style if style in STYLES else '')
					# Remix replaces the image in place; if that fails, post a new one instead
					if edit_message_id:
						print("Remix: replacing message", edit_message_id, "in place;", len(image_url) if isinstance(image_url, bytes) else "url", "bytes" if isinstance(image_url, bytes) else "")
					if not (edit_message_id and telegram.editPhoto(chat_id, edit_message_id, image_url, caption, keyboard)):
						if edit_message_id:
							print("Remix: in-place edit failed, posting a new image instead", file=stderr)
						telegram.sendPhoto(chat_id, image_url, caption, message_id, reply_markup=keyboard)
					if config_archive:
						image_bytesio = download_file(image_url)
						filename = config_archive_dir + '/image_' + str(now) + '.' + image_type(image_url)[0]
						bytesio_to_file(image_bytesio, filename)
				elif len(image_url):
					message = image_url
					error_to_telegram(chat_id, message, message_id)
			else:
				print("Prompt was too short - ignoring")
	return

def download_file(image_url):
	if isinstance(image_url, bytes):
		return io.BytesIO(image_url)
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
