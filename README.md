# dalibot
Telegram chat bot for [DALL·E 2](https://openai.com/dall-e-2/)

# Description
* Responds to a text prompt with an image
* Responds to an image with four variations

![Screenshot of chat with Dalibot](doc/dali_3.png?raw=true "close up portrait of a girl in the style of Claude Monet")

# Features
* Auto-crop non-square uploads to meet OpenAI requirements
* Optionally archive OpenAI results to local storage
* For speed and cost benefits, OpenAI images do not pass through the bot (unless you enable archiving)

# Usage
* Run `bot.py` to start the listener. By default, it listens on http://127.0.0.1:5000
* The prompt must be three or more words
* The prompt must begin with `/dream`. Alternatively, @mention the bot if it has admin access in the group.
* The bot only responds in group chats, unless you set `telegramAllowedUserIDs` in the .env file

# Requirements
* A web server with a valid domain name and certificate
* A python bot user from [BotFather](https://core.telegram.org/bots/tutorial)
* Python 3.8.10
  * dotenv
  * gevent
  * openai
  * Pillow
  * requests
* An [OpenAI API key](https://beta.openai.com/account/api-keys)

![Screenshot of chat with Dalibot](doc/dali_2.png?raw=true "an impressionist oil painting of sunflowers in a purple vase")

# Setup
* Clone the git repo
```
git clone https://github.com/robdevops/dalibot.git ~/dalibot
```
* Install the Python modules
```
pip3 install dotenv gevent openai Pillow requests
```
* Point your web server at the listener. Example Nginx config:
```
server {
	listen 8443 ssl;
	deny all;

	server_name         www.example.com;
	ssl_certificate     /etc/letsencrypt/live/www.example.com/fullchain.pem;
	ssl_certificate_key /etc/letsencrypt/live/www.example.com/privkey.pem;
	ssl_protocols       TLSv1 TLSv1.1 TLSv1.2;
	ssl_ciphers         HIGH:!aNULL:!MD5;

	location /telegram {
		proxy_pass http://127.0.0.1:5000/telegram;
		allow 91.108.4.0/22
		deny all;
	}
}
```
* Copy and edit the example config
```
cp env.template .env
```
![Screenshot of chat with Dalibot](doc/dali_4.png?raw=true "girl with a pearl earring by Johannes Vermeer in the style of 8-bit pixel art")

# Config
Config is via the .env file.

Mandatory parameters:
* Set `openai_api_key` to the [key from OpenAI](https://beta.openai.com/account/api-keys)
* Set `telegramOutgoingToken` to a [secret token of your choice](https://core.telegram.org/bots/api#setwebhook)
* Set `telegramOutgoingWebhook` to the URL of your web server
* Set `telegramBotToken` to the token provided by [BotFather](https://core.telegram.org/bots/tutorial)

Example:
```
openai_api_key = sk-mykey
telegramBotToken = 0000000000:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
telegramOutgoingToken = mysecret
telegramOutgoingWebhook = https://www.example.com/telegram
```

Optional parameters:
```
debug = 1
openai_organization = org-myorg
```

Enable archiving to download OpenAI images to disk (defaults to `dalibot/var/cache`). Note: user uploads for variations always traverse the bot but are never saved.
```
archive = 1
archive_dir = var/cache
```

Enable private messaging by listing telegram numeric ids separated by a space:
```
telegramAllowedUserIDs =
```

Override listen parameters:
```
ip = 127.0.0.1
port = 5000
```

![Screenshot of chat with Dalibot](doc/dali_1.png?raw=true "a painting of a fox sitting in a field at sunrise in the style of Claude Monet")

# Daemonize

There is an example systemd unit file `etc/systemd/system/dalibot.service` to start dalibot in the background at boot. Copy it to /etc
```
sudo cp -v ~/dalibot/etc/systemd/system/dalibot.service /etc/systemd/system/
```

Edit the file to set your path and user to run as:
```
sudo sed -i 's/CHANGEME/your username/' /etc/systemd/system/dalibot.service
```

Reload systemd:
```
sudo systemctl daemon-reload
```

Enable and start the bot:
```
sudo systemctl enable dalibot --now
```

