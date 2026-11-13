# dalibot
Telegram chat bot for AI image generation, powered by [OpenRouter](https://openrouter.ai/) (choose from dozens of image models)

# Description
* Responds to a text prompt with an image
* Responds to an image with four clearly different variations (each redrawn in its own style and shown from its own viewpoint, both invented by a cheap text model), sent as one album, each picture captioned with its own style and viewpoint. Add a caption to steer them.

![Screenshot of chat with Dalibot](doc/dali_1.png?raw=true "close up portrait of a girl in the style of Claude Monet")

# Features
* Auto convert, crop, and resize uploaded images to meet image model requirements
* Optionally archive results to local storage
* Runs self-hosted or serverless
* Minimal dependencies outside the Python Standard Library. There are none if you run it serverless and only use the text prompt feature.

# Usage
* The prompt must be three or more words
* The prompt must begin with a command, or tag the bot (`@botname`, anywhere in the message) if it has admin access in the group. Each command uses a different model:

| Command | Model | Notes |
| --- | --- | --- |
| `/dream` | `openai/gpt-image-2` by default | Set `OPENROUTER_IMAGE_MODEL` to change |
| `/imagine` | same as `/dream` | An alias of the default command |
| `/gpt` | `openai/gpt-image-2` | Cheapest |
| `/flux` | `black-forest-labs/flux-3-image-klein` | Fastest |
| `/qwen` | `qwen/qwen-image-2.1-turbo` | |

* The same commands work in a photo's caption to get variations from that model. In a group you can also reply to any picture (including one the bot made) with `@botname`, or with a bare command such as `/flux`, to get variations of it. Anything you add is passed along as a note, for example `@botname make it winter`.
* Editing a message to tag the bot (or to start with a command) works as if you had just sent it. That includes adding the tag to a photo's caption or changing a prompt. Edits that don't tag the bot are ignored.
* `/credits` (also `/tokens`, `/usage` and `/cost`) shows what the bot's OpenRouter API key has spent today, this week and this month, using OpenRouter's own totals. If `TELEGRAM_ALLOWED_USER_IDS` lists user ids, only those users can ask.
* Each generated image has buttons under it. Every button replaces the image in place:
  * 🔄 Remix generates again with the same model, prompt and style.
  * The style buttons (Monet, Dalí, Picasso, 8-bit, EGA, Photo, Watercolour, Hand drawn, Sketch, Lithograph, Rubber stamp, Tattoo, Stencil, Anime, Van Gogh, Oil painting, Cartoon, Comic book, 3D render, Pop art, Cyberpunk, Ukiyo-e and Black & white) work like tabs. The first press makes the image. Pressing it again later shows that image straight away, without calling a model. ↩ Original goes back to the image before any style.
  * Before a style is applied, a cheap text model removes words that fight it, so a "photorealistic" prompt loses that word when you press Picasso. Then a short phrase such as "in the style of Pablo Picasso" is added.
  * While an image is being made, the pressed button shows ⏳ in green, and the image and caption stay as they were until the new one replaces them. The other buttons just say "still painting" until it's done. If it fails, the previous buttons come back.
  * Image variations do not get buttons.
  * The bot keeps a small record of each image message (the prompt and Telegram file ids, not the images) in SQLite when self-hosted or DynamoDB on Lambda. See the setup guides.
  * To record pictures the bot made before it kept records, forward them to the bot in a private chat (you must be in `TELEGRAM_ALLOWED_USER_IDS`). Each one is saved with its caption and the date it was first sent, and the bot reacts with 👍. Nothing is generated, and forwarding the same picture twice does not add it twice. A forwarded picture has no buttons, is recorded under the default command whatever model made it, and is forgotten after `DALIBOT_STORE_DAYS` like any other record (forward it again to keep it longer). Forward with the sender and caption shown; a copy sent without them is treated as a new photo. To get variations of one of the bot's pictures, reply to it in the group instead of forwarding it.
* The bot only responds in group chats, unless you set `TELEGRAM_ALLOWED_USER_IDS` (user ids, or `all`)

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
  If you have already limited who can reach the bot, for example in BotFather, set `TELEGRAM_ALLOWED_USER_IDS=all` to let everyone who can reach it message it privately. Only do this if that restriction really is in place, because the bot then answers (and spends your OpenRouter credits for) anyone who can send it a message.
* It is recommended to message `/setjoingroups` to BotFather to set your bot group join to `Disabled` after you have added your bot to any desired groups.

## Secure your endpoint
* Only allow connections from Telegram's subnets as per the [example Nginx config](doc/self-hosted-push.md) or the [Amazon API Gateway Resource Policy](doc/serverless.md#amazon-api-gateway-resource-policy)
* Set `TELEGRAM_OUTGOING_TOKEN` to a strong value.

![Screenshot of chat with Dalibot](doc/dali_5.png?raw=true "a painting of a fox sitting in a field at sunrise in the style of Claude Monet")
