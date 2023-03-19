import json

from telegram_client import telegramClient

telegram_client = telegramClient()

def lambda_handler(event, context):
    if "body" in event:
        try:
            body = json.loads(event["body"])
            telegram_client.process_message(body)
        except Exception as e: 
            print(e)
            return {
                'statusCode': 200,
                'body': "Error"
            }
    return {
        'statusCode': 200,
        'body': "Success"
    }