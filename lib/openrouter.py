import urllib.request, urllib.error, socket, json, base64, concurrent.futures
from sys import stderr
from lib.config import *

URL = 'https://openrouter.ai/api/v1/images'

def generate(prompt):
	"""Text to image. Returns (True, image_bytes) or (False, error message)."""
	return _request({'prompt': prompt})

def variations(image_bytes, prompt, number=4):
	"""Ask for variations of an image. One request per image, because many models cap n at 1.
	Returns (True, image_bytes or [image_bytes...]) or (False, error message)."""
	data_url = 'data:image/png;base64,' + base64.b64encode(image_bytes).decode()
	body = {'prompt': prompt, 'input_references': [{'type': 'image_url', 'image_url': {'url': data_url}}]}
	with concurrent.futures.ThreadPoolExecutor(max_workers=number) as executor:
		results = list(executor.map(lambda _: _request(body), range(number)))
	images = [image for ok, image in results if ok]
	if not images:
		return results[0]
	return True, images[0] if len(images) == 1 else images

def _request(body):
	body = dict(body, model=config_openrouter_image_model, aspect_ratio='1:1')
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
