# Setup - AWS Lambda
These instructions are for AWS. The bot has not been tested under Azure/Google functions, and may require minor modification to work in those environments.

![Screenshot of chat with Dalibot](dali_4.png?raw=true "cute watermelon smiling")


## Create the Lambda function
Go to the [Lambda console](https://console.aws.amazon.com/lambda/home)
* Create a function
  * **Function name:** `dalibot`
  * **Runtime:** a Python version that matches the one you build for. By default the build script uses the Python on your build machine (check with `python -V` or `python3 -V`); to build for a different version, pass `-v` (see below)
  * **Architecture:** arm64
  * Hit _Create Function_
* You should now be in the function on the _Code_ tab. Scroll down to _Runtime settings_, and _Edit_
  * **Handler:** `bot.lambda_handler`
  * Hit _Save_
* Go to the _Configuration_ tab
  * Go to _General configuration_ and _Edit_
    * **Timeout:** `1` min
    * Hit _Save_

## Create the API Gateway
Go to the [API Gateway console](https://console.aws.amazon.com/apigateway/home)
* Build an API of type _REST API_
  * **API Name:** `dalibot`
  * Hit _Create API_
* From the _Action_ menu, Create a method of type _POST_
  * **Lambda function:** `dalibot`
  * Hit _Save_.
* Under your POST method > _Integration Request_:
  * Expand _HTTP Headers_ and add a header named `X-Amz-Invocation-Type` mapped from `'Event'` (with quotes). This tells Lambda to process incoming requests asyncronously, preventing duplicate notifications from Telegram.
  * Expand _Mapping Templates_ and add a mapping template for Content-Type `application/json`. Scroll down and enter the following mappings and _Save_. This allows the bot to route the request appropriately, and read Telegram's auth header:
```
{
    "method": "$context.httpMethod",
    "uri": "$context.path",
    "Content-Type" : "$input.params('Content-Type')",
    "body" : $input.json('$'),
    "headers": {
        #foreach($param in $input.params().header.keySet())
            "$param": "$util.escapeJavaScript($input.params().header.get($param))" #if($foreach.hasNext),#end
        #end
    }
}
```
* From the _Action_ menu, hit _Deploy API_
  * **Deployment stage:** `[New Stage]` 
  * **Stage name:** `dalibot` (this name forms your URI)
  * Hit _Deploy_
  * Take note of the _Invoke URL_ at the top of the stage editor


## Prepare the Lambda package

### Clone the git repo
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

### Run the build script
```
cd ~/dalibot
```
```
bash build_serverless.sh -p arm64
```

By default the package is built for the Python version running on your build machine. To build for a different Lambda runtime, add `-v` (for example `-v 3.13`). The Python version you choose must match the runtime you select in the function's _Runtime settings_.
```
bash build_serverless.sh -p arm64 -v 3.13
```

### Upload the package
Back in the Lambda function, go to the _Code_ tab and then _upload from .zip file_, and choose `dalibot_arm64.zip` from `~/dalibot/staging`.

### Configure
Go to _Configuration > Environment variables_ and add the following. See `dalibot.env.template` for the full list.

#### Mandatory parameters
  * Set `OPENROUTER_API_KEY` to your [OpenRouter API key](https://openrouter.ai/keys)
  * Set `TELEGRAM_OUTGOING_TOKEN` to a [secret token of your choice](https://core.telegram.org/bots/api#setwebhook)
  * Set `TELEGRAM_OUTGOING_WEBHOOK` to your API gateway stage Invoke URL from previous section
  * Set `TELEGRAM_BOT_TOKEN` to the token provided by [BotFather](https://core.telegram.org/bots/tutorial)

Example:
```
OPENROUTER_API_KEY=sk-or-v1-0123456789abcdef
TELEGRAM_BOT_TOKEN=4839574812:AAFD39kkdpWt3ywyRZergyOLMaJhac60qc
TELEGRAM_OUTGOING_TOKEN=sLnHdQmYoohmysecret7PX5VDM4cPW
TELEGRAM_OUTGOING_WEBHOOK=https://xxxxxx.execute-api.us-east-2.amazonaws.com/dalibot
```

#### Optional parameters

You can make stderr more verbose:
```
DALIBOT_DEBUG=1
```

You can choose the model behind the default command (defaults to `openai/gpt-image-2`). The `/gpt`, `/flux` and `/qwen` commands always use their own models:
```
OPENROUTER_IMAGE_MODEL=openai/gpt-image-2
```

You can choose the cheap text model that removes conflicting words from the prompt when a style button is pressed (defaults to `meta-llama/llama-3.1-8b-instruct`):
```
OPENROUTER_TEXT_MODEL=meta-llama/llama-3.1-8b-instruct
```

You can customise the bot command:
```
TELEGRAM_BOT_COMMAND=dream
```

You can enable private messaging by listing telegram numeric ids separated by a space:
```
TELEGRAM_ALLOWED_USER_IDS="123456789 987654321"
```

### Create the DynamoDB table (for image history)
The bot remembers each image message's prompt and the images made for it (as Telegram file ids, not the images themselves), so the buttons under an image can switch between them. This needs one small DynamoDB table. Without it the bot still works, but the buttons can't go back to earlier images (the logs say `Store ... failed (continuing without history)`).

In the [DynamoDB console](https://console.aws.amazon.com/dynamodbv2/home) choose _Create table_ and set:
  * **Table name:** `dalibot` (or set `DALIBOT_TABLE` to your name)
  * **Partition key:** `id`, type _String_

Leave _Table settings_ on _Default settings_ (DynamoDB Standard, On-demand capacity, no indexes) and choose _Create table_. Then open the table's _Additional settings_ and turn on _Time to live_ with the attribute name `ttl`. Old records then delete themselves (after 90 days; change with `DALIBOT_STORE_DAYS`).

Or with the AWS CLI:
```
aws dynamodb create-table --table-name dalibot --attribute-definitions AttributeName=id,AttributeType=S --key-schema AttributeName=id,KeyType=HASH --billing-mode PAY_PER_REQUEST
```
```
aws dynamodb update-time-to-live --table-name dalibot --time-to-live-specification Enabled=true,AttributeName=ttl
```

Then let the function use it. In the Lambda function go to _Configuration > Permissions_ and click the role name under _Execution role_ (it opens in the IAM console). On the role's _Permissions_ tab choose _Add permissions > Create inline policy_, switch to the _JSON_ editor, paste this (replace the region and account number with yours, which you can see in the function's ARN), then choose _Next_, name it (for example `dalibot-dynamodb`) and _Create policy_:
```
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": ["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:UpdateItem"],
            "Resource": "arn:aws:dynamodb:us-east-2:123456789012:table/dalibot"
        }
    ]
}
```
Lambda's Python runtime already includes the AWS library (`boto3`), so nothing needs adding to the package.

### Register the webhook with Telegram
The bot registers your webhook with Telegram when the function starts, which happens on its first invocation. Go to the _Test_ tab in the Lambda function and run any test event. The test itself is ignored (it has no Telegram message), but the logs should show:
```
Registering Telegram webhook: {"ok":true,"result":true,"description":"Webhook was set"}
Registering Telegram bot commands: {"ok":true,"result":true}
```
Telegram remembers the webhook, so you only need to do this again if you change `TELEGRAM_BOT_TOKEN`, `TELEGRAM_OUTGOING_TOKEN` or `TELEGRAM_OUTGOING_WEBHOOK`.


# Testing and troubleshooting
* Message the bot, then monitor the logs from Lambda Function > _Monitor > Logs_, or from the [CloudWatch console](https://console.aws.amazon.com/cloudwatch/home) under _Logs_ > _Log groups_.
* The function can also be triggered in other ways, but only a request with a Telegram json payload gets a reply. The _Test_ tab and the POST - Method execution in API Gateway console send no payload, so the bot logs "Ignoring invocation without a request body". With curl you can send one, for example:
  ```
  curl -iH "Content-Type: application/json" -H "X-Telegram-Bot-Api-Secret-Token: yoursecret" -X POST -d '{"message": {"message_id": 1, "from": {"id": 1, "first_name": "test" }, "chat": {"id": 123, "type": "private"}, "text": "hello" }}' https://xxxxxx.execute-api.us-east-2.amazonaws.com/dalibot
  ```
* If variations don't work and the error contains `ImportError: cannot import name '_imaging' from 'PIL'`, make sure the Python version and CPU architecture under  _Function > Code > Runtime settings_ match your build environment.

# Amazon API Gateway Resource Policy
(Optional) Improved security by locking down access to Telegram IP addresses. API Gateway Console > dalibot > Resource Policy:
```
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Principal": "*",
            "Action": "execute-api:Invoke",
            "Resource": "execute-api:/*/*/*",
            "Condition": {
                "IpAddress": {
                    "aws:SourceIp": [
                        "149.154.160.0/22",
                        "149.154.164.0/22",
                        "149.154.172.0/22",
                        "91.108.4.0/22",
                        "91.108.56.0/24"
                    ]
                }
            }
        }
    ]
}
```
