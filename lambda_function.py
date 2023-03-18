import json
import os
import urllib3

OPENAI_KEY = os.environ.get('OPENAI_KEY')
BOT_ID = os.environ.get('BOT_ID')
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
FREQUENCY = os.environ.get('FREQUENCY')
ALLOWED_CHATS = [int(num) for num in os.environ.get('ALLOWED_CHATS').split(',')]

SEND_MESSAGE_URL = 'https://api.telegram.org/bot' + TELEGRAM_TOKEN + '/sendMessage'
http = urllib3.PoolManager()

class openaiClient:
    def __init__(self) -> None:
        pass


class telegramClient:
    def __init__(self) -> None:
        self.openai_client = openaiClient()
    
    def send_message(self, text: str, chat_id, original_message_id):
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
    
    def should_reply(self, message:dict):
        """ The function that decides whether the bot should reply to a message or not

        Returns:
            bool: boolean value
        """
        if "reply_to_message" in message and message["reply_to_message"]["from"]["id"] == BOT_ID:
            return True
        return False
    
    def process_message(self, body):
        """ Process a message of a user and with some probability reply to it

        Args:
            body (str): a telegram webhook body
        """
        if (
            "message" in body and
            not body["message"]["from"]["is_bot"]
            ):
            message = body["message"]
            # Extract the message of a user
            if "text" in body["message"]:
                user_message = message["text"]
            elif "sticker" in body["message"] and "emoji" in body["message"]["sticker"]:
                user_message = message["sticker"]["emoji"]
            else:
               return
           
            chat_id = message["chat"]["id"]
            message_id=message["message_id"]
            if chat_id not in ALLOWED_CHATS:
                return
            
            if self.should_reply(message):
                ## Add here OpenAI call
                bot_message = user_message
                self.send_message(bot_message, chat_id, message_id)


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