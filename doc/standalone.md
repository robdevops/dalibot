# Setup - standalone (Python WSGI server)

![Screenshot of chat with Dalibot](dali_2.png?raw=true "an impressionist oil painting of sunflowers in a purple vase")


## Clone the git repo
```
sudo $(which apt dnf yum) install git
```
```
git clone https://github.com/robdevops/dalibot.git ~/dalibot
```

## Install the Python modules
```
cd ~/dalibot
```
```
pip3 install -r requirements.txt
```

## Copy the example dalibot config
```
cp dalibot.ini.template dalibot.ini
```

## Edit dalibot.ini

### Mandatory parameters
  * Set `openai_api_key` to the [key from OpenAI](https://beta.openai.com/account/api-keys)
  * Set `telegramBotToken` to the token provided by [BotFather](https://core.telegram.org/bots/tutorial)
  * Set `telegramOutgoingToken` to a [secret token of your choice](https://core.telegram.org/bots/api#setwebhook)
  * Set `telegramOutgoingWebhook` to the URL of your Amazon API Gateway stage

Example:
```
openai_api_key = sk-p999HAfj6Cm1bO00SXgJc7kFxvFPtQ1KBBWrqSOU
telegramBotToken = 4839574812:AAFD39kkdpWt3ywyRZergyOLMaJhac60qc
telegramOutgoingToken = sLnHdQmYoohmysecret7PX5VDM4cPW
telegramOutgoingWebhook = https://www.example.com/dalibot
```

### Optional parameters
You can make stderr more verbose:
```
debug = 1
```

You can customise the bot command:
```
telegramBotCommand = dream
```

You can enable downloading of OpenAI images to disk (defaults to `dalibot/var/cache`). Note: user uploads for variations are never saved.
```
archive = 1
archive_dir = var/cache
```

You can enable private messaging by listing telegram numeric ids separated by a space:
```
telegramAllowedUserIDs = 123456789 987654321
```

You can override the listen parameters:
```
ip = 127.0.0.1
port = 5000
```

## Start the bot 
Run `bot.py` to start the listener. By default, it listens on http://127.0.0.1:5000


# Front-end webserver

## Point your web server at the bot service

Example Nginx config:
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

## ACLs
If you wish to have the above telegram ACL dynamically update:
* Remove the existing `allow` lines
* Uncomment the `include` line
* Install the cron job:
```
sudo cp -v etc/cron.daily/nginx_telegram_cron /etc/cron.daily/
```

* Run the cron to generate the initial ACL file:
```
sudo /etc/cron.daily/nginx_telegram_cron
```


# Daemonize

There is an example systemd unit file `etc/systemd/system/dalibot.service` to start dalibot in the background at boot. 
Copy it to /etc/systemd/system:
```
sudo cp -v ~/dalibot/etc/systemd/system/dalibot.service /etc/systemd/system/
```

Edit the file to set your path and user to run as:
```
sudo sed -i "s/CHANGEME/${USER}/" /etc/systemd/system/dalibot.service
```

Reload systemd:
```
sudo systemctl daemon-reload
```

Enable and start the bot:
```
sudo systemctl enable dalibot --now
```
You can now monitor the bot's stderr with:
```
journalctl -fu dalibot
```
