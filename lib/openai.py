import urllib.request, urllib.error, socket, json, base64
import lib.multipart as multipart
from lib.config import *
from sys import stderr
from urllib.parse import unquote

def imagesGenerations(prompt, size='1024x1024', number=1):
	url = 'https://api.openai.com/v1/images/generations'
	data = {'model': config_openai_image_model, 'prompt': prompt, 'size': size, 'n': number}
	data = json.dumps(data).encode()
	req = urllib.request.Request(url, data=data, method='POST')
	req.add_header('Content-Type', 'application/json')
	req.add_header('Authorization', 'Bearer ' + config_openai_api_key)
	try:
		r = urllib.request.urlopen(req, timeout=20)
	except (urllib.error.HTTPError, urllib.error.URLError, socket.timeout) as e:
		try:
			errorjson = json.load(e)
		except:
			error = "OpenAI error " + e.code + ": " + str(e)
			print(error, file=stderr)
			return False, error
		else:
			success, message = processOpenaiUrl(errorjson, e.code)
	else:
		success, message = processOpenaiUrl(json.load(r), r.code)
	return success, message

def imagesVariations(imagebytes, size='256x256', number=1):
	url = 'https://api.openai.com/v1/images/variations'
	content_type, body = multipart.encode({'size': size, 'n': number}, {'image': ('image.png', 'image/png', imagebytes)})
	req = urllib.request.Request(url, data=body, method='POST')
	req.add_header('Content-Type', content_type)
	req.add_header('Authorization', 'Bearer ' + config_openai_api_key)
	try:
		r = urllib.request.urlopen(req, timeout=20)
	except urllib.error.HTTPError as e:
		try:
			errorjson = json.load(e)
		except Exception:
			error = "OpenAI error " + str(e.code) + ": " + str(e)
			print(error, file=stderr)
			return False, error
		return processOpenaiUrl(errorjson, e.code)
	except (urllib.error.URLError, socket.timeout) as e:
		error = "OpenAI connection error: " + str(e)
		print(error, file=stderr)
		return False, error
	return processOpenaiUrl(json.load(r), r.status)

def processOpenaiUrl(result, status_code):
	if 'data' in result:
		# Older models return a URL; GPT image models always return base64 (bytes)
		images = [item['url'] if 'url' in item else base64.b64decode(item['b64_json']) for item in result['data']]
		return True, images[0] if len(images) == 1 else images
	elif 'error' in result:
		error_message = result['error']['message']
		print(status_code, "OpenAI", error_message, file=stderr)
		return False, error_message
	else:
		print(status_code, 'OpenAI unknown error')
		return False, f'{status_code} unknown error communicating with OpenAI'

