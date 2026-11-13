#!/usr/bin/python3

import io
import re
import concurrent.futures
import time
from sys import stderr
import threading
import urllib.request, socket

from lib.config import *
import lib.telegram as telegram
import lib.openrouter as openrouter
import lib.store as store
from lib.multipart import image_type
from lib.styles import STYLES, with_style

def mention_pattern(botName):
	"""Matches @botname anywhere in a text (case-insensitive, and not as part of a longer name or an email address)."""
	return re.compile(r'(?<!\w)' + re.escape(botName) + r'(?!\w)', re.IGNORECASE)

def mentions_bot(text, botName):
	return bool(botName) and bool(mention_pattern(botName).search(text))

def without_mention(text, botName):
	"""text with every @botname removed and the spaces tidied."""
	if not botName:
		return text.strip()
	text = re.sub(r'\s+', ' ', mention_pattern(botName).sub(' ', text)).strip()
	return re.sub(r'\s+([,.;:!?])', r'\1', text) # "a fox @bot, please" -> "a fox, please"

UPSCALE = re.compile(r'(?<!\w)#upscale(?!\w)', re.IGNORECASE)

def upscale_picture(typing, chat_id, message_id, file_id, prompt, command, model):
	"""A picture posted with #upscale in its caption: have the image model redraw it at full size, post the result
	and add it to the image history under the rest of the caption. The small original is not kept."""
	typing.start()
	caption = re.sub(r'\s+', ' ', UPSCALE.sub(' ', prompt)).strip() # the tag is not part of the caption
	print("Detected a picture to upscale; downloading from telegram")
	image_url = telegram.getFileURL(file_id)
	if not image_url:
		return error_to_telegram(chat_id, "error fetching image from Telegram", message_id)
	success, cropped, image_data = prepare_image(image_url)
	if not success:
		return error_to_telegram(chat_id, image_data, message_id)
	print("Uploading image to OpenRouter to be upscaled")
	success, image = openrouter.upscale(image_data, model)
	if not success:
		return error_to_telegram(chat_id, image or "The image model returned nothing.", message_id)
	sent = telegram.sendPhoto(chat_id, image, caption or None, message_id)
	if sent and sent['message_id'] and sent['file_id']:
		store.save_image(chat_id, sent['message_id'], caption, command, None, sent['file_id'], caption)
	if cropped:
		telegram.sendMessage(chat_id, "Note: I centre-cropped your non-square image before sending it to the image model", message_id)

def parse_command(message, botName):
	"""Work out which model a message asks for. Returns (command, prompt, addressed).
	'/flux a cat' -> ('flux', 'a cat', True); '@bot a cat' or 'a cat @bot' -> (default command, 'a cat', True).
	An alias counts as the command it stands for: '/imagine a cat' -> (default command, 'a cat', True).
	The bot can be tagged anywhere in the text; the tag is not part of the prompt."""
	text = message.strip()
	m = re.match(r'^/(\w+)(@\w+)?\s*(.*)$', text, re.S)
	name = m.group(1).lower() if m else ''
	name = COMMAND_ALIASES.get(name, name)
	if name in image_models or name in CREDITS_COMMANDS:
		if m.group(2) and botName and m.group(2).lower() != botName.lower():
			return config_telegramBotCommand, text, False # addressed to a different bot
		return name, without_mention(m.group(3), botName), True
	if mentions_bot(text, botName):
		return config_telegramBotCommand, without_mention(text, botName), True
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

class Pending:
	"""While a button press is being worked on, show it on the buttons: the pressed one gets an hourglass and
	the native green style. The image and caption stay as they are until the new image replaces them. If we end
	up not replacing the image (an error, or we had to post a new message instead), put the previous buttons back."""
	def __init__(self, chat_id, message_id, command, button):
		self.chat_id, self.message_id, self.command, self.button = chat_id, message_id, command, button
		self.thread = None
		self.replaced = False # set when the image has been replaced in place

	def start(self):
		if self.button and self.message_id and not self.thread:
			self.thread = threading.Thread(target=self._show, daemon=True) # in parallel with generating
			self.thread.start()

	def _show(self):
		telegram.editButtons(self.chat_id, self.message_id, telegram.imageKeyboard(self.command, self.button['style'], pending=(self.button['action'], self.button['target'])))

	def wait(self):
		if self.thread:
			self.thread.join(timeout=10) # so this can never land after the final image

	def finish(self):
		if self.thread and not self.replaced:
			self.wait()
			telegram.editButtons(self.chat_id, self.message_id, telegram.imageKeyboard(self.command, self.button['style']))

def process_request(service, chat_id, user, message, botName, userRealName, chat_type, message_id, file_id=False, style=None, edit_message_id=None, button=None):
	typing = Typing(service, chat_id)
	command = parse_command(message, botName)[0]
	pending = Pending(chat_id, edit_message_id, command, button if service == 'telegram' else None)
	try:
		_process_request(typing, pending, service, chat_id, user, message, botName, userRealName, chat_type, message_id, file_id, style, edit_message_id)
	finally:
		typing.stop()
		pending.finish()

