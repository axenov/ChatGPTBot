import os
import openai
import json

from dinamodb_client import dynamoDBClient

OPENAI_KEY = os.environ.get('OPENAI_KEY')
OPENAI_MODEL = os.environ.get('OPENAI_MODEL')
SYSTEM_PROMPT = os.environ.get('SYSTEM_PROMPT')
ASSYSTANT_PROMPT = os.environ.get('ASSYSTANT_PROMPT')
CONTEXT_LENGTH = int(os.environ.get('CONTEXT_LENGTH'))

#dynamoDB_client = dynamoDBClient()
class openaiClient:
    def __init__(self) -> None:
        openai.api_key = OPENAI_KEY
    
    def complete_chat(self, user_message: str, chat_id: int, bot_id: int):
        """ Generate the bot's answer to a user's message"""
        #previous_messages = dynamoDB_client.load_messages(chat_id=f"{str(chat_id)}_{str(bot_id)}")[-CONTEXT_LENGTH:]
        previous_messages=[]
        
        messages = [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "assistant", "content": ASSYSTANT_PROMPT}] + \
            previous_messages + \
            [{"role": "user", "content": user_message}]
        
        
        response = openai.ChatCompletion.create(
            model=OPENAI_MODEL,
            messages = messages,
            temperature=1.0,
            max_tokens=128,
            frequency_penalty=1.0,
            presence_penalty=1.0,
        )
        answer = response["choices"][0]["message"]["content"]
        print(answer)
        #dynamoDB_client.save_messages(chat_id, messages[-(CONTEXT_LENGTH-1):] + [json.dumps({"role": "assistant", "content": answer})])
        return answer