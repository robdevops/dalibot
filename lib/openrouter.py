import urllib.request, urllib.error, socket, json, base64, concurrent.futures
from sys import stderr
from lib.config import *

URL = 'https://openrouter.ai/api/v1/images'
CHAT_URL = 'https://openrouter.ai/api/v1/chat/completions'

REMIX_INSTRUCTIONS = (
	"You rewrite prompts for an AI image generator. You get an ORIGINAL prompt and a TARGET STYLE. "
	"Rewrite the prompt so it depicts the same subject, scene and details, but in the target style. "
	"Remove or replace any wording in the original that conflicts with the target style, such as photographic or realism terms, "
	"camera and lens details, other art styles or mediums, and resolution keywords like 4k. "
	"Write one paragraph of under 70 words that ends with the style cues. "
	"Reply with only the rewritten prompt, with no quotes or commentary."
)

def remix(prompt, style_label, style_cues):
	"""Have a cheap text model rewrite a prompt for a style, dropping conflicting terms.
	Returns the new prompt, or None if anything goes wrong (the caller then falls back to appending the style)."""
	body = {
		'model': config_openrouter_text_model,
		'messages': [
			{'role': 'system', 'content': REMIX_INSTRUCTIONS},
			{'role': 'user', 'content': f"ORIGINAL: {prompt}\nTARGET STYLE: {style_label}: {style_cues}"},
		],
		'max_tokens': 200,
		'temperature': 0.7,
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
		print("Prompt remix failed, using the plain prompt:", repr(e), file=stderr)
		return None
	return text[:900] or None

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
