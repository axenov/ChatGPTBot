import base64
import json
import os
import urllib3
import random
import re
from typing import Any, Dict, List, Optional

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
SEND_PHOTO_URL = 'https://api.telegram.org/bot' + TELEGRAM_TOKEN + '/sendPhoto'
GET_FILE_URL = 'https://api.telegram.org/bot' + TELEGRAM_TOKEN + '/getFile'
FILE_DOWNLOAD_URL = 'https://api.telegram.org/file/bot' + TELEGRAM_TOKEN + '/{}'
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


def _username_from_message(message: Dict[str, Any]) -> str:
    return message.get("from", {}).get("username") or message.get("from", {}).get("first_name") or "unknown_user"


def _download_file(file_id: str) -> Optional[bytes]:
    file_payload = {"file_id": file_id}
    response = http.request('POST', GET_FILE_URL,
                            headers={'Content-Type': 'application/json'},
                            body=json.dumps(file_payload), timeout=10)
    response_data = json.loads(response.data.decode())
    if not response_data.get("ok"):
        return None
    file_path = response_data.get("result", {}).get("file_path")
    if not file_path:
        return None
    file_url = FILE_DOWNLOAD_URL.format(file_path)
    file_response = http.request('GET', file_url, timeout=10)
    if file_response.status != 200:
        return None
    return file_response.data


def _extract_images(message: Dict[str, Any]) -> List[str]:
    images: List[str] = []
    if "photo" in message:
        photo_sizes = message["photo"]
        if isinstance(photo_sizes, list) and photo_sizes:
            selected_photo = photo_sizes[-1]
            file_id = selected_photo.get("file_id")
            if file_id:
                raw = _download_file(file_id)
                if raw:
                    images.append(base64.b64encode(raw).decode("utf-8"))
    return images


def _structured_user_message(message: Dict[str, Any], user_message: str) -> Dict[str, Any]:
    return {
        "role": "user",
        "username": _username_from_message(message),
        "text": user_message,
        "id": str(message.get("message_id")),
        "reply_to_id": str(message.get("reply_to_message", {}).get("message_id")) if message.get("reply_to_message") else None,
        "images": _extract_images(message),
    }


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

    def send_photo(self, chat_id: int, image_bytes: bytes, caption: str, original_message_id: int, mime_type: str = "image/png"):
        # Ensure we send the actual file name in the tuple
        filename = f"image.{mime_type.split('/')[-1]}"
        
        # The 'fields' dict for urllib3's multipart/form-data
        fields = {
            "chat_id": str(chat_id),
            "caption": format_with_code_blocks(caption),
            "reply_to_message_id": str(original_message_id),
            "parse_mode": "MarkdownV2",
            "photo": (filename, image_bytes, mime_type),
        }
        
        # Note: urllib3 request with fields and encode_multipart=False (or implied via POST with fields) 
        # usually handles multipart correctly if we don't set Content-Type manually to JSON.
        # However, verify that we aren't sending 'Content-Type: application/json' which would break it.
        # The PoolManager.request method generates the correct Content-Type header with boundary.
        
        try:
            response = http.request(
                'POST',
                SEND_PHOTO_URL,
                fields=fields
            )
            print(f"Send photo response: {response.data}")
        except Exception as e:
            print(f"Error sending photo: {e}")

    def should_reply(self, message: dict):
        """ The function that decides whether the bot should reply to a message or not """
        entities = message.get("entities") or []
        mentions_bot = any(
            entity.get("type") == "mention" and ("@" + BOT_NAME) in message.get("text", "")
            for entity in entities
        )
        if (
            (message["from"]["id"] == message["chat"]["id"]) or
            ("reply_to_message" in message and message["reply_to_message"].get("from", {}).get("id") == BOT_ID) or
            mentions_bot
        ):
            return True
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
            (not body["message"]["from"]["is_bot"] or body["message"]["from"].get("username") == "GroupAnonymousBot") and
            "forward_from_message_id" not in body["message"]
            ):
            message = body["message"]

            chat_id = message["chat"]["id"]
            message_id = message["message_id"]
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
            elif "photo" in body["message"]:
                user_message = message.get("caption", "Image shared without caption")
            else:
                return

            structured_message = _structured_user_message(message, user_message.replace("@" + BOT_NAME, ""))

            if self.should_reply(message):
                bot_message = openai_client.complete_chat(structured_message, chat_id, BOT_ID)
                reply_text = bot_message.get("text", "").strip()
                if bot_message.get("text"):
                    self.send_message(reply_text, chat_id, message_id)
                if bot_message.get("tool_images_meta"):
                    print(f"[LOG] Found {len(bot_message.get('tool_images_meta'))} images to send.")
                    for image_meta, encoded in zip(bot_message.get("tool_images_meta", []), bot_message.get("images", [])):
                        if not encoded:
                            print("[ERROR] Encoded image data is missing.")
                            continue
                        print(f"[LOG] Sending image to Telegram chat {chat_id}...")
                        image_bytes = base64.b64decode(encoded)
                        caption = image_meta.get("prompt", "").strip() or "Here is your image."
                        self.send_photo(chat_id, image_bytes, caption, message_id, image_meta.get("mime_type", "image/png"))
                        print("[LOG] Image sent successfully.")
            else:
                previous_messages = dynamoDB_client.load_messages(f"{str(chat_id)}_{str(BOT_ID)}")[-CONTEXT_LENGTH:]
                dynamoDB_client.save_messages(f"{str(chat_id)}_{str(BOT_ID)}", previous_messages[-(CONTEXT_LENGTH-1):] + [structured_message])