def _process_request(typing, pending, service, chat_id, user, message, botName, userRealName, chat_type, message_id, file_id, style, edit_message_id):
	now = int(time.time())
	command, prompt, addressed = parse_command(message, botName)
	model = image_models[command][0]
	if file_id and UPSCALE.search(message):
		upscale_picture(typing, chat_id, message_id, file_id, prompt, command, model)
	elif file_id:
		print("Detected inbound photo")
		if addressed or chat_type == 'private':
			typing.start()
			note = prompt # what the user wrote with the photo, if anything
			message = prompt
			if len(message):
				message = 'Variation of ' + message
			variations = 2 if debug else 4
			# have the text model pick a style and a viewpoint for each image while the picture is downloaded and prepared, so it adds no waiting
			looks_job = concurrent.futures.ThreadPoolExecutor(max_workers=1)
			looks_future = looks_job.submit(openrouter.variation_looks, note, variations)
			looks_job.shutdown(wait=False)
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
			result = openrouter.variations(image_data, note, variations, model, looks_future.result())
			success, image_url = result[0], result[1]
			if success:
				print("Sending result to Telegram")
				captions = variation_captions(message, result[2], cropped)
				if isinstance(image_url, list):
					telegram.sendMediaGroup(chat_id, image_url, captions, message_id) # one album, so the chat isn't flooded
				else:
					telegram.sendPhoto(chat_id, image_url, captions[0], message_id)
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
				pending.start()
				style_key = style if style in STYLES else ''
				# 'base' is the prompt after any expansion and cleanup, before the style phrase is added
				base = None
				if style_key and edit_message_id and pending.button and pending.button['action'] == 'r':
					# Remix of a styled image: the cleanup would give the same answer again, so reuse the saved result
					saved = ((store.get(chat_id, edit_message_id) or {}).get('images', {}).get(style_key) or {}).get('base')
					if saved:
						base = saved
						print("Remix: reusing the saved prompt, no text model call")
				if not base:
					if len(message.split()) < MIN_PROMPT_WORDS: # only reachable from a button press
						# a button press on a very short prompt: have the text model flesh it out so it still works
						message = openrouter.expand(message, MIN_PROMPT_WORDS)
						print("Expanded short prompt:", message)
					base = message
					if style_key:
						# a cheap text model removes words that fight the style
						base = openrouter.remix(message, STYLES[style_key][1]) or message
				print("Sending prompt to OpenRouter:", model, style_key)
				styled = base
				if style_key: # then we append a short style phrase
					styled = with_style(base, style_key, fix=openrouter.fix_style)
					print("Styled prompt:", styled)
				success, image_url = openrouter.generate(styled, model)
				if success:
					print("Sending result to Telegram")
					caption = styled # show the prompt that was actually used
					keyboard = telegram.imageKeyboard(command, style_key)
					# Button presses replace the image in place; if that fails, post a new one instead
					sent = False
					if edit_message_id:
						pending.wait() # the 'working' edit must land first, or it could overwrite the new image
						print("Replacing message", edit_message_id, "in place;", len(image_url), "bytes" if isinstance(image_url, bytes) else "(url)")
						sent = telegram.editPhoto(chat_id, edit_message_id, image_url, caption, keyboard)
						if sent:
							sent['message_id'] = edit_message_id
							pending.replaced = True
						else:
							print("In-place edit failed, posting a new image instead", file=stderr)
					if not sent:
						sent = telegram.sendPhoto(chat_id, image_url, caption, message_id, reply_markup=keyboard)
					if sent and sent['message_id'] and sent['file_id']:
						if edit_message_id and sent['message_id'] != edit_message_id:
							# the old message couldn't be edited, so this is a new one: bring its earlier images along
							store.carry_over(chat_id, edit_message_id, sent['message_id'])
						# remember the image (by Telegram file_id) so the buttons can switch back to it
						store.save_image(chat_id, sent['message_id'], prompt, command, style_key, sent['file_id'], caption, base)
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

def variation_captions(message, looks, cropped):
	"""One caption per variation: its style and viewpoint. The first also carries what the user asked for ("Variation of ...")
	and a note if we cropped the photo. Telegram allows 1024 characters per caption."""
	captions = []
	for i, (style, viewpoint) in enumerate(looks):
		lines = [message] if i == 0 and message else []
		lines.append(f"{style}, {viewpoint}")
		if i == 0 and cropped:
			lines.append("Note: I centre-cropped your non-square image before sending it to the image model")
		caption = "\n".join(lines)
		captions.append(caption if len(caption) <= 1024 else caption[:1021] + "...")
	return captions

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
