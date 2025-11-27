# ChatGPTBot

This is a conversational assistant for Telegram running on AWS Lambda and DynamoDB and using OpenAI API to generate answers.

New capabilities:
- Vision understanding when users attach Telegram photos.
- Image generation through Gemini when the model triggers the dedicated tool.

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
| MAX_TOKENS          | maximum completion tokens (sent as `max_completion_tokens`) |
| PRESENCE_PENALTY    | deprecated for GPT-5 (ignored)                              |
| FREQUENCY_PENALTY   | deprecated for GPT-5 (ignored)                              |
| TOP_P               | deprecated for GPT-5 (ignored)                              |
| TEMPERATURE         | temperature model parameter                                 |
| GEMINI_API_KEY      | API key for Gemini image generation                         |
| GEMINI_IMAGE_MODEL  | Gemini model name for image creation (default: gemini-2.5-flash-image) |
| IMAGE_MIME_TYPE     | MIME type for generated images (e.g., image/png)            |

Deployment notes:
- Update the Lambda layer/package with the refreshed `requirements.txt` (OpenAI and google-generativeai).
- Ensure the Telegram webhook is still configured with the API Gateway URL after deployment.
- Grant the function access to DynamoDB and allow outbound HTTPS so it can reach Telegram, OpenAI, and Gemini endpoints.

