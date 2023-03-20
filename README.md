# ChatGPTBot

This is a conversational assistant for Telegram running on AWS Lambda and DynamoDB and using OpenAI API to generate answers.

To connect the Lambda function to you Telegram bot run:

```bash
curl --data "url={API_GATEWAY_URL}" "https://api.telegram.org/bot{TELEGRAM_TOKEN}/setWebhook"
```

Environmental Variables:

| Variable            | Description                                                 |
| ------------------- | ----------------------------------------------------------- |
| ALLOWED_CHATS       | ids of the supported chats                                  |
| BOT_ID              | id of a bot                                                 |
| FREQUENCY           | frequency at which the bot replies to messages              |
| OPENAI_KEY          | OpenAI secret key                                           |
| OPENAI_MODEL        | the used OpenAI model                                       |
| TELEGRAM_TOKEN      | Telegram API access token                                   |
| SYSTEM_PROMPT       | description of a bot role                                   |
| STYLE_PROMPT        | how the bot should answer, concatenated to any user message |
| CONTEXT_LENGTH      | number of messages analyzed to make a reply                 |
| DYNAMODB_TABLE_NAME | DynamoDB table name                                         |
| RESET_COMMAND       | the Telegram bot command to reset the history               |
| BOT_NAME            | the name of the bot as it is in Telegram                    |
| MAX_TOKENS          | number of tokens in model response                          |
| PRESENCE_PENALTY    | presence penalty model parameter                            |
| FREQUENCY_PENALTY   | frequency penalty model parameter                           |
| TOP_P               | top_p model parameter                                       |
| TEMPERATURE         | temperature model parameter                                 |

