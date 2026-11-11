import urllib.request, urllib.error, socket, json, uuid
from lib.config import *
from sys import stderr
from urllib.parse import unquote

def imagesGenerations(prompt, size='1024x1024', number=1):
	url = 'https://api.openai.com/v1/images/generations'
	data = {'model': 'dall-e-3', 'prompt': prompt, 'size': size, 'n': number, 'response_format': 'url'}
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
	boundary = uuid.uuid4().hex
	fields = {'size': size, 'n': number, 'response_format': 'url'}
	body = b''
	for name, value in fields.items():
		body += f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode()
	body += f'--{boundary}\r\nContent-Disposition: form-data; name="image"; filename="image.png"\r\nContent-Type: image/png\r\n\r\n'.encode()
	body += imagebytes + f'\r\n--{boundary}--\r\n'.encode()
	req = urllib.request.Request(url, data=body, method='POST')
	req.add_header('Content-Type', 'multipart/form-data; boundary=' + boundary)
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
		if len(result['data']) == 1:
			image_url = result['data'][0]['url']
		else:
			image_url = []
			for item in result['data']:
				#image_url.append(unquote(item['url']))
				image_url.append(item['url'])
		return True, image_url
	elif 'error' in result:
		error_message = result['error']['message']
		print(status_code, "OpenAI", error_message, file=stderr)
		return False, error_message
	else:
		print(status_code, 'OpenAI unknown error')
		return False, f'{status_code} unknown error communicating with OpenAI'

