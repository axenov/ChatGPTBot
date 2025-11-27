import base64
import os
import json
import uuid
import re
from typing import Any, Dict, List, Optional

from google import generativeai as genai
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


def _strip_prefix_markup(text: str) -> str:
    if not text:
        return text
    cleaned = re.sub(r"\[msg:[^\]]+\]\s*(\([^)]*\))?\s*", "", text).strip()
    return cleaned or text


class openaiClient:
    def __init__(self, dynamoDB_client: dynamoDBClient) -> None:
        self.client = OpenAI(api_key=OPENAI_KEY)
        if GEMINI_API_KEY:
            genai.configure(api_key=GEMINI_API_KEY)
        else:
            print("GEMINI_API_KEY is not set; image generation tool calls will fail.")
        self.dynamoDB_client = dynamoDB_client

    def _chat_key(self, chat_id: int, bot_id: int) -> str:
        return f"{str(chat_id)}_{str(bot_id)}"

    def _format_message_for_model(self, message: Dict[str, Any], include_style_prompt: bool = False) -> Dict[str, Any]:
        prefix = f"[msg:{message.get('id')}] @{message.get('username', 'user')}"
        if message.get("reply_to_id"):
            prefix += f" (in reply to msg:{message['reply_to_id']})"
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
        trimmed = messages[-CONTEXT_LENGTH:]
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
                            "size": {
                                "type": "string",
                                "description": "Preferred image size, such as 1024x1024.",
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
            prefix = f"[msg:{message.get('id')}] @{message.get('username', 'user')}"
            if message.get("reply_to_id"):
                prefix += f" replying to msg:{message['reply_to_id']}"
            text_body = message.get("text", "")
            lines.append(f"{prefix}: {text_body}")
        return "\n".join(lines)

    def _generate_image(self, prompt: str, size: Optional[str]) -> Optional[Dict[str, Any]]:
        model = genai.GenerativeModel(GEMINI_IMAGE_MODEL)
        generation_config: Dict[str, Any] = {"response_mime_type": IMAGE_MIME_TYPE}
        if size:
            generation_config["image_size"] = size
        try:
            response = model.generate_content(
                [prompt],
                generation_config=generation_config,
            )
        except Exception as exc:
            print(f"Gemini generation failed: {exc}")
            return None
        if not response or not response.candidates:
            return None
        candidate = response.candidates[0]
        if not candidate.content or not candidate.content.parts:
            return None
        for part in candidate.content.parts:
            if hasattr(part, "inline_data") and part.inline_data and getattr(part.inline_data, "data", None):
                return {
                    "data": part.inline_data.data,
                    "mime_type": part.inline_data.mime_type or IMAGE_MIME_TYPE,
                    "prompt": prompt
                }
        return None

    def _handle_tool_calls(self, tool_calls, conversation_messages: List[Dict[str, Any]], base_messages):
        tool_responses = []
        generated_images: List[Dict[str, Any]] = []
        for tool_call in tool_calls:
            if tool_call.function.name == "generate_image":
                args = json.loads(tool_call.function.arguments)
                prompt = args.get("prompt", "")
                size = args.get("size")
                prompt_with_history = f"{prompt}\n\nConversation summary:\n{self._summarize_conversation(conversation_messages)}"
                image_result = self._generate_image(prompt_with_history, size)
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
            tool_choice="auto",
            tools=self._build_tools(),
        )
        return response.choices[0].message, generated_images, follow_up_messages

    def _infer_image_prompt_from_text(self, assistant_text: str) -> Optional[Dict[str, Any]]:
        """
        Try to extract a tool-friendly payload from a text-only response that
        should have triggered an image tool call.
        """
        candidates = [assistant_text]
        code_block = re.search(r"```(?:json)?\s*(.*?)\s*```", assistant_text, re.DOTALL)
        if code_block:
            candidates.append(code_block.group(1))

        for candidate in candidates:
            try:
                data = json.loads(candidate)
            except Exception:
                continue
            if not isinstance(data, dict):
                continue
            prompt = data.get("prompt") or data.get("image_prompt") or data.get("text")
            if prompt:
                return {"prompt": prompt, "size": data.get("size")}
        return None

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
        model_messages = [{"role": "system", "content": [{"type": "text", "text": SYSTEM_PROMPT}]}] + formatted_history + [
            self._format_message_for_model(user_message, include_style_prompt=True)
        ]

        response = self.client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=model_messages,
            temperature=TEMPERATURE,
            max_completion_tokens=MAX_COMPLETION_TOKENS,
            tool_choice="auto",
            tools=self._build_tools(),
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

        assistant_text = _text_from_content(assistant_message.content)

        inferred_image = None
        if not tool_generated_images:
            inferred_image = self._infer_image_prompt_from_text(assistant_text)
            if inferred_image:
                prompt_with_history = f"{inferred_image['prompt']}\n\nConversation summary:\n{self._summarize_conversation(limited_previous + [user_message])}"
                image_result = self._generate_image(prompt_with_history, inferred_image.get("size"))
                if image_result:
                    tool_generated_images.append(image_result)
                    assistant_text = assistant_text.split("```", 1)[0].strip() or "Image generated from your request."

        assistant_text = _strip_prefix_markup(assistant_text)

        assistant_images: List[str] = []
        assistant_metadata: List[Dict[str, Any]] = []
        for image_data in tool_generated_images:
            encoded = (
                base64.b64encode(image_data["data"]).decode("utf-8")
                if isinstance(image_data.get("data"), (bytes, bytearray))
                else image_data.get("data")
            )
            if not encoded:
                continue
            assistant_images.append(encoded)
            assistant_metadata.append({
                "prompt": image_data.get("prompt"),
                "mime_type": image_data.get("mime_type", IMAGE_MIME_TYPE),
            })
        assistant_record = {
            "role": "assistant",
            "username": BOT_NAME,
            "text": assistant_text,
            "id": f"{user_message.get('id', uuid.uuid4().hex)}-assistant",
            "reply_to_id": user_message.get("id"),
            "images": assistant_images,
            "tool_images_meta": assistant_metadata,
        }

        updated_history = limited_previous + [user_message, assistant_record]
        self._trim_and_save_messages(chat_key, updated_history)

        return assistant_record
