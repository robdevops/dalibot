import urllib.request, urllib.error, http.client, socket, json, base64, concurrent.futures, random, re
from sys import stderr
from lib.config import *
import lib.deadline as deadline
from lib.styles import STYLES, VIEWPOINTS

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
		with urllib.request.urlopen(req, timeout=deadline.limit(20)) as r:
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
		with urllib.request.urlopen(req, timeout=deadline.limit(20)) as r:
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
		with urllib.request.urlopen(req, timeout=deadline.limit(20)) as r:
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

def generate(prompt, model=None, aspect_ratio=None):
	"""Text to image, square unless aspect_ratio (one of RATIOS) says otherwise. Returns (True, image_bytes) or (False, error message)."""
	return _request({'prompt': prompt}, model, aspect_ratio)

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
	left_styles = [cue for key, (label, cue) in STYLES.items() if key not in VIEWPOINTS and not any(s and same(cue, s) for s in styles)]
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

# Image models redraw rather than enlarge, so this asks for the closest thing to an enlargement they can do.
UPSCALE_PROMPT = (
	"Reproduce this exact image at high resolution. Keep the composition, the subject, every object, the colours, the lighting "
	"and the art style exactly as they are. Only sharpen it and add fine detail and texture where the original is blurry, blocky "
	"or noisy. Do not add, remove, move, crop or restyle anything."
)

# For #strict: one image that does what the user asked to their picture, and nothing more.
STRICT_PROMPT = (
	"Change this image exactly as the following instructions say, and do nothing else: {note}\n"
	"Keep everything the instructions do not ask to change as it is: the subject, the composition, the colours, the lighting "
	"and the art style."
)

def strict(image_bytes, note, model=None):
	"""One image: the user's picture changed as their note says, without the styles and viewpoints variations add.
	Returns (True, image_bytes) or (False, error message)."""
	data_url = 'data:image/png;base64,' + base64.b64encode(image_bytes).decode()
	return _request({'prompt': STRICT_PROMPT.format(note=note), 'input_references': [{'type': 'image_url', 'image_url': {'url': data_url}}]}, model)

def upscale(image_bytes, model=None):
	"""Redraw a small or soft image as faithfully as the model can, at the model's full size.
	Returns (True, image_bytes) or (False, error message)."""
	data_url = 'data:image/png;base64,' + base64.b64encode(image_bytes).decode()
	return _request({'prompt': UPSCALE_PROMPT, 'input_references': [{'type': 'image_url', 'image_url': {'url': data_url}}]}, model)

# A technical picture (a diagram, cutaway, schematic...) has to be right. As in signalbot, a capable model writes the
# whole prompt for it (layout, every label and arrow, how they connect), picks its shape, and lists the facts it must
# get right as requirements; the bot then wraps that in a brief that puts accuracy first, and rules for its text.
# An artistic prompt is drawn as the user wrote it.
RATIOS = ['1:1', '3:2', '2:3', '16:9', '9:16', '4:3', '3:4']
MAX_REQUIREMENTS = 12
PLAN_INSTRUCTIONS = (
	"You prepare a picture for an AI image generator, which sees only the prompt you write. Set kind to technical for a "
	"picture that explains or teaches: a diagram, cutaway, cross-section, schematic, infographic, labelled or how-it-works "
	"illustration; artistic for anything else, such as art, a scene, a portrait, a logo or a meme. For artistic, give only "
	"the kind. For technical, first work out the facts yourself, as an expert would check them, then list each one the "
	"picture must get right in requirements: what every label says and exactly what it points to, which way each arrow "
	"points and what it means, angles, counts, order, what is perpendicular, parallel, above or inside what, and any "
	"quantities with their numbers and units (worked out, and for something to scale, the proportions that must hold). "
	"Then write the prompt in full: the subject, the layout and composition, the style if one was asked for, and every "
	"box, label and arrow, with how they connect and the exact text of each. Keep labels few and short. Choose the "
	"aspect_ratio that suits the layout: 1:1 unless it suits wide (16:9, 3:2, 4:3) or tall (9:16, 2:3, 3:4). "
	"Call plan_picture once."
)
PLAN_TOOL = {'type': 'function', 'function': {'name': 'plan_picture', 'description': 'Say what kind of picture this is and, for a technical one, write its prompt and what it must get right.',
	'parameters': {'type': 'object', 'required': ['kind'], 'properties': {
		'kind': {'type': 'string', 'enum': ['technical', 'artistic'], 'description': 'technical for a diagram, cutaway, infographic or other picture that explains; artistic for anything else.'},
		'prompt': {'type': 'string', 'description': 'Technical only: the full description of the picture for the image model.'},
		'aspect_ratio': {'type': 'string', 'enum': RATIOS, 'description': "Technical only: the picture's shape."},
		'requirements': {'type': 'array', 'maxItems': MAX_REQUIREMENTS, 'items': {'type': 'string'}, 'description': 'Technical only: each fact the picture must get exactly right, one per item.'},
	}}}}
