import requests
from lib.config import *
from sys import stderr
import json
from urllib.parse import unquote

def imagesGenerations(prompt, size='256x256', number=1):
    url = 'https://api.openai.com/v1/images/generations'
    headers = {'Content-type': 'application/json', 'Authorization': 'Bearer ' + config_openai_api_key}
    payload = {'prompt': prompt, 'size': size, 'n': number, 'response_format': 'url'}
    try:
        r = requests.post(url, headers=headers, json=payload, timeout=config_http_timeout)
    except requests.exceptions.ConnectionError as e:
        print("OpenAI:", e, file=stderr)
        return False, e
    success, message = processOpenaiUrl(r.json())
    return success, message

def imagesVariations(imagebytes, size='256x256', number=4):
    url = 'https://api.openai.com/v1/images/variations'
    headers = {'Authorization': 'Bearer ' + config_openai_api_key }
    files = {"image": imagebytes}
    #files = { "image": ("image_1671453832.png", open("image_1671453832.png", "rb")) }
    data = {'size': size, 'n': number, 'response_format': 'url'}
    try:
        r = requests.post(url, headers=headers, data=data, files=files, timeout=30)
    except requests.exceptions.ConnectionError as e:
        print("OpenAI:", e, file=stderr)
        return False, e
    success, message = processOpenaiUrl(r.json())
    return success, message

def processOpenaiUrl(result):
    if 'data' in result:
        if len(result['data']) == 1:
            image_url = result['data'][0]['url']
        elif len(result['data']) > 1:
            image_url = []
            for item in result['data']:
                #image_url.append(unquote(item['url']))
                image_url.append(item['url'])
    elif 'error' in result:
        error_code = result['error']['code']
        error_message = result['error']['message']
        print(r.status_code, error_code, error_message, file=stderr)
        return False, error_message
    else:
        print(r.status_code, 'unknown error communicating with OpenAI')
        return False, f'{r.status_code} unknown error communicating with OpenAI'
    return True, image_url

