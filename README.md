# dalibot
Telegram chat bot for [DALL·E 2](https://openai.com/dall-e-2/)

# Description
* Responds to a text prompt with an image
* Responds to an image with four variations

![Screenshot of chat with Dalibot](doc/dali_1.png?raw=true "close up portrait of a girl in the style of Claude Monet")

# Features
* Auto convert, crop, and resize uploaded images to meet OpenAI requirements
* Optionally archive OpenAI results to local storage
* For speed and cost benefits, OpenAI image data does not pass through the bot. Only the URL does (unless you enable archiving)

# Requirements
* A web server with a valid domain name and certificate
* A Telegram bot token from [BotFather](https://core.telegram.org/bots/tutorial)
* An [OpenAI API key](https://beta.openai.com/account/api-keys)
* Python 3.8.10+
  * gevent
  * pillow (only if using the image variations feature)
  * requests

# Usage
* Run `bot.py` to start the listener. By default, it listens on http://127.0.0.1:5000
* The prompt must be three or more words
* The prompt must begin with `/dream`. Alternatively, @mention the bot if it has admin access in the group.
* The bot only responds in group chats, unless you set `telegramAllowedUserIDs` in dalibot.ini

![Screenshot of chat with Dalibot](doc/dali_2.png?raw=true "an impressionist oil painting of sunflowers in a purple vase")

# Setup
* Clone the git repo
```
sudo $(which apt dnf yum) install git
```
```
git clone https://github.com/robdevops/dalibot.git ~/dalibot
```
* Install the Python modules
```
cd ~/dalibot
```
```
pip3 install -r requirements.txt
```
* Point your web server at the listener. Example Nginx config:
```
server {
    listen 8443 ssl;
    server_name         www.example.com;
    ssl_certificate     /etc/letsencrypt/live/www.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/www.example.com/privkey.pem;
    ssl_protocols       TLSv1 TLSv1.1 TLSv1.2;
    ssl_ciphers         HIGH:!aNULL:!MD5;

    location /telegram {
        proxy_pass http://127.0.0.1:5000/telegram;
        allow 91.108.4.0/22;
        allow 91.108.56.0/24;
        allow 149.154.160.0/22;
        allow 149.154.164.0/22;
        allow 149.154.172.0/22;
        #include /etc/nginx/telegram_subnets;
        deny all;
    }
}
```
If you wish to have the above telegram ACL dynamically update, you can uncomment the `include` line, and run `sudo etc/cron.daily/nginx_telegram_cron` once, or install it as a cron job with `sudo cp -v etc/cron.daily/nginx_telegram_cron /etc/cron.daily/`

* If running on AWS Lambda behind AWS API Gateway, the following mapping template should go under _POST - Integration Request > Mapping Templates > application/json_. This is required to route incoming requests to the appropriate chat network, and to authenticate Telegram's `X-Telegram-Bot-Api-Secret-Token` header against your configured `telegramOutgoingToken` value.
```
{
    "method": "$context.httpMethod",
    "path": "$context.path",
    "body" : $input.json('$'),
    "headers": {
        #foreach($param in $input.params().header.keySet())
            "$param": "$util.escapeJavaScript($input.params().header.get($param))" #if($foreach.hasNext),#end
        #end
    }
}
```

* Copy and edit the example config
```
cp dalibot.ini.template dalibot.ini
```
![Screenshot of chat with Dalibot](doc/dali_3.png?raw=true "girl with a pearl earring by Johannes Vermeer in the style of 8-bit pixel art")

# Config
Config is via dalibot.ini

Mandatory parameters:
* Set `openai_api_key` to the [key from OpenAI](https://beta.openai.com/account/api-keys)
* Set `telegramOutgoingToken` to a [secret token of your choice](https://core.telegram.org/bots/api#setwebhook)
* Set `telegramOutgoingWebhook` to the URL of your web server
* Set `telegramBotToken` to the token provided by [BotFather](https://core.telegram.org/bots/tutorial)

Example:
```
openai_api_key = sk-p999HAfj6Cm1bO00SXgJc7kFxvFPtQ1KBBWrqSOU
telegramBotToken = 4839574812:AAFD39kkdpWt3ywyRZergyOLMaJhac60qc
telegramOutgoingToken = sLnHdQmYoohmysecret7PX5VDM4cPW
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

![Screenshot of chat with Dalibot](doc/dali_4.png?raw=true "cute watermelon smiling")

# Daemonize

There is an example systemd unit file `etc/systemd/system/dalibot.service` to start dalibot in the background at boot. 
Copy it to /etc/systemd/system:
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
You can now monitor the bot's stderr with :
```
journalctl -fu dalibot
```

# Security
* Protect your API keys and bot tokens from other users on the system:
```
chmod 600 dalibot.ini
```
* Because Telegram bots are discoverable by anyone, the bot ignores private messages by default. You can whitelist users in dalibot.ini. User IDs can be obtained from the URL bar when messaging a user on https://web.telegram.org/, or from the bots console output when someone messages it. Example config:
```
telegramAllowedUserIDs = 123456789 987654321
```
* To prevent unauthorized use, it's recommended to message `/setjoingroups` to BotFather and set it to `Disabled` after you have added your bot to any desired groups.
* Only allow connections from Telegram's subnets as per the example Nginx config.
* Set `telegramOutgoingToken` to a strong value to prevent another bot being used to access your URL.

![Screenshot of chat with Dalibot](doc/dali_5.png?raw=true "a painting of a fox sitting in a field at sunrise in the style of Claude Monet")
