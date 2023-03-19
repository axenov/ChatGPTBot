# ChatGPTBot

This is a conversational assistant for Telegram running on AWS Lambda and using OpenAI API to generate answers.

To connect the AWS Lambda to your Telegram bot run:

```bash
curl --data "url={YOUR_API_GATEWAY_URL}" "https://api.telegram.org/bot{TELEGRAM_TOKEN}/setWebhook"
```

Environmental Variables:

| Variable       | Description                                    |
| -------------- | ---------------------------------------------- |
| ALLOWED_CHATS  | ids of the supported chats                     |
| BOT_ID         | id of a bot                                    |
| FREQUENCY      | frequency at which the bot replies to messages |
| OPENAI_KEY     | OpenAI secret key                              |
| OPENAI_MODEL   | the used OpenAI model                          |
| TELEGRAM_TOKEN | Telegram API access token                      |
|                |                                                |
|                |                                                |
|                |                                                |

