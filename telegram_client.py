import json
import os
import urllib3
import random
import re

from openai_client import openaiClient
from dinamodb_client import dynamoDBClient

BOT_ID = int(os.environ.get('BOT_ID'))
BOT_NAME = os.environ.get('BOT_NAME')
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
FREQUENCY = float(os.environ.get('FREQUENCY'))
ALLOWED_CHATS = [int(num) for num in os.environ.get('ALLOWED_CHATS').split(',')]
RESET_COMMAND = os.environ.get('RESET_COMMAND')
CONTEXT_LENGTH = int(os.environ.get('CONTEXT_LENGTH'))

SEND_MESSAGE_URL = 'https://api.telegram.org/bot' + TELEGRAM_TOKEN + '/sendMessage'
http = urllib3.PoolManager()

dynamoDB_client = dynamoDBClient()
openai_client = openaiClient(dynamoDB_client)

def format_for_telegram(text: str) -> str:
    """
    Финальная, пуленепробиваемая версия, которая готовит текст для MarkdownV2.
    Конвертирует заголовки, защищает валидную разметку и экранирует всё остальное.
    """
    # Шаг 1: Конвертируем заголовки в жирный-подчеркнутый текст.
    heading_pattern = re.compile(r'^\s*#+\s+(.*?)\s*$', re.MULTILINE)
    text = heading_pattern.sub(r'__**\1**__', text)

    # Шаг 2: Защищаем все известные сущности Markdown.
    patterns = [
        r'```(?:.|\n)*?```', r'`.*?`', r'\[.*?\]\(.*?\)', r'__\*\*(?:.|\n)*?\*\*__',
        r'\*(?:.|\n)*?\*', r'_(?:.|\n)*?_', r'__(?:.|\n)*?__', r'~(?:.|\n)*?~',
        r'\|\|(?:.|\n)*?\|\|',
    ]
    master_pattern = re.compile('|'.join(patterns), re.DOTALL)
    
    protected_blocks = []
    
    def _protect_block(match):
        placeholder = f"UNBREAKABLEPLACEHOLDER{len(protected_blocks)}UNBREAKABLE"
        protected_blocks.append(match.group(0))
        return placeholder
    
    text_with_placeholders = master_pattern.sub(_protect_block, text)

    # Шаг 3: Экранируем оставшиеся спецсимволы.
    escape_chars = r'_*[]()~`>#+-=|{}.!' 
    escape_pattern = f'([{re.escape(escape_chars)}])'
    escaped_text = re.sub(escape_pattern, r'\\\1', text_with_placeholders)

    # Шаг 4: Возвращаем защищенные блоки на место.
    for i, block in enumerate(protected_blocks):
        placeholder_to_replace = f"UNBREAKABLEPLACEHOLDER{i}UNBREAKABLE"
        escaped_text = escaped_text.replace(placeholder_to_replace, block)
        
    return escaped_text

import re

def format_with_code_blocks(text: str) -> str:
    """
    A controlled formatter for Telegram MarkdownV2.
    
    This function's priorities are:
    1. Preserve all code blocks (`...` and ```...```) perfectly.
    2. Escape all other special characters to prevent API errors.
    """
    # A list to store the code blocks we find.
    code_blocks = []
    
    # A simple function to replace a found code block with a placeholder.
    def _protect_code_block(match):
        # Add the found code block (e.g., `my_variable`) to our list.
        code_blocks.append(match.group(0))
        # Return a unique, safe placeholder.
        return f"CODEBLOCKPLACEHOLDER{len(code_blocks) - 1}"

    # This regex finds both multiline ```...``` and inline `...` code blocks.
    code_pattern = re.compile(r'(```(?:.|\n)*?```|`.*?`)', re.DOTALL)
    # Run the replacement.
    text_with_placeholders = code_pattern.sub(_protect_code_block, text)

    # Now, escape every other special character in the remaining text.
    escape_chars = r'_*[]()~`>#+-=|{}.!'
    remaining_text_escaped = re.sub(f'([{re.escape(escape_chars)}])', r'\\\1', text_with_placeholders)

    # Finally, restore the original code blocks.
    final_text = remaining_text_escaped
    for i, block in enumerate(code_blocks):
        final_text = final_text.replace(f"CODEBLOCKPLACEHOLDER{i}", block)
        
    return final_text

