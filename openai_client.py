import os
import openai
import json
import random

from dinamodb_client import dynamoDBClient

OPENAI_KEY = os.environ.get('OPENAI_KEY')
OPENAI_MODEL = os.environ.get('OPENAI_MODEL')
SYSTEM_PROMPT = os.environ.get('SYSTEM_PROMPT')
ASSYSTANT_PROMPT = os.environ.get('ASSYSTANT_PROMPT')
FACT_PROMPT = os.environ.get('FACT_PROMPT')
CONTEXT_LENGTH = int(os.environ.get('CONTEXT_LENGTH'))

class openaiClient:
    def __init__(self, dynamoDB_client: dynamoDBClient()) -> None:
        openai.api_key = OPENAI_KEY
        self.dynamoDB_client = dynamoDB_client
    
    def complete_chat(self, user_message: str, chat_id: int, bot_id: int):
        """ Generate the bot's answer to a user's message"""
        previous_messages = self.dynamoDB_client.load_messages(f"{str(chat_id)}_{str(bot_id)}")[-CONTEXT_LENGTH:]
        # Boost the style
        #previous_messages= previous_messages[:int(CONTEXT_LENGTH / 2)] + [{"role": "assistant", "content": ASSYSTANT_PROMPT}] + previous_messages[int(CONTEXT_LENGTH / 2):]
        messages = [{"role": "system", "content": FACT_PROMPT+SYSTEM_PROMPT}, {"role": "assistant", "content": ASSYSTANT_PROMPT}] + \
            previous_messages + \
            [{"role": "user", "content": user_message}]
        if random.random()<0.3:
            messages += [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "assistant", "content": ASSYSTANT_PROMPT}]
        print(messages)
        
        response = openai.ChatCompletion.create(
            model=OPENAI_MODEL,
            messages = messages,
            temperature=1.0,
            top_p=1.0,
            max_tokens=128,
            frequency_penalty=1.0,
            presence_penalty=1.0,
        )
        answer = response["choices"][0]["message"]["content"]
        print(answer)
        self.dynamoDB_client.save_messages(f"{str(chat_id)}_{str(bot_id)}", previous_messages[-(CONTEXT_LENGTH-1):] + [{"role": "user", "content": user_message}, {"role": "assistant", "content": answer}])
        return answer