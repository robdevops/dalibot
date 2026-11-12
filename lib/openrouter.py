import urllib.request, urllib.error, socket, json, base64, concurrent.futures, random, re
from sys import stderr
from lib.config import *
from lib.styles import STYLES

URL = 'https://openrouter.ai/api/v1/images'
CHAT_URL = 'https://openrouter.ai/api/v1/chat/completions'

REMIX_INSTRUCTIONS = (
	"You edit prompts for an AI image generator. A style phrase will be appended to the prompt afterwards. "
	"Remove only the words and phrases in the prompt that describe a conflicting style, medium or rendering, "
	"for example 'photorealistic', 'oil painting', 'cartoon', 'pixel art', '4k', or camera and lens details. "
	"Keep the subject and any words about composition or framing, such as 'close up' or 'wide angle'. "
	"Do not add anything. Do not rephrase, reorder or embellish the remaining words. "
	"If nothing conflicts, return the prompt unchanged. Reply with only the edited prompt."
)

def remix(prompt, style_cue):
	"""Have a cheap text model strip words from a prompt that fight the style that is about to be added.
	Returns the cleaned prompt, or None if anything goes wrong or the model embellishes (the caller then keeps the original)."""
	body = {
		'model': config_openrouter_text_model,
		'messages': [
			{'role': 'system', 'content': REMIX_INSTRUCTIONS},
			{'role': 'user', 'content': f"STYLE TO BE ADDED: {style_cue}\nPROMPT: {prompt}"},
		],
		'max_tokens': 200,
		'temperature': 0,
	}
	req = urllib.request.Request(CHAT_URL, data=json.dumps(body).encode(), method='POST')
	req.add_header('Content-Type', 'application/json')
	req.add_header('Authorization', 'Bearer ' + (config_openrouter_api_key or ''))
	try:
		with urllib.request.urlopen(req, timeout=20) as r:
			text = json.load(r)['choices'][0]['message']['content'].strip().strip('"').strip()
	except Exception as e:
		if isinstance(e, urllib.error.HTTPError):
			e.close()
		print("Prompt cleanup failed, using the original prompt:", repr(e), file=stderr)
		return None
	if not only_removes_few_words(prompt, text):
		print("Prompt cleanup returned an unusable edit, using the original prompt:", repr(text), file=stderr)
		return None
	return text

def words(text):
	"""Lower-case words with surrounding punctuation removed."""
	strip = '.,;:!?"\'()'
	return [w.strip(strip).lower() for w in text.split() if w.strip(strip)]

def is_subsequence(small, big):
	remaining = iter(big)
	return all(word in remaining for word in small) # each word must appear, in order

def only_removes_few_words(original, edited):
	"""True if edited is the original with some words deleted (nothing added or reordered),
	keeping at least half of the words, so the cleanup cannot gut or embellish a prompt."""
	a, b = words(original), words(edited)
	return bool(b) and len(b) * 2 >= len(a) and is_subsequence(b, a)

def only_adds_few_words(original, edited, max_added):
	"""True if edited is the original (every word, in order) plus at most max_added more words."""
	a, b = words(original), words(edited)
	return is_subsequence(a, b) and len(b) - len(a) <= max_added

FIX_INSTRUCTIONS = (
	"You fix prompts for an AI image generator. The prompt must clearly mention the style '{label}'. "
	"Rewrite it so it includes that word or a form of it (for example 'photograph' for 'Photo'), "
	"changing as little else as possible. Reply with only the fixed prompt."
)

def fix_style(prompt, label):
	"""Ask the cheap text model to work the style named by a button into a prompt that lacks it.
	Returns the fixed prompt, or None if anything goes wrong (the caller then appends the label itself)."""
	body = {
		'model': config_openrouter_text_model,
		'messages': [
			{'role': 'system', 'content': FIX_INSTRUCTIONS.format(label=label)},
			{'role': 'user', 'content': prompt},
		],
		'max_tokens': 200,
		'temperature': 0,
	}
	req = urllib.request.Request(CHAT_URL, data=json.dumps(body).encode(), method='POST')
	req.add_header('Content-Type', 'application/json')
	req.add_header('Authorization', 'Bearer ' + (config_openrouter_api_key or ''))
	try:
		with urllib.request.urlopen(req, timeout=20) as r:
			text = json.load(r)['choices'][0]['message']['content'].strip().strip('"').strip()
	except Exception as e:
		if isinstance(e, urllib.error.HTTPError):
			e.close()
		print("Style fix failed:", repr(e), file=stderr)
		return None
	# a fix may add a short phrase such as 'as a photograph', never rewrite the prompt
	return text if text and only_adds_few_words(prompt, text, 6) else None

EXPAND_INSTRUCTIONS = (
	"The prompt below is too short. Make it at least {min_words} words by adding as few words as possible: "
	"{need} word(s) is ideal. Prefer a simple adjective or qualifier next to the subject (for example 'fly' becomes 'a small fly'). "
	"Do not add a setting, lighting, composition, style or medium. Keep every original word, in order. "
	"Reply with only the new prompt."
)

