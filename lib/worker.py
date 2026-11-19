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
import lib.palette as palette
import lib.chart as chart
import json
from lib.multipart import image_type
from lib.styles import STYLES, VIEWPOINTS, with_style

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

def model_tag(command):
	"""The hashtag the bot puts on a picture's caption to say which model made it: #gpt, #flux or #qwen, by the model
	the command actually uses (so the default command, whatever it is called, gets its model's tag). Any other model
	gets a tag made from its id."""
	model = image_models.get(command, (command,))[0] or ''
	for name, (named, _) in NAMED_MODELS.items():
		if named == model:
			return '#' + name
	tag = re.sub(r'[^0-9A-Za-z_]', '', model.split('/')[-1]) # e.g. #supermodel9
	return '#' + (tag if re.search('[A-Za-z]', tag) else 'model' + tag) # Telegram links a hashtag only if it has a letter

def model_tags():
	"""Every tag model_tag can give, and the command it stands for (a command named after its model when there is one)."""
	tags = {}
	for name in list(NAMED_MODELS) + list(image_models):
		if name in image_models:
			tags.setdefault(model_tag(name), name)
	return tags

def tag_caption(caption, command):
	"""caption with the model's hashtag on a line of its own at the end, kept within Telegram's caption limit."""
	tag = model_tag(command)
	if not caption:
		return tag
	room = telegram.CAPTION_MAX - len(tag) - 1
	if len(caption) > room:
		caption = caption[:room - 3] + '...'
	return caption + '\n' + tag

def split_model_tag(caption):
	"""(caption without the bot's model hashtag, the command the hashtag stands for or None). Only the bot's own tags
	are taken off, so a user's caption that ends with a hashtag of their own keeps it."""
	caption = caption or ''
	found = re.search(r'(?:^|\n)(#\w+)\s*$', caption) # the bot's tag is always on a line of its own
	if found and found.group(1) in model_tags():
		return caption[:found.start()], model_tags()[found.group(1)]
	return caption, None

UPSCALE = re.compile(r'(?<!\w)#upscale(?!\w)', re.IGNORECASE)
STRICT = re.compile(r'(?<!\w)#(?:strict|variation)(?!\w)', re.IGNORECASE) # #variation is another name for #strict

def is_command(message, name, botName=None):
	"""Does the message start with /name (or /name@thisbot)? In a group Telegram delivers commands to the bot even
	without admin access or a mention, so these work there with no @botname."""
	m = re.match(r'^\s*/(\w+)(@\w+)?(?:\s|$)', message or '')
	return bool(m and m.group(1).lower() == name and not (m.group(2) and botName and m.group(2).lower() != botName.lower()))

PALETTE = re.compile(r'(?<!\w)#(?:palette|hex)(?!\w)', re.IGNORECASE)

def wants_palette(message, botName=None):
	"""Does the message ask for a picture's colours: #palette or #hex anywhere, or /palette or /hex at the start?"""
	return any(is_command(message, name, botName) for name in PALETTE_COMMANDS) or bool(PALETTE.search(message or ''))

def make_palette(file_id, mode='vivid', layout='8'):
	"""(grid PNG, caption) of a Telegram picture's main colours, or (None, a message for the user). layout is '8' or
	'16' colours, or 'tones' (shadows, midtones and highlights, a row each). The caption lists the hex codes to copy."""
	image_url = telegram.getFileURL(file_id)
	if not image_url:
		return None, "error fetching image from Telegram"
	try:
		with urllib.request.urlopen(image_url, timeout=config_http_timeout) as r:
			image_data = r.read(20 * 1024 * 1024 + 1) # Telegram lets bots download up to 20 MB
		if layout == 'tones':
			bands = palette.tones(image_data, mode)
			return palette.tones_grid(bands), '\n'.join(f"{name}: {' '.join(hexes) or '-'}" for name, hexes in bands)
		hexes = palette.colours(image_data, int(layout), mode)
		return palette.grid(hexes), ' '.join(hexes)
	except ModuleNotFoundError:
		return None, "This feature requires the pillow library to be installed"
	except Exception as e:
		print("Palette failed:", repr(e), file=stderr)
		return None, "Sorry, I couldn't read the colours of that picture."

