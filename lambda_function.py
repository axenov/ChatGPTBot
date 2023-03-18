import json
import os
import urllib3

TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')

def lambda_handler(event, context):
    if "body" in event and "message" in event["body"]:
        try:
            message = event["body"]["message"]
            if not message["from"]["is_bot"]:
                bot_message = message["text"]

                send_message_url = 'https://api.telegram.org/bot' + TELEGRAM_TOKEN + '/sendMessage'
                payload = {
                    "chat_id": message["chat"]["id"],
                    "parse_mode": "HTML",
                    "text": bot_message,
                    "reply_to_message_id": message["message_id"]
                }
                http = urllib3.PoolManager()
                response = http.request('POST', send_message_url, 
                                        headers={'Content-Type': 'application/json'},
                                        body=json.dumps(payload), timeout=10)
                print(response.data)
            return {
                'statusCode': 200,
                'body': "Message was sent succesfully!"
            }
        except Exception as e:
            print(e)
            return {
                'statusCode': 500,
                'body': "Error"
            }
    return {
        'statusCode': 200,
        'body': "Success"
    }