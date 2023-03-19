import json
import os
import urllib3
import random
import openai

BOT_ID = int(os.environ.get('BOT_ID'))
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
FREQUENCY = float(os.environ.get('FREQUENCY'))
ALLOWED_CHATS = [int(num) for num in os.environ.get('ALLOWED_CHATS').split(',')]

OPENAI_KEY = os.environ.get('OPENAI_KEY')
OPENAI_MODEL = os.environ.get('OPENAI_MODEL')

SEND_MESSAGE_URL = 'https://api.telegram.org/bot' + TELEGRAM_TOKEN + '/sendMessage'
http = urllib3.PoolManager()

class openaiClient:
    def __init__(self) -> None:
        openai.api_key = OPENAI_KEY
    
    def complete_chat(self, user_message: str):
        response = openai.ChatCompletion.create(
            model=OPENAI_MODEL,
            messages = [
                {"role": "system", "content": "Ты чат-бот с открытым исходным кодом, который использует OpenAI GPT-3.5 для генерации ответов на вопросы. Пиши краткие сообщения."},
                {"role": "user", "content": user_message},
            ],
            temperature=1.0,
            max_tokens=128,
            frequency_penalty=1.0,
            presence_penalty=1.0,
        )
        answer = response["choices"][0]["message"]["content"]
        print(answer)
        return answer


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
            "reply_to_message_id": original_message_id
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
        else:
            bet = random.random()
            if bet < FREQUENCY:
                return True
        return False
    
    def process_message(self, body):
        """ Process a message of a user and with some probability reply to it

        Args:
            body (str): a telegram webhook body
        """
        if (
            "message" in body and
            not body["message"]["from"]["is_bot"] and
            "forward_from_message_id" not in body["message"]
            ):
            message = body["message"]
            # Extract the message of a user
            if "text" in body["message"]:
                user_message = message["text"]
            elif "sticker" in body["message"] and "emoji" in body["message"]["sticker"]:
                user_message = message["sticker"]["emoji"]
            elif "photo" in body["message"] and "caption" in body["message"]["photo"]:
                user_message = message["photo"]["caption"]
            else:
               return
           
            chat_id = message["chat"]["id"]
            message_id=message["message_id"]
            if chat_id not in ALLOWED_CHATS:
                return
            
            if self.should_reply(message):
                bot_message = self.openai_client.complete_chat(user_message)
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