def expand(prompt, min_words):
	"""Lengthen a too-short prompt by the minimum needed, so a button press can still produce an image.
	Never adds more than a word or so beyond what is required; if the model adds more, or fails, fixed filler is used instead."""
	need = max(1, min_words - len(words(prompt)))
	body = {
		'model': config_openrouter_text_model,
		'messages': [
			{'role': 'system', 'content': EXPAND_INSTRUCTIONS.format(min_words=min_words, need=need)},
			{'role': 'user', 'content': prompt},
		],
		'max_tokens': 60,
		'temperature': 0,
	}
	req = urllib.request.Request(CHAT_URL, data=json.dumps(body).encode(), method='POST')
	req.add_header('Content-Type', 'application/json')
	req.add_header('Authorization', 'Bearer ' + (config_openrouter_api_key or ''))
	try:
		with urllib.request.urlopen(req, timeout=20) as r:
			text = json.load(r)['choices'][0]['message']['content'].strip().strip('"').strip()
		if len(words(text)) >= min_words and only_adds_few_words(prompt, text, need + 1):
			return text
		print("Prompt expansion added too much or too little, using filler:", repr(text), file=stderr)
	except Exception as e:
		if isinstance(e, urllib.error.HTTPError):
			e.close()
		print("Prompt expansion failed, using filler:", repr(e), file=stderr)
	return filler(prompt, min_words)

def filler(prompt, min_words):
	"""The least we can add by hand to reach min_words: an article, then 'image'."""
	if prompt.split()[0].lower() not in ('a', 'an', 'the'):
		prompt = 'A ' + prompt
	if len(prompt.split()) < min_words:
		prompt += ' image'
	if len(prompt.split()) < min_words:
		prompt = 'An image of ' + prompt
	return prompt

def generate(prompt, model=None):
	"""Text to image. Returns (True, image_bytes) or (False, error message)."""
	return _request({'prompt': prompt}, model)

# Asking a model for "a variation" tends to return near copies. So each image is told to be redrawn in its own,
# specific style AND shown from its own viewpoint, chosen to be as different from the others as possible. The cheap
# text model invents them (it can't see the picture, but it doesn't need to); if it fails we use our own lists.
VARIATION_LOOKS_INSTRUCTIONS = (
	"You plan several different versions of one picture for an AI image generator. "
	"Reply with a JSON array of exactly {number} objects, each with a \"style\" and a \"viewpoint\". "
	"A style is 3 to 10 words that fit after 'redraw it', for example \"as a Japanese ukiyo-e woodblock print\" or "
	"\"in the style of a 1950s travel poster\". A viewpoint is 2 to 10 words that fit after 'shown', for example "
	"\"from directly above\", \"as an extreme close-up, head-on\" or \"from far away, tiny in a wide scene\". "
	"Make every style different from the others (different media, eras, techniques and colour treatments, such as a painting, "
	"a photograph, a 3D render, a graphic or pixel style) and every viewpoint different from the others. Never repeat one. "
	"Reply with only the JSON array."
)

# used when the text model can't be asked or answers badly
FALLBACK_VIEWPOINTS = [
	"from directly above", "looking up from far below", "in profile, from the side", "as an extreme close-up, head-on",
	"from far away, small in a wide scene", "from behind", "from a three-quarter front view",
]

def variation_looks(note, number):
	"""number (style, viewpoint) pairs, e.g. ('as a ukiyo-e woodblock print', 'from directly above'), each different from the
	others. Asks the cheap text model; any style or viewpoint that is missing, repeated or unusable is replaced from
	our own lists, one at a time, so a good half is never thrown away with a bad one. Never fails."""
	styles, viewpoints = [], []
	same = lambda a, b: a.casefold() == b.casefold()
	def usable(text, among):
		return 2 <= len(text.split()) <= 14 and '\n' not in text and not any(same(text, other) for other in among if other)
	try:
		text = _ask(VARIATION_LOOKS_INSTRUCTIONS.format(number=number), f"The user's note about the picture, which may be empty: {note or '(none)'}", 400, 1.0)
		found = re.search(r'\[.*\]', text, re.S)
		for item in json.loads(found.group(0) if found else text)[:number]:
			style = str(item.get('style', '') if isinstance(item, dict) else item).strip().strip('"').strip()
			viewpoint = str(item.get('viewpoint', '') if isinstance(item, dict) else '').strip().strip('"').strip()
			styles.append(style if usable(style, styles) else None)
			viewpoints.append(viewpoint if usable(viewpoint, viewpoints) else None)
	except Exception as e:
		print("Style suggestions failed, using our own lists:", repr(e), file=stderr)
	styles += [None] * (number - len(styles))
	viewpoints += [None] * (number - len(viewpoints))
	left_styles = [cue for label, cue in STYLES.values() if not any(s and same(cue, s) for s in styles)]
	left_views = [v for v in FALLBACK_VIEWPOINTS if not any(w and same(v, w) for w in viewpoints)]
	random.shuffle(left_styles)
	random.shuffle(left_views)
	for i in range(number):
		if styles[i] is None:
			styles[i] = left_styles.pop()
		if viewpoints[i] is None:
			viewpoints[i] = left_views.pop() if left_views else random.choice(FALLBACK_VIEWPOINTS)
	return list(zip(styles, viewpoints))

