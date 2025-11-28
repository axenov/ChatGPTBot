import base64
import os
import json
import uuid
import re
from typing import Any, Dict, List, Optional

from google import genai
from google.genai import types
from openai import OpenAI

from dinamodb_client import dynamoDBClient

OPENAI_KEY = os.environ.get('OPENAI_KEY')
OPENAI_MODEL = os.environ.get('OPENAI_MODEL')
SYSTEM_PROMPT = os.environ.get('SYSTEM_PROMPT')
STYLE_PROMPT = os.environ.get('STYLE_PROMPT')
CONTEXT_LENGTH = int(os.environ.get('CONTEXT_LENGTH'))
TEMPERATURE = float(os.environ.get('TEMPERATURE'))
MAX_COMPLETION_TOKENS = int(os.environ.get('MAX_TOKENS'))
BOT_NAME = os.environ.get('BOT_NAME', 'assistant')
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
GEMINI_IMAGE_MODEL = os.environ.get('GEMINI_IMAGE_MODEL', 'gemini-2.5-flash-image')
IMAGE_MIME_TYPE = os.environ.get('IMAGE_MIME_TYPE', 'image/png')


def _text_from_content(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                parts.append(item.get("text", ""))
        return "\n".join(parts)
    return str(content)


def _strip_prefix(text: str) -> str:
    cleaned = text.strip()
    cleaned = re.sub(r"^\[msg:[^\]]+\]\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"^@[^\n]*?\):\s*", "", cleaned)
    cleaned = re.sub(r"^@[^\n]*?:\s*", "", cleaned)
    reply_prefix_pattern = r"^(?:@?[^:]{0,80}?\b(?:reply|ответ)[^:]{0,40}:)\s*"
    cleaned = re.sub(reply_prefix_pattern, "", cleaned, flags=re.IGNORECASE)
    return cleaned


SUPPORTED_ASPECT_RATIOS = {
    "1:1",
    "2:3",
    "3:2",
    "3:4",
    "4:3",
    "4:5",
    "5:4",
    "9:16",
    "16:9",
    "21:9",
}


def _normalize_aspect_ratio(aspect_ratio: Optional[str]) -> Optional[str]:
    if not aspect_ratio:
        return None
    candidate = str(aspect_ratio).strip().lower()
    return candidate if candidate in SUPPORTED_ASPECT_RATIOS else "1:1"


class openaiClient:
    def __init__(self, dynamoDB_client: dynamoDBClient) -> None:
        self.client = OpenAI(api_key=OPENAI_KEY)
        self.dynamoDB_client = dynamoDB_client

    def _chat_key(self, chat_id: int, bot_id: int) -> str:
        return f"{str(chat_id)}_{str(bot_id)}"

    def _format_message_for_model(self, message: Dict[str, Any], include_style_prompt: bool = False) -> Dict[str, Any]:
        message_id = message.get("id")
        reply_id = message.get("reply_to_id")
        if reply_id and reply_id == message_id:
            reply_id = None

        # Surface both message ID and reply target to help the model follow threading.
        prefix_parts = [f"@{message.get('username', 'user')} said (message {message_id})"]
        if reply_id:
            prefix_parts.append(f"in reply to message {reply_id}")
        prefix = " ".join(prefix_parts)
        text_body = message.get("text", "")
        if include_style_prompt and STYLE_PROMPT:
            text_body = f"{text_body}\n{STYLE_PROMPT}"
        content_parts: List[Dict[str, Any]] = [{"type": "text", "text": f"{prefix}:\n{text_body}"}]
        for image in message.get("images", []):
            content_parts.append({
                "type": "image_url",
                "image_url": {"url": f"data:{IMAGE_MIME_TYPE};base64,{image}"}
            })
        return {"role": message.get("role", "user"), "content": content_parts}

    def _trim_and_save_messages(self, chat_key: str, messages: List[Dict[str, Any]]):
        # Filter out heavy image data before saving history to DynamoDB
        messages_to_save = []
        for msg in messages:
            msg_copy = msg.copy()
            # Remove base64 image data to avoid exceeding DynamoDB item size limits
            if "images" in msg_copy:
                msg_copy["images"] = []
            messages_to_save.append(msg_copy)

        trimmed = messages_to_save[-CONTEXT_LENGTH:]
        self.dynamoDB_client.save_messages(chat_key, trimmed)

    def _build_tools(self) -> List[Dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": "generate_image",
                    "description": "Create an illustrative image with Gemini based on the chat context.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "prompt": {
                                "type": "string",
                                "description": "Target visual description to render."
                            },
                            "aspect_ratio": {
                                "type": "string",
                                "description": "One of the Gemini-supported aspect ratios, such as 1:1 or 16:9.",
                            }
                        },
                        "required": ["prompt"],
                    },
                },
            }
        ]

    def _summarize_conversation(self, messages: List[Dict[str, Any]]) -> str:
        lines = []
        for message in messages:
            prefix = f"@{message.get('username', 'user')} (message {message.get('id')})"
            reply_id = message.get("reply_to_id")
            if reply_id and reply_id != message.get("id"):
                prefix += f" replying to {reply_id}"
            text_body = message.get("text", "")
            lines.append(f"{prefix}: {text_body}")
        return "\n".join(lines)

    def _generate_image(self, prompt: str, aspect_ratio: Optional[str], display_prompt: Optional[str]) -> Optional[Dict[str, Any]]:
        normalized_ratio = _normalize_aspect_ratio(aspect_ratio)
        try:
            client = genai.Client(api_key=GEMINI_API_KEY)
            response = client.models.generate_content(
                model=GEMINI_IMAGE_MODEL,
                contents=[prompt],
                config=types.GenerateContentConfig(
                    image_config=types.ImageConfig(
                        aspect_ratio=normalized_ratio,
                    ),
                ),
            )
        except Exception as exc:
            print(f"Gemini generation failed: {exc}")
            return None
        if not response:
            return None
        
        # https://ai.google.dev/gemini-api/docs/image-generation#python_23
        if hasattr(response, "parts"):
            for part in response.parts:
                if part.inline_data:
                    return {
                        "data": part.inline_data.data,
                        "mime_type": part.inline_data.mime_type or IMAGE_MIME_TYPE,
                        "prompt": prompt,
                        "display_prompt": display_prompt or prompt,
                    }

        return None

    def _handle_tool_calls(self, tool_calls, conversation_messages: List[Dict[str, Any]], base_messages):
        tool_responses = []
        generated_images: List[Dict[str, Any]] = []
        for tool_call in tool_calls:
            if tool_call.function.name == "generate_image":
                args = json.loads(tool_call.function.arguments)
                prompt = args.get("prompt", "")
                aspect_ratio = args.get("aspect_ratio")
                prompt_with_history = f"{prompt}\n\nConversation summary:\n{self._summarize_conversation(conversation_messages)}"
                image_result = self._generate_image(prompt_with_history, aspect_ratio, prompt)
                if image_result:
                    generated_images.append(image_result)
                    tool_responses.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": json.dumps({
                            "status": "image_generated",
                            "prompt": prompt_with_history,
                            "mime_type": image_result.get("mime_type", IMAGE_MIME_TYPE)
                        }),
                    })
                else:
                    tool_responses.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": json.dumps({
                            "status": "failed",
                            "reason": "Image generation returned no data"
                        }),
                    })
        if not tool_responses:
            return None, [], base_messages
        follow_up_messages = base_messages + tool_responses
        response = self.client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=follow_up_messages,
            temperature=TEMPERATURE,
            max_completion_tokens=MAX_COMPLETION_TOKENS,
            tools=self._build_tools(),
        )
        return response.choices[0].message, generated_images, follow_up_messages

    def remember_only(self, chat_id: int, bot_id: int, message: Dict[str, Any]):
        chat_key = self._chat_key(chat_id, bot_id)
        previous_messages = self.dynamoDB_client.load_messages(chat_key)
        updated_messages = previous_messages + [message]
        self._trim_and_save_messages(chat_key, updated_messages)

    def complete_chat(self, user_message: Dict[str, Any], chat_id: int, bot_id: int):
        """Generate the bot's answer to a user's message"""
        chat_key = self._chat_key(chat_id, bot_id)
        previous_messages = self.dynamoDB_client.load_messages(chat_key)
        limited_previous = previous_messages[-CONTEXT_LENGTH:]
        formatted_history = [self._format_message_for_model(m) for m in limited_previous]
        tool_instruction = "If the user asks to create or render an image, always call the `generate_image` tool and do not describe the JSON yourself. Return concise, human-friendly answers without technical prefixes."
        model_messages = [
            {"role": "system", "content": [{"type": "text", "text": SYSTEM_PROMPT}]},
            {"role": "system", "content": [{"type": "text", "text": tool_instruction}]},
        ] + formatted_history + [self._format_message_for_model(user_message, include_style_prompt=True)]

        response = self.client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=model_messages,
            temperature=TEMPERATURE,
            max_completion_tokens=MAX_COMPLETION_TOKENS,
            tools=self._build_tools(),
            tool_choice="auto",
        )

        first_choice = response.choices[0].message
        assistant_message = first_choice
        tool_generated_images: List[Dict[str, Any]] = []
        if first_choice.tool_calls:
            assistant_message, tool_generated_images, _ = self._handle_tool_calls(
                first_choice.tool_calls,
                limited_previous + [user_message],
                model_messages + [first_choice.model_dump()]
            )

        assistant_text = _strip_prefix(_text_from_content(assistant_message.content))
        assistant_images = []
        for image_data in tool_generated_images:
             data = image_data.get("data")
             if isinstance(data, (bytes, bytearray)):
                  assistant_images.append(base64.b64encode(data).decode("utf-8"))
             elif isinstance(data, str):
                  assistant_images.append(data)

        assistant_metadata = [
            {
                "prompt": _strip_prefix(image_data.get("display_prompt", "") or image_data.get("prompt", "")),
                "mime_type": image_data.get("mime_type", IMAGE_MIME_TYPE),
            }
            for image_data in tool_generated_images
        ]
        assistant_id = f"{user_message.get('id', uuid.uuid4().hex)}-assistant"
        reply_to_id = user_message.get("id")
        if reply_to_id == assistant_id:
            reply_to_id = None
        assistant_record = {
            "role": "assistant",
            "username": BOT_NAME,
            "text": assistant_text,
            "id": assistant_id,
            "reply_to_id": reply_to_id,
            "images": assistant_images,
            "tool_images_meta": assistant_metadata,
        }

        updated_history = limited_previous + [user_message, assistant_record]
        self._trim_and_save_messages(chat_key, updated_history)

        return assistant_record