def format_with_styles(text: str) -> str:
    """
    Formats text for Telegram MarkdownV2, preserving code blocks,
    bold, italic, and underline styles.
    """
    # A list to store the protected formatting blocks.
    protected_blocks = []
    
    # The function to replace a found block with a placeholder.
    def _protect_block(match):
        protected_blocks.append(match.group(0))
        return f"PROTECTEDBLOCK{len(protected_blocks) - 1}"

    # We now add patterns for bold, italic, and underline.
    # The order is important: more specific patterns (like underline) go first.
    patterns = [
        r'```(?:.|\n)*?```',  # Multiline code blocks
        r'`.*?`',              # Inline code
        r'__(?:.|\n)*?__',     # Underline
        r'\*(?:.|\n)*?\*',      # Bold
        r'_(?:.|\n)*?_',      # Italic
    ]
    master_pattern = re.compile('|'.join(patterns), re.DOTALL)
    
    # Run the replacement to protect all specified markdown.
    text_with_placeholders = master_pattern.sub(_protect_block, text)

    # Escape every other special character in the remaining text.
    escape_chars = r'_*[]()~`>#+-=|{}.!'
    remaining_text_escaped = re.sub(f'([{re.escape(escape_chars)}])', r'\\\1', text_with_placeholders)

    # Restore the original, protected blocks.
    final_text = remaining_text_escaped
    for i, block in enumerate(protected_blocks):
        final_text = final_text.replace(f"PROTECTEDBLOCK{i}", block)
        
    return final_text


class telegramClient:
    def __init__(self) -> None:
        pass
    
    def send_message(self, text: str, chat_id, original_message_id):
        """ Reply to a message of a user

        Args:
            text (str): the bot's message
            chat_id (int): id of a chat
            original_message_id (int): id of a message to reply to
        """
        payload = {
            "chat_id": chat_id,
            "parse_mode": "MarkdownV2",
            "text": format_with_code_blocks(text),
            "reply_to_message_id": original_message_id
        }
        response = http.request('POST', SEND_MESSAGE_URL, 
                                headers={'Content-Type': 'application/json'},
                                body=json.dumps(payload), timeout=10)
        print(response.data)
    
    def should_reply(self, message:dict):
        """ The function that decides whether the bot should reply to a message or not """
        if (
            (message["from"]["id"] == message["chat"]["id"]) or
            ("reply_to_message" in message and message["reply_to_message"]["from"]["id"] == BOT_ID) or
            ("entities" in message and message["entities"][0]["type"] == "mention" and ("@" + BOT_NAME) in message["text"])
        ):
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
        print(body)
        if (
            "message" in body and
            (not body["message"]["from"]["is_bot"] or body["message"]["from"]["username"]=="GroupAnonymousBot") and
            "forward_from_message_id" not in body["message"]
            ):
            message = body["message"]
            
            chat_id = message["chat"]["id"]
            message_id=message["message_id"]
            if chat_id not in ALLOWED_CHATS:
                print(f"{chat_id} is not allower")
                return

            if "entities" in message and message["entities"][0]["type"]  == "bot_command" and  ("/" + RESET_COMMAND) in message["text"]:
                dynamoDB_client.reset_chat(f"{str(chat_id)}_{str(BOT_ID)}")
                return
            
            # Extract the message of a user
            if "text" in body["message"]:
                user_message = message["text"]
            elif "sticker" in body["message"] and "emoji" in body["message"]["sticker"]:
                user_message = message["sticker"]["emoji"]
            elif "photo" in body["message"] and "caption" in body["message"]:
                user_message = message["caption"]
            else:
                return

            if self.should_reply(message):
                user_message = user_message.replace("@" + BOT_NAME, "")
                bot_message = openai_client.complete_chat(user_message, chat_id, BOT_ID)
                self.send_message(bot_message, chat_id, message_id)
            else:
                previous_messages = dynamoDB_client.load_messages(f"{str(chat_id)}_{str(BOT_ID)}")[-CONTEXT_LENGTH:]
                dynamoDB_client.save_messages(f"{str(chat_id)}_{str(BOT_ID)}", previous_messages[-(CONTEXT_LENGTH-1):] + [{"role": "user", "content": user_message}])