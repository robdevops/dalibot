# Setup - self-hosted (push)

Telegram pushes each message to a webhook URL on your own web server. This needs a domain, a TLS certificate and a front-end web server. If you don't need that, use the simpler [pull setup](self-hosted-pull.md).

Follow the [pull setup](self-hosted-pull.md) first, then make the changes below.

## Install gevent
```
cd ~/dalibot
```
```
pip3 install gevent
```

## Edit dalibot.ini
Add these to the mandatory parameters:
  * Set `telegramOutgoingToken` to a [secret token of your choice](https://core.telegram.org/bots/api#setwebhook)
  * Set `telegramOutgoingWebhook` to the public URL of your web server

```
telegramOutgoingToken = sLnHdQmYoohmysecret7PX5VDM4cPW
telegramOutgoingWebhook = https://www.example.com/dalibot
```

You can override the listen parameters:
```
ip = 127.0.0.1
port = 5000
```

## Start the bot
Run `bot.py`. It listens on http://127.0.0.1:5000 by default. To run it in the background at boot, see [Daemonize](self-hosted-pull.md#daemonize).


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