def palette_picture(typing, chat_id, message_id, file_id):
	"""Reply to the picture (message_id) with a grid of its main colours, each tile labelled with its hex code, the
	codes as text in the caption so they can be copied, and buttons to show them another way. Replying to the picture
	itself is what lets a button find it again. Made here with Pillow, so no model is asked. Recorded with kind
	'palette' (see save_palette)."""
	typing.start()
	print("Detected a picture for its palette; downloading from telegram")
	grid, caption = make_palette(file_id)
	if not grid:
		return error_to_telegram(chat_id, caption, message_id)
	sent = telegram.sendPhoto(chat_id, grid, caption, message_id, reply_markup=telegram.paletteKeyboard())
	if not sent:
		return error_to_telegram(chat_id, SEND_FAILED, message_id)
	save_palette(chat_id, sent, caption, 'vivid', '8', file_id)

def save_palette(chat_id, sent, caption, mode, layout, source=None):
	"""Record a palette view: kind 'palette' and command 'palette', so a gallery can leave palettes out. Each view
	(mode and layout, e.g. 'vivid-8', 'average-tones') is kept under its own key, so a button can show it again
	without redrawing it."""
	if sent and sent.get('message_id') and sent.get('file_id'):
		store.save_image(chat_id, sent['message_id'], caption, PALETTE_COMMAND, f'{mode}-{layout}', sent['file_id'], caption, kind='palette', source=source)

def wants_upscale(message, botName=None):
	"""Does the message ask for a picture to be redrawn at full size: #upscale anywhere, or /upscale at the start?"""
	return is_command(message, UPSCALE_COMMAND, botName) or bool(UPSCALE.search(message or ''))

def wants_strict(message, botName=None):
	"""Does the message ask for one faithful change to a picture: #strict or #variation anywhere, or /variation at the start?"""
	return is_command(message, STRICT_COMMAND, botName) or bool(STRICT.search(message or ''))

def without_tag(tag, text):
	return re.sub(r'\s+', ' ', tag.sub(' ', text)).strip()

def redraw_picture(typing, chat_id, message_id, file_id, caption, command, what, redraw, style=None, keyboard=None, pending=None, edit_message_id=None):
	"""Send the user's picture to the image model with redraw(image_data), post the one image that comes back with
	caption (and keyboard, if any), and add it to the image history under caption, with the picture's file_id as its
	source. With edit_message_id (a Retry press) the new image replaces that message's image instead.
	The user's own picture is not kept."""
	typing.start()
	if pending and edit_message_id:
		pending.start()
	print(f"Detected a picture to {what}; downloading from telegram")
	image_url = telegram.getFileURL(file_id)
	if not image_url:
		return error_to_telegram(chat_id, "error fetching image from Telegram", message_id)
	success, cropped, image_data = prepare_image(image_url)
	if not success:
		return error_to_telegram(chat_id, image_data, message_id)
	print(f"Uploading image to OpenRouter to {what}")
	success, image = redraw(image_data)
	if not success:
		return error_to_telegram(chat_id, image or "The image model returned nothing.", message_id)
	sent = False
	if edit_message_id:
		pending.wait() # the busy buttons must land first, or they could replace the new ones
		sent = telegram.editPhoto(chat_id, edit_message_id, image, tag_caption(caption, command), keyboard)
		if sent:
			sent['message_id'] = edit_message_id
			pending.replaced = True
		else:
			print("In-place edit failed, posting a new image instead", file=stderr)
	if not sent:
		sent = telegram.sendPhoto(chat_id, image, tag_caption(caption, command), message_id, reply_markup=keyboard)
	if not sent:
		return error_to_telegram(chat_id, "The picture was redrawn, but sending it to Telegram failed. Please try again.", message_id)
	if sent['message_id'] and sent['file_id']:
		# filed under the source's style; a Retry in place keeps the image it replaces in the record's 'previous'
		store.save_image(chat_id, sent['message_id'], caption, command, style, sent['file_id'], caption, source=file_id)
	else:
		print(f"The picture ({what}) was posted but could not be added to the image history", file=stderr)
	if cropped:
		telegram.sendMessage(chat_id, "Note: I centre-cropped your non-square image before sending it to the image model", message_id)