# The second, narrower request when the first sorted a prompt as technical but wrote nothing for it.
FACTS_INSTRUCTIONS = PLAN_INSTRUCTIONS.replace("Set kind to technical for", "The user wants a technical picture:").replace("Call plan_picture once.", "Call write_picture once.")
FACTS_TOOL = {'type': 'function', 'function': {'name': 'write_picture', 'description': 'Write the technical picture\'s prompt and what it must get right.',
	'parameters': {'type': 'object', 'required': ['prompt', 'requirements'], 'properties': {
		'prompt': PLAN_TOOL['function']['parameters']['properties']['prompt'],
		'aspect_ratio': PLAN_TOOL['function']['parameters']['properties']['aspect_ratio'],
		'requirements': dict(PLAN_TOOL['function']['parameters']['properties']['requirements'], minItems=1),
	}}}}
# image models favour looks over accuracy unless told otherwise (signalbot's brief and rules, word for word)
TECHNICAL_BRIEF = ("A picture that teaches, so it must be accurate: draw exactly what is described, and nothing that contradicts it. "
	"Keep any style the description asks for, but never at the cost of accuracy; if it names none, use a clean, uncluttered layout "
	"with room around each part, consistent line weights and high contrast. "
	"Draw each thing once; things too close to tell apart at the picture's scale share one mark and one label, with an inset if they must be shown apart.")
TEXT_RULES = ("Text: only the words given above (labels, any title or caption), spelled exactly, each short, large and legible, "
	"a label placed next to what it names with a leader line if needed, and each label exactly once. No other text, no placeholder text, no invented numbers or values. "
	"Every arrow points exactly as described.")
TECHNICAL_HEADER = TECHNICAL_BRIEF[:40] # every prompt built for a technical picture starts with this, so a saved one can be recognised
MAX_PROMPT = 4000
MAX_REQUIREMENT = 300

def _tool_call(instructions, prompt, tool):
	"""One call to the planning model that has to answer through tool. Returns the tool's arguments (a dict), or raises."""
	body = {'model': config_openrouter_plan_model, 'messages': [{'role': 'system', 'content': instructions}, {'role': 'user', 'content': prompt}],
		'tools': [tool], 'tool_choice': {'type': 'function', 'function': {'name': tool['function']['name']}}, 'max_tokens': 3000, 'temperature': 0.2}
	req = urllib.request.Request(CHAT_URL, data=json.dumps(body).encode(), method='POST')
	req.add_header('Content-Type', 'application/json')
	req.add_header('Authorization', 'Bearer ' + (config_openrouter_api_key or ''))
	with urllib.request.urlopen(req, timeout=deadline.limit(40)) as r: # a full prompt takes a capable model a little while
		message = json.load(r)['choices'][0]['message']
	calls = message.get('tool_calls') or []
	if calls:
		return json.loads(calls[0]['function']['arguments'])
	found = re.search(r'\{.*\}', message.get('content') or '', re.S) # a model that answered in text instead
	return json.loads(found.group(0)) if found else {}

def _tidy(answer):
	"""The planned picture's fields as they can be used: a prompt string, a known aspect ratio, a list of requirements."""
	answer['prompt'] = str(answer.get('prompt') or '').strip()[:MAX_PROMPT]
	if answer.get('aspect_ratio') not in RATIOS:
		answer['aspect_ratio'] = None
	requirements = answer.get('requirements') if isinstance(answer.get('requirements'), list) else []
	answer['requirements'] = [str(r).strip()[:MAX_REQUIREMENT] for r in requirements if str(r or '').strip()][:MAX_REQUIREMENTS]
	return answer

