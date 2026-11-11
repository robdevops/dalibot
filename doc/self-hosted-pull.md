# Setup - self-hosted (pull)

The bot connects out to Telegram and fetches messages (long polling). You need no domain, certificate or web server. To have Telegram push messages to you instead, see [push setup](self-hosted-push.md).

![Screenshot of chat with Dalibot](dali_2.png?raw=true "an impressionist oil painting of sunflowers in a purple vase")


## Clone the git repo
Install git with your package manager, if you don't already have it:

| System | Command |
| --- | --- |
| Arch Linux | `sudo pacman -S git` |
| Debian, Ubuntu | `sudo apt install git` |
| DragonFly BSD, FreeBSD | `sudo pkg install git` |
| Fedora, RHEL | `sudo dnf install git` |
| macOS (Homebrew) | `brew install git` |
| macOS (MacPorts) | `sudo port install git` |
| NetBSD | `sudo pkgin install git` |
| OpenBSD | `doas pkg_add git` |
| Windows | `winget install Git.Git` |

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
cp dalibot.env.template dalibot.env
```
```
chmod 600 dalibot.env
```

## Edit dalibot.env
Settings are environment variables, one `NAME=value` per line.

### Mandatory parameters
  * Set `OPENAI_API_KEY` to the [key from OpenAI](https://beta.openai.com/account/api-keys)
  * Set `TELEGRAM_BOT_TOKEN` to the token provided by [BotFather](https://core.telegram.org/bots/tutorial)

Example:
```
OPENAI_API_KEY=sk-p999HAfj6Cm1bO00SXgJc7kFxvFPtQ1KBBWrqSOU
TELEGRAM_BOT_TOKEN=4839574812:AAFD39kkdpWt3ywyRZergyOLMaJhac60qc
```

### Optional parameters
You can make stderr more verbose:
```
DALIBOT_DEBUG=1
```

You can choose the OpenAI image model (defaults to `gpt-image-1.5`). Use any GPT image model your account can access:
```
OPENAI_IMAGE_MODEL=gpt-image-1.5
```

You can customise the bot command:
```
TELEGRAM_BOT_COMMAND=dream
```

You can enable downloading of OpenAI images to disk (defaults to `dalibot/var/cache`). Note: user uploads for variations are never saved.
```
DALIBOT_ARCHIVE=1
DALIBOT_ARCHIVE_DIR=var/cache
```

You can enable private messaging by listing telegram numeric ids separated by a space:
```
TELEGRAM_ALLOWED_USER_IDS="123456789 987654321"
```

## Start the bot
Load the config into the environment and run `bot.py`. It starts polling Telegram.
```
cd ~/dalibot
```
```
set -a; . ./dalibot.env; set +a
```
```
./bot.py
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

The unit loads `~/dalibot/dalibot.env` for you via `EnvironmentFile`.

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