def upscale_picture(typing, chat_id, message_id, file_id, prompt, command, model, style=None, pending=None, edit_message_id=None):
	"""A picture posted with #upscale in its caption: have the image model redraw it at full size, post the result
	and add it to the image history under the rest of the caption. The small original is not kept."""
	caption = without_tag(UPSCALE, prompt) # the tag is not part of the caption
	redraw_picture(typing, chat_id, message_id, file_id, caption, command, 'upscale', lambda image: openrouter.upscale(image, model), style,
		keyboard=telegram.retryKeyboard(command, action='u'), pending=pending, edit_message_id=edit_message_id)

def strict_picture(typing, chat_id, message_id, file_id, prompt, command, model, style=None, pending=None, edit_message_id=None):
	"""A picture posted with #strict and an instruction in its caption: one image of that picture changed as the
	instruction says, with none of the extra styles and viewpoints that variations add."""
	note = without_tag(STRICT, prompt)
	if not note:
		return error_to_telegram(chat_id, "Add what you want changed, for example: #strict make it night time", message_id)
	redraw_picture(typing, chat_id, message_id, file_id, note, command, 'change as asked', lambda image: openrouter.strict(image, note, model), style,
		keyboard=telegram.retryKeyboard(command), pending=pending, edit_message_id=edit_message_id)

def parse_command(message, botName):
	"""Work out which model a message asks for. Returns (command, prompt, addressed).
	'/flux a cat' -> ('flux', 'a cat', True); '@bot a cat' or 'a cat @bot' -> (default command, 'a cat', True).
	An alias counts as the command it stands for: '/imagine a cat' -> (default command, 'a cat', True).
	The bot can be tagged anywhere in the text; the tag is not part of the prompt."""
	text = message.strip()
	m = re.match(r'^/(\w+)(@\w+)?\s*(.*)$', text, re.S)
	name = m.group(1).lower() if m else ''
	name = COMMAND_ALIASES.get(name, name)
	if name in (STRICT_COMMAND, UPSCALE_COMMAND) + PALETTE_COMMANDS and name not in image_models: # commands that work on a picture
		if m.group(2) and botName and m.group(2).lower() != botName.lower():
			return config_telegramBotCommand, text, False
		return config_telegramBotCommand, without_mention(m.group(3), botName), True
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

	def _keyboard(self, busy):
		if self.button['action'] in ('s', 'u', 't'): # Retry under a #strict, #upscale or technical picture
			return telegram.retryKeyboard(self.command, pending=busy, action=self.button['action'])
		return telegram.imageKeyboard(self.command, self.button['style'], pending=(self.button['action'], self.button['target']) if busy else None)

	def _show(self):
		telegram.editButtons(self.chat_id, self.message_id, self._keyboard(True))

	def wait(self):
		if self.thread:
			self.thread.join(timeout=10) # so this can never land after the final image

	def finish(self):
		if self.thread and not self.replaced:
			self.wait()
			telegram.editButtons(self.chat_id, self.message_id, self._keyboard(False))

