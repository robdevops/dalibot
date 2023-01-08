# Setup - AWS Lambda
These instructions are for AWS. The bot has not been tested under Azure/Google functions, and may require minor modification to work in those environments.

![Screenshot of chat with Dalibot](dali_4.png?raw=true "cute watermelon smiling")


## Create the Lambda function
Go to the [Lambda console](https://us-east-2.console.aws.amazon.com/lambda/home)
* Create a function
  * **Function name:** `dalibot`
  * **Runtime:** the Python version that matches your build environment (check with `python -V`
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
Go to the [API Gateway console](https://us-east-2.console.aws.amazon.com/apigateway/home)
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
```
sudo $(which apt dnf yum) install git
```
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

### Complete the config
```
cd staging
```

```
Edit dalibot.ini
```

#### Mandatory parameters
  * Set `openai_api_key` to the [key from OpenAI](https://beta.openai.com/account/api-keys)
  * Set `telegramOutgoingToken` to a [secret token of your choice](https://core.telegram.org/bots/api#setwebhook)
  * Set `telegramOutgoingWebhook` to your API gateway stage Invoke URL from previous section
  * Set `telegramBotToken` to the token provided by [BotFather](https://core.telegram.org/bots/tutorial)

Example:
```
openai_api_key = sk-p999HAfj6Cm1bO00SXgJc7kFxvFPtQ1KBBWrqSOU
telegramBotToken = 4839574812:AAFD39kkdpWt3ywyRZergyOLMaJhac60qc
telegramOutgoingToken = sLnHdQmYoohmysecret7PX5VDM4cPW
telegramOutgoingWebhook = https://xxxxxx.execute-api.us-east-2.amazonaws.com/dalibot
```

#### Optional parameters

You can make stderr more verbose:
```
debug = 1
```

You can customise the bot command:
```
telegramBotCommand = dream
```

You can enable private messaging by listing telegram numeric ids separated by a space:
```
telegramAllowedUserIDs = 123456789 987654321
```

### Add your config to the package
```
zip dalibot_arm64.zip dalibot.ini
```

### Upload the package
Back in the Lambda function, go to the _Code_ tab and then _upload from .zip file_ from the staging directory.


# Testing and troubleshooting
* Message the bot, then monitor the logs from Lambda Function > _Monitor > Logs_, or from the [CloudWatch console](https://us-east-2.console.aws.amazon.com/cloudwatch/home) under _Logs_ > _Log groups_.
* The function can also be triggered in various ways, but these will fail at various points because they won't receive the Telegram json payload:
  * From the _Test_ tab in the Lambda function
  * From the POST - Method execution in API Gateway console.
  * With curl, for example:
  ```
  curl -iH "Content-Type: application/json" -H "X-Telegram-Bot-Api-Secret-Token: yoursecret" -X POST -d '{"message": {"message_id": 1, "from": {"id": 1, "first_name": "test" }, "chat": {"id": 123, "type": "private"}, "text": "hello" }}' https://xxxxxx.execute-api.us-east-2.amazonaws.com/dalibot
  ```
* If variations don't work and the error contains `ImportError: cannot import name '_imaging' from 'PIL'`, make sure the Python version and CPU architecture under  _Function > Code > Runtime settings_ match your build environment.

# Amazon API Gateway Resource Policy
Optional: An example Telegram ACL for API Gateway Console > dalibot > Resource Policy:
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
