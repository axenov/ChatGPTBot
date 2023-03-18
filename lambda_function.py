import json
from botocore.vendored import requests


def lambda_handler(event, context):
    BOT_TOKEN = os.environ.get('TELEGRAM_TOKEN')
    BOT_CHAT_ID = "6591590"
    bot_message = "Лищ кит"
    payload = 'https://api.telegram.org/bot' + BOT_TOKEN + '/sendMessage?chat_id=' + BOT_CHAT_ID + \
                '&parse_mode=HTML&text=' + bot_message
    response = requests.get(payload, timeout=10)
    return {
        'statusCode': 200,
        'body': json.dumps('Hello from Lambda!')
    }
