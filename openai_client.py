import os
import openai
import json
import random

from dinamodb_client import dynamoDBClient

OPENAI_KEY = os.environ.get('OPENAI_KEY')
OPENAI_MODEL = os.environ.get('OPENAI_MODEL')
SYSTEM_PROMPT = os.environ.get('SYSTEM_PROMPT')
ASSYSTANT_PROMPT = os.environ.get('ASSYSTANT_PROMPT')
STYLE_PROMPT = os.environ.get('STYLE_PROMPT')
CONTEXT_LENGTH = int(os.environ.get('CONTEXT_LENGTH'))
TEMPERATURE = float(os.environ.get('TEMPERATURE'))
TOP_P = float(os.environ.get('TOP_P'))
FREQUENCY_PENALTY = float(os.environ.get('FREQUENCY_PENALTY'))
PRESENCE_PENALTY = float(os.environ.get('PRESENCE_PENALTY'))
MAX_TOKENS = int(os.environ.get('MAX_TOKENS'))

class openaiClient:
    def __init__(self, dynamoDB_client: dynamoDBClient()) -> None:
        openai.api_key = OPENAI_KEY
        self.dynamoDB_client = dynamoDB_client
    
    def complete_chat(self, user_message: str, chat_id: int, bot_id: int):
        """ Generate the bot's answer to a user's message"""
        previous_messages = self.dynamoDB_client.load_messages(f"{str(chat_id)}_{str(bot_id)}")[-CONTEXT_LENGTH:]
        messages = [{"role": "system", "content": SYSTEM_PROMPT}] + \
            previous_messages + \
            [{"role": "user", "content": f"{user_message}\n{STYLE_PROMPT}"}]
        print(messages)
        
        response = openai.ChatCompletion.create(
            model=OPENAI_MODEL,
            messages = messages,
            temperature=TEMPERATURE,
            top_p=TOP_P,
            max_tokens=MAX_TOKENS,
            frequency_penalty=FREQUENCY_PENALTY,
            presence_penalty=PRESENCE_PENALTY,
        )
        answer = response["choices"][0]["message"]["content"]
        print(answer)
        previous_messages = previous_messages + [{"role": "user", "content": user_message}, {"role": "assistant", "content": answer}]
        previous_messages = previous_messages[-CONTEXT_LENGTH:] 
        self.dynamoDB_client.save_messages(f"{str(chat_id)}_{str(bot_id)}", previous_messages)
        return answer