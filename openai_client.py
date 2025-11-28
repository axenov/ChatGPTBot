import base64
import os
import json
import uuid
import re
from datetime import datetime, timezone
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
        # If this is a persisted tool call or tool response, return it directly.
        # They are stored as raw dicts from OpenAI API (role='tool' or role='assistant' with tool_calls)
        if message.get("role") == "tool":
            return {
                "role": "tool",
                "tool_call_id": message.get("tool_call_id"),
                "content": message.get("content")
            }
        
        if message.get("role") == "assistant" and message.get("tool_calls"):
             # This is a stored assistant message that made tool calls.
             # We need to reconstruct it properly for the API.
             return {
                 "role": "assistant",
                 "content": message.get("content"),
                 "tool_calls": message.get("tool_calls")
             }

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
            if "images" in msg_copy and msg_copy["images"]:
                msg_copy["images"] = []
                # Add metadata phrase if user attached an image
                if msg_copy.get("role") == "user":
                    msg_copy["text"] = f"{msg_copy.get('text', '')} [User attached an image]"
                # Add metadata phrase if assistant generated an image
                elif msg_copy.get("role") == "assistant" and msg_copy.get("tool_images_meta"):
                     msg_copy["text"] = f"{msg_copy.get('text', '')} [Assistant generated an image]"

            messages_to_save.append(msg_copy)

        # Trim to CONTEXT_LENGTH but ensure we don't cut in the middle of a tool call sequence
        trimmed = messages_to_save[-CONTEXT_LENGTH:]
        
        # If the first message is a tool response or orphaned, skip until we find a clean start
        # A clean start is: user message, or assistant message without tool_calls
        while trimmed and (
            trimmed[0].get("role") == "tool" or 
            (trimmed[0].get("role") == "assistant" and trimmed[0].get("tool_calls"))
        ):
            trimmed = trimmed[1:]
        
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
        print(f"[LOG] Starting Gemini image generation. Prompt: {prompt[:200]}... Ratio: {normalized_ratio}")
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
            print("[LOG] Gemini API response received.")
        except Exception as exc:
            print(f"[ERROR] Gemini generation failed: {exc}")
            return None
        if not response:
            print("[ERROR] No response object from Gemini.")
            return None
        
        # Log full response details for debugging
        print(f"[DEBUG] Response type: {type(response)}")
        print(f"[DEBUG] Response has parts: {hasattr(response, 'parts')}")
        if hasattr(response, 'candidates') and response.candidates:
            for i, candidate in enumerate(response.candidates):
                print(f"[DEBUG] Candidate {i}: finish_reason={getattr(candidate, 'finish_reason', 'N/A')}")
                if hasattr(candidate, 'content') and candidate.content:
                    print(f"[DEBUG] Candidate {i} content parts: {len(candidate.content.parts) if candidate.content.parts else 0}")
                    for j, part in enumerate(candidate.content.parts or []):
                        print(f"[DEBUG] Part {j}: has text={hasattr(part, 'text') and part.text is not None}, has inline_data={hasattr(part, 'inline_data') and part.inline_data is not None}")
                        if hasattr(part, 'text') and part.text:
                            print(f"[DEBUG] Part {j} text: {part.text[:200] if part.text else 'None'}...")
        
        # Check for blocked content
        if hasattr(response, 'prompt_feedback'):
            print(f"[DEBUG] Prompt feedback: {response.prompt_feedback}")
        
        # https://ai.google.dev/gemini-api/docs/image-generation#python_23
        if hasattr(response, "parts"):
            for part in response.parts:
                if part.inline_data:
                    print(f"[LOG] Image data found. Size: {len(part.inline_data.data)} bytes.")
                    return {
                        "data": part.inline_data.data,
                        "mime_type": part.inline_data.mime_type or IMAGE_MIME_TYPE,
                        "prompt": prompt,
                        "display_prompt": display_prompt or prompt,
                    }
        print("[ERROR] No image parts found in Gemini response.")
        return None

    def _handle_tool_calls(self, tool_calls, conversation_messages: List[Dict[str, Any]], base_messages):
        print(f"[LOG] Handling {len(tool_calls)} tool calls.")
        tool_responses = []
        generated_images: List[Dict[str, Any]] = []
        for tool_call in tool_calls:
            if tool_call.function.name == "generate_image":
                print("[LOG] Processing generate_image tool call.")
                args = json.loads(tool_call.function.arguments)
                prompt = args.get("prompt", "")
                aspect_ratio = args.get("aspect_ratio")
                # Send only the clean image description to Gemini, without conversation context
                # The conversation context was confusing Gemini into responding with text instead of generating an image
                image_result = self._generate_image(prompt, aspect_ratio, prompt)
                if image_result:
                    print("[LOG] Image generation successful.")
                    generated_images.append(image_result)
                    tool_responses.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": json.dumps({
                            "status": "image_generated",
                            "prompt": prompt,
                            "mime_type": image_result.get("mime_type", IMAGE_MIME_TYPE)
                        }),
                    })
                else:
                    print("[ERROR] Image generation failed or returned no result.")
                    tool_responses.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": json.dumps({
                            "status": "failed",
                            "reason": "Image generation returned no data"
                        }),
                    })
        if not tool_responses:
            print("[LOG] No tool responses generated.")
            return None, [], base_messages
        follow_up_messages = base_messages + tool_responses
        print("[LOG] Sending tool outputs back to OpenAI model.")
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

    def _filter_valid_tool_messages(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Filter out orphaned tool messages that don't have a matching tool_call in the preceding assistant message.
        OpenAI requires that every 'tool' message must reference a tool_call_id that exists in the previous assistant's tool_calls.
        """
        result = []
        current_valid_tool_call_ids = set()
        
        for msg in messages:
            role = msg.get("role")
            
            if role == "assistant" and msg.get("tool_calls"):
                # This assistant message has tool_calls - collect valid IDs
                current_valid_tool_call_ids = {tc.get("id") for tc in msg.get("tool_calls", []) if tc.get("id")}
                result.append(msg)
            elif role == "tool":
                # Only include tool response if its tool_call_id is in the valid set
                tool_call_id = msg.get("tool_call_id")
                if tool_call_id and tool_call_id in current_valid_tool_call_ids:
                    result.append(msg)
                else:
                    print(f"[WARNING] Skipping orphaned tool message with tool_call_id={tool_call_id}")
            else:
                # Regular user/assistant message - reset the valid tool call IDs
                current_valid_tool_call_ids = set()
                result.append(msg)
        
        return result

    def complete_chat(self, user_message: Dict[str, Any], chat_id: int, bot_id: int):
        """Generate the bot's answer to a user's message"""
        chat_key = self._chat_key(chat_id, bot_id)
        previous_messages = self.dynamoDB_client.load_messages(chat_key)
        limited_previous = previous_messages[-CONTEXT_LENGTH:]
        
        # Filter out orphaned tool messages that would cause OpenAI API errors
        limited_previous = self._filter_valid_tool_messages(limited_previous)

        formatted_history = [self._format_message_for_model(m) for m in limited_previous]
        tool_instruction = "TOOL USAGE INSTRUCTIONS: If any member of the chat asks to create, draw or render an image or a picture in any language, always call the `generate_image` tool and do not describe the JSON yourself or answer with some text. Otherwise return concise, human-friendly answers without technical prefixes. "
        current_time = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S %Z")
        time_instruction = f"Current date and time (UTC): {current_time}. Use this to keep your answers time-aware."
        model_messages = [
            {"role": "system", "content": [{"type": "text", "text": SYSTEM_PROMPT}]},
            {"role": "system", "content": [{"type": "text", "text": time_instruction}]},
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
        
        # Collect tool calls and responses for persistence
        tool_call_records = []
        if first_choice.tool_calls:
            # 1. Add the assistant's tool call message to history
            tool_call_records.append(first_choice.model_dump())
            
            assistant_message, tool_generated_images, follow_up_messages = self._handle_tool_calls(
                first_choice.tool_calls,
                limited_previous + [user_message],
                model_messages + [first_choice.model_dump()]
            )
            
            # 2. Add the tool response messages to history (from follow_up_messages)
            # follow_up_messages contains [..., tool_call_msg, tool_response_msg_1, tool_response_msg_2, ...]
            # We want to capture the tool responses.
            # The last message in follow_up_messages is NOT the final assistant response yet, it's the input to the final completion.
            # So we can scan follow_up_messages for role='tool'
            for msg in follow_up_messages:
                if isinstance(msg, dict) and msg.get("role") == "tool":
                     tool_call_records.append(msg)

        assistant_text = _strip_prefix(_text_from_content(assistant_message.content))
        
        # Remove accidental metadata strings from the generated text if they appear
        assistant_text = assistant_text.replace("[User attached an image]", "").replace("[Assistant generated an image]", "").strip()

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
        
        # This is the text message from the LLM (Telegram message #1)
        assistant_record = {
            "role": "assistant",
            "username": BOT_NAME,
            "text": assistant_text,
            "id": assistant_id,
            "reply_to_id": reply_to_id,
            "images": assistant_images,
            "tool_images_meta": assistant_metadata,
        }

        # Prepare history to save: User -> Tools (if any) -> Assistant Text -> Image Messages (if any)
        history_to_save = limited_previous + [user_message]
        
        for tool_msg in tool_call_records:
             history_to_save.append(tool_msg)
             
        history_to_save.append(assistant_record)
        
        # For each generated image, create a separate "image message" record in history
        # This represents Telegram message #2 (the photo with caption)
        for idx, image_meta in enumerate(assistant_metadata):
            image_caption = image_meta.get("prompt", "").strip() or "Here is your image."
            image_message_record = {
                "role": "assistant",
                "username": BOT_NAME,
                "text": f"{image_caption} [Assistant generated an image]",
                "id": f"{assistant_id}-image-{idx}",
                "reply_to_id": reply_to_id,
                "images": [],  # Don't store actual image data
            }
            history_to_save.append(image_message_record)
        
        self._trim_and_save_messages(chat_key, history_to_save)

        return assistant_record
