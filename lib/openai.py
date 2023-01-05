import urllib.request, socket, json
from lib.config import *
from sys import stderr
from urllib.parse import unquote

def imagesGenerations(prompt, size='256x256', number=1):
    url = 'https://api.openai.com/v1/images/generations'
    data = {'prompt': prompt, 'size': size, 'n': number, 'response_format': 'url'}
    data = json.dumps(data).encode()
    req = urllib.request.Request(url, data=data, method='POST')
    req.add_header('Content-Type', 'application/json')
    req.add_header('Authorization', 'Bearer ' + config_openai_api_key)
    try:
        r = urllib.request.urlopen(req, timeout=20)
    except (urllib.error.HTTPError, urllib.error.URLError, socket.timeout) as e:
        error = "OpenAI error: " + str(e)
        print(error, file=stderr)
        return False, error
    success, message = processOpenaiUrl(json.load(r), r.code)
    return success, message

def imagesVariations(imagebytes, size='256x256', number=4):
    try:
        import requests
    except ModuleNotFoundError:
        error = "This feature requires the requests library to be installed"
        print(error, file=stderr)
        return False, error
    url = 'https://api.openai.com/v1/images/variations'
    headers = {'Authorization': 'Bearer ' + config_openai_api_key }
    files = {"image": imagebytes}
    data = {'size': size, 'n': number, 'response_format': 'url'}
    try:
        r = requests.post(url, headers=headers, data=data, files=files, timeout=20)
    except requests.exceptions.ConnectionError as e:
        error = "OpenAI upload error: " + str(e)
        print(error, file=stderr)
        return False, error
    success, message = processOpenaiUrl(r.json(), r.status_code)
    return success, message

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
        error_code = result['error']['code']
        error_message = result['error']['message']
        print(status_code, error_code, error_message, file=stderr)
        return False, error_message
    else:
        print(status_code, 'unknown error communicating with OpenAI')
        return False, f'{status_code} unknown error communicating with OpenAI'

