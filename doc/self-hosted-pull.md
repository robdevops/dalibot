# Setup - self-hosted (pull)

The bot connects out to Telegram and fetches messages (long polling). You need no domain, certificate or web server. To have Telegram push messages to you instead, see [push setup](self-hosted-push.md).

![Screenshot of chat with Dalibot](dali_2.png?raw=true "an impressionist oil painting of sunflowers in a purple vase")


## Clone the git repo
Install git with your package manager, if you don't already have it:

| System | Command |
| --- | --- |
| Debian, Ubuntu | `sudo apt install git` |
| Fedora, RHEL | `sudo dnf install git` |
| Arch Linux | `sudo pacman -S git` |
| macOS (Homebrew) | `brew install git` |
| macOS (MacPorts) | `sudo port install git` |

```
git clone https://github.com/robdevops/dalibot.git ~/dalibot
```

## Install the Python modules (optional)
Text prompts and image generation need no extra modules. Only install Pillow, for image variations:
```
cd ~/dalibot
```
```
pip3 install Pillow
```

## Copy the example dalibot config
```
cp dalibot.ini.template dalibot.ini
```

## Edit dalibot.ini

### Mandatory parameters
  * Set `openai_api_key` to the [key from OpenAI](https://beta.openai.com/account/api-keys)
  * Set `telegramBotToken` to the token provided by [BotFather](https://core.telegram.org/bots/tutorial)

Example:
```
openai_api_key = sk-p999HAfj6Cm1bO00SXgJc7kFxvFPtQ1KBBWrqSOU
telegramBotToken = 4839574812:AAFD39kkdpWt3ywyRZergyOLMaJhac60qc
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

## Start the bot
Run `bot.py`. It starts polling Telegram.


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
