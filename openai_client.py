import os
import openai

OPENAI_KEY = os.environ.get('OPENAI_KEY')
OPENAI_MODEL = os.environ.get('OPENAI_MODEL')

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