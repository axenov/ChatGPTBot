import json
import os
import urllib3

TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
SEND_MESSAGE_URL = 'https://api.telegram.org/bot' + TELEGRAM_TOKEN + '/sendMessage'

http = urllib3.PoolManager()

def send_message(text: str, chat_id, original_message_id):
    """ Reply to a message of a user

    Args:
        text (str): the bot's message
        chat_id (int): id of a chat
        original_message_id (int): id of a message to reply to
    """
    payload = {
        "chat_id": chat_id,
        "parse_mode": "HTML",
        "text": text,
        #"reply_to_message_id": original_message_id
    }
    response = http.request('POST', SEND_MESSAGE_URL, 
                            headers={'Content-Type': 'application/json'},
                            body=json.dumps(payload), timeout=10)
    print(response.data)
    
def should_reply():
    """ The function that decides whether the bot should reply to a message or not

    Returns:
        boot: True of False
    """
    return True

def lambda_handler(event, context):
    if "body" in event:
        try:
            body = json.loads(event["body"])
            if "message" in body and not body["message"]["from"]["is_bot"]:
                message = body["message"]
                ## Add here OpenAI call
                if should_reply():
                    bot_message = message["text"]
                    send_message(bot_message, message["chat"]["id"], message["message_id"])
                    return {
                        'statusCode': 200,
                        'body': "Message was sent succesfully"
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