import json
import os
import urllib3


def lambda_handler(event, context):
    if not event["body"]["message"]["from"]["is_bot"]:
        BOT_TOKEN = os.environ.get('TELEGRAM_TOKEN')
        BOT_CHAT_ID = event["body"]["message"]["chat"]["id"]
        bot_message = event["body"]["message"]["text"]
        payload = 'https://api.telegram.org/bot' + BOT_TOKEN + '/sendMessage?chat_id=' + BOT_CHAT_ID + '&parse_mode=HTML&text=' + bot_message
        http = urllib3.PoolManager()
        response = http.request('GET', payload, timeout=10)
        print(response.data)
    return {
        'statusCode': 200,
        'body': "Success"
    }