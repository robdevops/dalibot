import urllib.request, urllib.error, socket, json, base64, concurrent.futures
from sys import stderr
from lib.config import *

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

def only_removes_few_words(original, edited):
	"""True if edited is the original with some words deleted (nothing added or reordered),
	keeping at least half of the words, so the cleanup cannot gut or embellish a prompt."""
	words = lambda s: [w.strip('.,;:!?"\'()').lower() for w in s.split() if w.strip('.,;:!?"\'()')]
	a, b = words(original), words(edited)
	if not b or len(b) * 2 < len(a):
		return False
	remaining = iter(a)
	return all(word in remaining for word in b) # each edited word must appear in order in the original

def generate(prompt, model=None):
	"""Text to image. Returns (True, image_bytes) or (False, error message)."""
	return _request({'prompt': prompt}, model)

def variations(image_bytes, prompt, number=4, model=None):
	"""Ask for variations of an image. One request per image, because many models cap n at 1.
	Returns (True, image_bytes or [image_bytes...]) or (False, error message)."""
	data_url = 'data:image/png;base64,' + base64.b64encode(image_bytes).decode()
	body = {'prompt': prompt, 'input_references': [{'type': 'image_url', 'image_url': {'url': data_url}}]}
	with concurrent.futures.ThreadPoolExecutor(max_workers=number) as executor:
		results = list(executor.map(lambda _: _request(body, model), range(number)))
	images = [image for ok, image in results if ok]
	if not images:
		return results[0]
	return True, images[0] if len(images) == 1 else images

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