def plan(prompt):
	"""Sort a new prompt into 'technical' or 'artistic' with the planning model and, for a technical one, get its full
	prompt, aspect ratio and requirements: {'kind', 'prompt', 'aspect_ratio', 'requirements'}. A technical answer with
	nothing written is asked once more; it stays technical either way. Returns None if it can't tell (the prompt is then
	used unchanged, as for an artistic one)."""
	try:
		answer = _tool_call(PLAN_INSTRUCTIONS, prompt, PLAN_TOOL)
	except Exception as e:
		print("Prompt planning failed, using the prompt unchanged:", repr(e), file=stderr)
		return None
	if not isinstance(answer, dict) or answer.get('kind') not in ('technical', 'artistic'):
		print("Prompt planning gave no usable answer, using the prompt unchanged:", str(answer)[:200], file=stderr)
		return None
	_tidy(answer)
	if answer['kind'] == 'technical' and not (answer['prompt'] and answer['requirements']):
		print("Prompt planning sorted it as technical but wrote too little; asking for the prompt and requirements", file=stderr)
		try:
			more = _tool_call(FACTS_INSTRUCTIONS, prompt, FACTS_TOOL)
			if isinstance(more, dict):
				_tidy(more)
				answer.update({name: more[name] for name in ('prompt', 'aspect_ratio', 'requirements') if more.get(name)})
		except Exception as e:
			print("Asking again failed; drawing it as technical with what there is:", repr(e), file=stderr)
	return answer

def technical_prompt(prompt, planned):
	"""The prompt the image model sees for a technical picture: the brief that puts accuracy first, the planned prompt
	(or the user's own, if none was written), the requirements as must-haves, then the rules for its text."""
	lines = [TECHNICAL_BRIEF, '', planned.get('prompt') or prompt, '']
	requirements = planned.get('requirements') or []
	if requirements:
		lines.append("It must get these exactly right:")
		lines += ['- ' + requirement for requirement in requirements]
		lines.append('')
	lines.append(TEXT_RULES)
	return '\n'.join(lines)

def _ask(system, user, max_tokens, temperature):
	"""One call to the cheap text model. Returns its reply, or raises."""
	body = {'model': config_openrouter_text_model, 'messages': [{'role': 'system', 'content': system}, {'role': 'user', 'content': user}],
		'max_tokens': max_tokens, 'temperature': temperature}
	req = urllib.request.Request(CHAT_URL, data=json.dumps(body).encode(), method='POST')
	req.add_header('Content-Type', 'application/json')
	req.add_header('Authorization', 'Bearer ' + (config_openrouter_api_key or ''))
	try:
		with urllib.request.urlopen(req, timeout=deadline.limit(20)) as r:
			return json.load(r)['choices'][0]['message']['content'].strip()
	except urllib.error.HTTPError as e:
		e.close()
		raise

def _request(body, model=None, aspect_ratio=None):
	body = dict(body, model=model or config_openrouter_image_model, aspect_ratio=aspect_ratio if aspect_ratio in RATIOS else '1:1')
	if config_image_quality:
		body['quality'] = config_image_quality # ignored by models without a quality setting
	if debug:
		body['quality'] = 'low' # cheaper
	req = urllib.request.Request(URL, data=json.dumps(body).encode(), method='POST')
	req.add_header('Content-Type', 'application/json')
	req.add_header('Authorization', 'Bearer ' + (config_openrouter_api_key or ''))
	try:
		r = urllib.request.urlopen(req, timeout=deadline.limit(config_image_timeout))
	except urllib.error.HTTPError as e:
		try:
			error = json.load(e)['error']['message']
		except Exception:
			error = str(e)
		e.close()
		error = f"OpenRouter error {e.code}: {error}"
		print(error, file=stderr)
		return False, error
	except (urllib.error.URLError, OSError) as e:
		error = connection_error(e)
		print(error, file=stderr)
		return False, error
	try:
		item = json.load(r)['data'][0]
		return True, base64.b64decode(item['b64_json'])
	except (KeyError, IndexError, ValueError) as e:
		error = "Unexpected response from OpenRouter: " + repr(e)
		print(error, file=stderr)
		return False, error
	except (OSError, http.client.HTTPException) as e: # e.g. a timeout while reading the picture
		error = connection_error(e)
		print(error, file=stderr)
		return False, error
	finally:
		r.close()

def connection_error(e):
	"""A message for the user about a network problem; a timeout gets plain wording."""
	if isinstance(e, TimeoutError) or isinstance(getattr(e, 'reason', None), TimeoutError) or 'timed out' in str(e):
		return "OpenRouter took too long to make the image. Please try again."
	return "OpenRouter connection error: " + str(e)

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
