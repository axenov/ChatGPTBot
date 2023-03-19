import os
import openai
import json

from dinamodb_client import dynamoDBClient

OPENAI_KEY = os.environ.get('OPENAI_KEY')
OPENAI_MODEL = os.environ.get('OPENAI_MODEL')
SYSTEM_PROMPT = os.environ.get('SYSTEM_PROMPT')
ASSYSTANT_PROMPT = os.environ.get('ASSYSTANT_PROMPT')
CONTEXT_LENGTH = int(os.environ.get('CONTEXT_LENGTH'))

class openaiClient:
    def __init__(self, dynamoDB_client: dynamoDBClient()) -> None:
        openai.api_key = OPENAI_KEY
        self.dynamoDB_client = dynamoDB_client
    
    def complete_chat(self, user_message: str, chat_id: int, bot_id: int):
        """ Generate the bot's answer to a user's message"""
        previous_messages = self.dynamoDB_client.load_messages(f"{str(chat_id)}_{str(bot_id)}")[-CONTEXT_LENGTH:]
        
        messages = [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "assistant", "content": ASSYSTANT_PROMPT}] + \
            previous_messages + \
            [{"role": "user", "content": user_message}]
        print(messages)
        
        response = openai.ChatCompletion.create(
            model=OPENAI_MODEL,
            messages = messages,
            temperature=1.0,
            max_tokens=160,
            frequency_penalty=1.0,
            presence_penalty=1.0,
        )
        answer = response["choices"][0]["message"]["content"]
        print(answer)
        self.dynamoDB_client.save_messages(f"{str(chat_id)}_{str(bot_id)}", previous_messages[-(CONTEXT_LENGTH-1):] + [{"role": "user", "content": user_message}, {"role": "assistant", "content": answer}])
        return answer