def process_request(service, chat_id, user, message, botName, userRealName, chat_type, message_id, file_id=False, style=None, edit_message_id=None, button=None):
	typing = Typing(service, chat_id)
	command = parse_command(message, botName)[0]
	pending = Pending(chat_id, edit_message_id, command, button if service == 'telegram' else None)
	try:
		_process_request(typing, pending, service, chat_id, user, message, botName, userRealName, chat_type, message_id, file_id, style, edit_message_id)
	finally:
		typing.stop()
		try:
			pending.finish()
		finally:
			if button and edit_message_id: # a button press: let the next press on this message through
				store.release(chat_id, edit_message_id, button.get('claim'))

def _process_request(typing, pending, service, chat_id, user, message, botName, userRealName, chat_type, message_id, file_id, style, edit_message_id):
	now = int(time.time())
	command, prompt, addressed = parse_command(message, botName)
	model = image_models[command][0]
	if file_id and wants_palette(message, botName):
		palette_picture(typing, chat_id, message_id, file_id)
	elif file_id and wants_upscale(message, botName):
		upscale_picture(typing, chat_id, message_id, file_id, prompt, command, model, style, pending, edit_message_id)
	elif file_id and wants_strict(message, botName):
		strict_picture(typing, chat_id, message_id, file_id, prompt, command, model, style, pending, edit_message_id)
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
				captions = [tag_caption(caption, command) for caption in variation_captions(message, result[2], cropped)]
				if isinstance(image_url, list):
					sent = telegram.sendMediaGroup(chat_id, image_url, captions, message_id) # one album, so the chat isn't flooded
				else:
					sent = telegram.sendPhoto(chat_id, image_url, captions[0], message_id)
					sent = [sent] if sent else []
				if not sent:
					error_to_telegram(chat_id, SEND_FAILED, message_id)
				store.save_variations(chat_id, note, command, sent, [f"{style}, {viewpoint}" for style, viewpoint in result[2]]) # so a gallery can find them
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
		if (addressed or chat_type == 'private') and any(wants(message, botName) for wants in (wants_strict, wants_upscale, wants_palette)) and not (style or edit_message_id):
			error_to_telegram(chat_id, "That changes a picture: reply to one with it, or post a picture with it in the caption.", message_id)
		elif addressed or chat_type == 'private':
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
				technical = False
				aspect = None # a technical picture's planned shape; others are square
				drawing = None # a to-scale chart's spec: the bot draws it instead of the image model
				fallback = None # the image model's prompt for it, if the chart can't be drawn
				replan = False
				if edit_message_id:
					# a button on a technical picture: reuse the prompt and shape worked out for it, so every version agrees
					saved = (store.get(chat_id, edit_message_id) or {}).get('images', {}).values()
					planned_image = next((image for image in saved if (image.get('base') or '').startswith(openrouter.TECHNICAL_HEADER)), None)
					if planned_image:
						base, aspect, technical = planned_image['base'], planned_image.get('aspect'), True
						print("Reusing the technical picture's planned prompt")
					elif any((image.get('base') or '').startswith(chart.SAVED) for image in saved):
						replan = True # drawn by the bot: the same data would draw the same picture, so ask the planner again
				if not base:
					if len(message.split()) < MIN_PROMPT_WORDS: # only reachable from a button press
						# a button press on a very short prompt: have the text model flesh it out so it still works
						message = openrouter.expand(message, MIN_PROMPT_WORDS)
						print("Expanded short prompt:", message)
					base = message
					if not is_button or replan: # a new prompt: a diagram or schematic must get its facts right before it is drawn
						planned = openrouter.plan(message)
						print("Prompt kind:", (planned or {}).get('kind', 'unknown (used unchanged)'))
						if planned and planned['kind'] == 'technical':
							try: # the image model's prompt: the picture itself, or the fallback if a chart can't be drawn
								planned_base = openrouter.technical_prompt(message, planned)
							except Exception as e: # an answer shaped wrongly
								print("Building the technical prompt failed:", repr(e), file=stderr)
								planned_base = None
							aspect = planned.get('aspect_ratio')
							if planned.get('chart'): # already checked: the bot draws it, exactly to scale
								drawing, fallback = planned['chart'], planned_base
								base, technical = chart.SAVED + json.dumps(drawing), True
								print("To scale: drawing it as a chart:", base)
							elif planned_base:
								base, technical = planned_base, True
								print("Technical prompt", aspect or '1:1', base)
					if style_key and style_key not in VIEWPOINTS and not technical:
						# a cheap text model removes words that fight the style (a camera angle fights none)
						base = openrouter.remix(message, STYLES[style_key][1]) or message
				technical = technical or base.startswith(openrouter.TECHNICAL_HEADER) # e.g. a Remix that reused it
				print("Drawing the to-scale chart" if drawing else f"Sending prompt to OpenRouter: {model} {style_key}")
				styled = base
				if style_key and technical: # its own line, after the rules, so it can't read as one of them
					styled = base + '\nStyle: ' + STYLES[style_key][1] + '.'
				elif style_key: # then we append a short style phrase
					styled = with_style(base, style_key, fix=openrouter.fix_style)
				if style_key:
					print("Styled prompt:", styled)
				if drawing:
					try:
						success, image_url = True, chart.draw(drawing)
					except Exception as e:
						print("Drawing the chart failed:", repr(e), "- asking the image model instead" if fallback else '', file=stderr)
						drawing = None
						if fallback: # the planned picture, drawn by the image model
							base = styled = fallback
							success, image_url = openrouter.generate(styled, model, aspect)
						else:
							success, image_url = False, "Sorry, I couldn't draw that diagram."
				else:
					success, image_url = openrouter.generate(styled, model, aspect)
				if success:
					print("Sending result to Telegram")
					caption = styled # show the prompt that was actually used
					if technical: # not the long planned prompt: what was asked for (and the style)
						caption = with_style(prompt, style_key) if style_key else prompt
					# a technical picture gets just Retry ('t': the same facts, drawn again in place); style buttons would only
					# decorate what has to be correct
					keyboard = telegram.retryKeyboard(command, action='t') if technical else telegram.imageKeyboard(command, style_key)
					# Button presses replace the image in place; if that fails, post a new one instead
					sent = False
					if edit_message_id:
						pending.wait() # the 'working' edit must land first, or it could overwrite the new image
						print("Replacing message", edit_message_id, "in place;", len(image_url), "bytes" if isinstance(image_url, bytes) else "(url)")
						sent = telegram.editPhoto(chat_id, edit_message_id, image_url, caption if drawing else tag_caption(caption, command), keyboard)
						if sent:
							sent['message_id'] = edit_message_id
							pending.replaced = True
						else:
							print("In-place edit failed, posting a new image instead", file=stderr)
					if not sent and telegram.upload_timeout() >= 5: # too close to the Lambda deadline: just say it failed
						sent = telegram.sendPhoto(chat_id, image_url, caption if drawing else tag_caption(caption, command), message_id, reply_markup=keyboard)
					if not sent:
						error_to_telegram(chat_id, SEND_FAILED, message_id)
					if sent and sent['message_id'] and sent['file_id']:
						if edit_message_id and sent['message_id'] != edit_message_id:
							# the old message couldn't be edited, so this is a new one: bring its earlier images along
							store.carry_over(chat_id, edit_message_id, sent['message_id'])
						# remember the image (by Telegram file_id) so the buttons can switch back to it
						store.save_image(chat_id, sent['message_id'], prompt, command, style_key, sent['file_id'], caption, base, aspect=aspect,
							kind='chart' if drawing else None) # a chart is the bot's drawing, not the model's: a gallery can tell
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
		left = (width - crop) // 2
		upper = (height - crop) // 2
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

SEND_FAILED = "Sorry, the image was made but sending it to Telegram failed. Please try again."

def error_to_telegram(chat_id, message, message_id):
	print("Sending error to Telegram")
	telegram.sendMessage(chat_id, message, message_id)
	return
