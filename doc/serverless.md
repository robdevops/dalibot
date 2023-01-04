# Setup - AWS Lambda
The bot should also work as an Azure Function or a Google Cloud Function, but it has not been tested, and the setup procedure will vary, although principles remain the same.

![Screenshot of chat with Dalibot](dali_4.png?raw=true "cute watermelon smiling")


## Create the Lambda function
Go to the [Lambda console](https://us-east-2.console.aws.amazon.com/lambda/home)
* Create a function
  * Function name: dalibot
  * In the _Runtime_ drop down menu, select the latest Python
  * Click _Create Function_
* Scroll down to _Runtime settings_ and _Edit_
  * Change _Handler_ to _bot.lambda_handler_ and _Save_
* Go to the _Configuration_ tab
  * Go to _General configuration_ and _Edit_
    * Change Timeout to _1 min_ and _Save_

## Create the API Gateway
Go to the [API Gateway console](https://us-east-2.console.aws.amazon.com/apigateway/home)
* Create an API of type _REST API_
  * API Name: dalibot
* From the _Action_ menu, Create a method of type _POST_
  * Enter your Lambda function name and _Save_.
* Under your method > _Integration Request_:
  * Expand _HTTP Headers_. Add a header named `X-Amz-Invocation-Type` mapped from `'Event'` (with quotes). This tells Lambda to process incoming requests asyncronously, preventing duplicate notifications from Telegram.
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
* From the _Action_ menu, choose _Deploy API_ and create a new stage. The name will form your URI.
  * Go to _Deploy_ and take note of the _Invoke URL_ at the top of the stage editor.


## Prepare the Lambda package
* Clone the git repo
```
sudo $(which apt dnf yum) install git
```
```
git clone https://github.com/robdevops/dalibot.git ~/dalibot
```
* Install the Python modules
```
cd ~/dalibot
```
```
pip3 install requests pillow --upgrade --target=$(pwd)
```
* Copy and edit the example config
```
cp dalibot.ini.template dalibot.ini
```

* Edit dalibot.ini. Mandatory parameters:
  * Set `openai_api_key` to the [key from OpenAI](https://beta.openai.com/account/api-keys)
  * Set `telegramOutgoingToken` to a [secret token of your choice](https://core.telegram.org/bots/api#setwebhook)
  * Set `telegramOutgoingWebhook` to the URL of your Amazon API Gateway stage
  * Set `telegramBotToken` to the token provided by [BotFather](https://core.telegram.org/bots/tutorial)

Example:
```
openai_api_key = sk-p999HAfj6Cm1bO00SXgJc7kFxvFPtQ1KBBWrqSOU
telegramBotToken = 4839574812:AAFD39kkdpWt3ywyRZergyOLMaJhac60qc
telegramOutgoingToken = sLnHdQmYoohmysecret7PX5VDM4cPW
telegramOutgoingWebhook = https://kgah94bla2.execute-api.us-east-2.amazonaws.com/dalibot
```

Optional parameters:
```
debug = 1
```

Enable private messaging by listing telegram numeric ids separated by a space:
```
telegramAllowedUserIDs =
```

* Create the package
```
zip -r script.zip .
```
* Back in the Lambda function, go to the _Code_ tab and upload from .zip file

## Testing and troubleshooting
* Message the bot, then monitor the logs from Lambda Function > _Monitor > Logs_, or from the [CloudWatch console](https://us-east-2.console.aws.amazon.com/cloudwatch/home) under _Logs_ > _Log groups_.
* The function can also be triggered in various ways, but these will not be end-to-end tests:
  * From the _Test_ tab in the Lambda function
  * From the POST - Method execution in API Gateway console.
  * With curl, for example:
  ```
  curl -iH "Content-Type: application/json" -H "X-Telegram-Bot-Api-Secret-Token: yoursecret" -X POST -d '{"message": {"message_id": 1, "from": {"id": 1, "first_name": "test" }, "chat": {"id": 123, "type": "private"}, "text": "hello" }}' https://xxxxxx.execute-api.us-east-2.amazonaws.com/dalibot
  ```
