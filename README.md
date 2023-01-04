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

# Requirements
* Either a serverless environment like AWS Lambda, or a web server with a valid domain name and certificate.
* A Telegram bot token from [BotFather](https://core.telegram.org/bots/tutorial)
* An [OpenAI API key](https://beta.openai.com/account/api-keys)
* Python 3.8.10+
  * gevent (only if not running serverless)
  * pillow (only if using the image variations feature)
  * requests

# Usage
* The prompt must be three or more words
* The prompt must begin with `/dream`. Alternatively, @mention the bot if it has admin access in the group.
* The bot only responds in group chats, unless you set `telegramAllowedUserIDs` in dalibot.ini

![Screenshot of chat with Dalibot](doc/dali_2.png?raw=true "an impressionist oil painting of sunflowers in a purple vase")

# Setup
* If managing your own web server, see [WSGI setup](doc/standalone.md)
* If running serverless, see [cloud function setup](doc/serverless.md)

![Screenshot of chat with Dalibot](doc/dali_4.png?raw=true "cute watermelon smiling")

# Security
* If not running serverless, protect your API keys and bot tokens from other users on the system:
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