def variation_prompt(note, look):
	style, viewpoint = look
	prompt = f"Create a bold, clearly different variation of this image. Keep the main subject recognisable, but redraw it {style}, shown {viewpoint}. Do not simply copy or lightly retouch the original."
	return prompt + f" The user's note about what they want: {note}" if note else prompt

def variations(image_bytes, note, number=4, model=None, looks=None):
	"""Ask for variations of an image, each with its own style and viewpoint. note is what the user wrote, if anything.
	looks can be supplied (from variation_looks, possibly fetched earlier in parallel). One request per image, because many
	models cap n at 1. Returns (True, image_bytes or [image_bytes...], looks) or (False, error message), where looks lists
	the (style, viewpoint) of each image that came back, in the same order, so they can be shown to the user."""
	looks = looks or variation_looks(note, number)
	data_url = 'data:image/png;base64,' + base64.b64encode(image_bytes).decode()
	reference = [{'type': 'image_url', 'image_url': {'url': data_url}}]
	bodies = [{'prompt': variation_prompt(note, looks[i]), 'input_references': reference} for i in range(number)]
	with concurrent.futures.ThreadPoolExecutor(max_workers=number) as executor:
		results = list(executor.map(lambda body: _request(body, model), bodies))
	images = [image for ok, image in results if ok]
	if not images:
		return results[0]
	used = [look for look, (ok, image) in zip(looks, results) if ok]
	return True, images[0] if len(images) == 1 else images, used

def _ask(system, user, max_tokens, temperature):
	"""One call to the cheap text model. Returns its reply, or raises."""
	body = {'model': config_openrouter_text_model, 'messages': [{'role': 'system', 'content': system}, {'role': 'user', 'content': user}],
		'max_tokens': max_tokens, 'temperature': temperature}
	req = urllib.request.Request(CHAT_URL, data=json.dumps(body).encode(), method='POST')
	req.add_header('Content-Type', 'application/json')
	req.add_header('Authorization', 'Bearer ' + (config_openrouter_api_key or ''))
	try:
		with urllib.request.urlopen(req, timeout=20) as r:
			return json.load(r)['choices'][0]['message']['content'].strip()
	except urllib.error.HTTPError as e:
		e.close()
		raise

def _request(body, model=None):
	body = dict(body, model=model or config_openrouter_image_model, aspect_ratio='1:1')
	if debug:
		body['quality'] = 'low' # cheaper; ignored by models without a quality setting
	req = urllib.request.Request(URL, data=json.dumps(body).encode(), method='POST')
	req.add_header('Content-Type', 'application/json')
	req.add_header('Authorization', 'Bearer ' + (config_openrouter_api_key or ''))
	try:
		r = urllib.request.urlopen(req, timeout=config_image_timeout)
	except urllib.error.HTTPError as e:
		try:
			error = json.load(e)['error']['message']
		except Exception:
			error = str(e)
		e.close()
		error = f"OpenRouter error {e.code}: {error}"
		print(error, file=stderr)
		return False, error
	except (urllib.error.URLError, socket.timeout) as e:
		error = "OpenRouter connection error: " + str(e)
		print(error, file=stderr)
		return False, error
	try:
		item = json.load(r)['data'][0]
		return True, base64.b64decode(item['b64_json'])
	except (KeyError, IndexError, ValueError) as e:
		error = "Unexpected response from OpenRouter: " + repr(e)
		print(error, file=stderr)
		return False, error

KEY_URL = 'https://openrouter.ai/api/v1/key'

def spend():
	"""What OpenRouter says this API key has spent, in USD: {'today', 'week', 'month'}.
	These are OpenRouter's own daily, weekly and monthly totals. Returns (True, totals) or (False, error message)."""
	req = urllib.request.Request(KEY_URL)
	req.add_header('Authorization', 'Bearer ' + (config_openrouter_api_key or ''))
	try:
		with urllib.request.urlopen(req, timeout=config_http_timeout) as r:
			data = json.load(r)['data']
		return True, {'today': float(data['usage_daily']), 'week': float(data['usage_weekly']), 'month': float(data['usage_monthly'])}
	except urllib.error.HTTPError as e:
		e.close()
		error = f"OpenRouter error {e.code}"
	except (urllib.error.URLError, socket.timeout) as e:
		error = "OpenRouter connection error: " + str(e)
	except (KeyError, TypeError, ValueError) as e:
		error = "Unexpected response from OpenRouter: " + repr(e)
	print(error, file=stderr)
	return False, error
