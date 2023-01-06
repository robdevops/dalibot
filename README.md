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
* Runs stand-alone or serverless
* Minimal dependencies outside the Python Standard Library. There are none if you run it serverless and only use the text prompt feature.

# Usage
* The prompt must be three or more words
* The prompt must begin with `/dream`. Alternatively, @mention the bot if it has admin access in the group.
* The bot only responds in group chats, unless you set `telegramAllowedUserIDs` in dalibot.ini

# Requirements
* A Telegram bot token from [BotFather](https://core.telegram.org/bots/tutorial)
* An [OpenAI API key](https://beta.openai.com/account/api-keys)
* Python 3.8.10+
* For stand-alone mode:
  * A web server with a valid domain and certificate
  * gevent module for Python
* If using the image variations feature:
  * pillow module for Python
  * requests module for Python

# Setup
* If managing your own web server, see [WSGI setup](doc/standalone.md)
* If running serverless, see [cloud function setup](doc/serverless.md)

# Security
## Protect your API keys and bot tokens
```
chmod 600 dalibot.ini
```

## Preventing Unauthorized use of your bot
* Because Telegram bots are discoverable by anyone, the bot ignores private messages by default. You can whitelist users in dalibot.ini. User IDs can be obtained from the URL bar when messaging a user on https://web.telegram.org/, or from the bots console output when someone messages it. Example config:
```
telegramAllowedUserIDs = 123456789 987654321
```
* It is recommended to message `/setjoingroups` to BotFather to set your bot group join to `Disabled` after you have added your bot to any desired groups.
## Secure your endpoint
* Only allow connections from Telegram's subnets as per the [example Nginx config](doc/standalone.md).
* Set `telegramOutgoingToken` to a strong value.

![Screenshot of chat with Dalibot](doc/dali_5.png?raw=true "a painting of a fox sitting in a field at sunrise in the style of Claude Monet")
