# dalibot
Telegram chat bot for AI image generation, powered by [OpenRouter](https://openrouter.ai/) (choose from dozens of image models)

# Description
* Responds to a text prompt with an image
* Responds to an image with four variations

![Screenshot of chat with Dalibot](doc/dali_1.png?raw=true "close up portrait of a girl in the style of Claude Monet")

# Features
* Auto convert, crop, and resize uploaded images to meet image model requirements
* Optionally archive results to local storage
* Runs self-hosted or serverless
* Minimal dependencies outside the Python Standard Library. There are none if you run it serverless and only use the text prompt feature.

# Usage
* The prompt must be three or more words
* The prompt must begin with a command, or @mention the bot if it has admin access in the group. Each command uses a different model:

| Command | Model | Notes |
| --- | --- | --- |
| `/dream` | `openai/gpt-image-2` by default | Set `OPENROUTER_IMAGE_MODEL` to change |
| `/gpt` | `openai/gpt-image-2` | Cheapest |
| `/flux` | `black-forest-labs/flux-3-image-klein` | Fastest |
| `/qwen` | `qwen/qwen-image-2.1-turbo` | |

* The same commands work in a photo's caption to get variations from that model.
* Each generated image has buttons under it: 🔄 Reload generates again with the same model and prompt, and Monet, Dalí, Picasso, 8-bit, EGA, Photo, Watercolour, Hand drawn, Sketch, Lithograph, Rubber stamp, Tattoo and Stencil regenerate it in that style. A cheap text model first removes words that fight the style, so a "photorealistic" prompt loses that word when you press Picasso, then a short phrase such as "in the style of Pablo Picasso" is added. (Image variations do not get buttons.)
* The bot only responds in group chats, unless you set `TELEGRAM_ALLOWED_USER_IDS`

# Requirements
* A Telegram bot token from [BotFather](https://t.me/botfather)
* An [OpenRouter API key](https://openrouter.ai/keys)
* Python 3.10+
* For self-hosted pull mode (long polling): nothing else
* For self-hosted push mode (webhook, optional):
  * A web server with a valid domain and certificate
  * Python gevent module
* If using the image variations feature:
  * Python pillow module

# Setup
* If self-hosting, see [pull setup](doc/self-hosted-pull.md) (simplest), or [push setup](doc/self-hosted-push.md) (webhook; optional)
* If running serverless, see [cloud function setup](doc/serverless.md)

# Security
## Protect your API keys and bot tokens
```
chmod 600 dalibot.env
```

## Preventing Unauthorized use of your bot
* Because Telegram bots are discoverable by anyone, the bot ignores private messages by default. You can whitelist users with `TELEGRAM_ALLOWED_USER_IDS`. User IDs can be obtained from the URL bar when messaging a user on https://web.telegram.org/, or from the bots console output when someone messages it. Example config:
```
TELEGRAM_ALLOWED_USER_IDS="123456789 987654321"
```
* It is recommended to message `/setjoingroups` to BotFather to set your bot group join to `Disabled` after you have added your bot to any desired groups.

## Secure your endpoint
* Only allow connections from Telegram's subnets as per the [example Nginx config](doc/self-hosted-push.md) or the [Amazon API Gateway Resource Policy](doc/serverless.md#amazon-api-gateway-resource-policy)
* Set `TELEGRAM_OUTGOING_TOKEN` to a strong value.

![Screenshot of chat with Dalibot](doc/dali_5.png?raw=true "a painting of a fox sitting in a field at sunrise in the style of Claude Monet")
