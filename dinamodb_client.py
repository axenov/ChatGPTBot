import os
import boto3
import json
from typing import List, Dict, Any

from botocore.exceptions import ClientError

DYNAMODB_TABLE_NAME = os.environ.get('DYNAMODB_TABLE_NAME')

dynamodb = boto3.resource('dynamodb')


class dynamoDBClient:
    def __init__(self) -> None:
        pass

    def _encode_messages(self, messages: List[Dict[str, Any]]):
        return "\n\n".join([json.dumps(message) for message in messages])

    def save_messages(self, table_id, messages: List[Dict[str, Any]]):
        """Save messages to a DynamoDB table"""
        data = {
            'chat_id': table_id,
            'messages': self._encode_messages(messages)
        }
        table = dynamodb.Table(DYNAMODB_TABLE_NAME)
        response = table.put_item(Item=data)
        return response

    def _decode_message(self, raw_message: str, index: int) -> Dict[str, Any]:
        try:
            message_obj = json.loads(raw_message)
        except json.JSONDecodeError:
            message_obj = {
                "role": "user",
                "username": "legacy_user",
                "text": raw_message,
                "id": f"legacy-{index}",
                "reply_to_id": None,
                "images": []
            }
        if isinstance(message_obj, str):
            message_obj = {
                "role": "user",
                "username": "legacy_user",
                "text": message_obj,
                "id": f"legacy-{index}",
                "reply_to_id": None,
                "images": []
            }
        message_obj.setdefault("id", f"legacy-{index}")
        message_obj.setdefault("reply_to_id", None)
        message_obj.setdefault("username", "legacy_user")
        message_obj.setdefault("text", "")
        message_obj.setdefault("images", [])
        message_obj.setdefault("role", "user")
        return message_obj

    def load_messages(self, table_id) -> List[Dict[str, Any]]:
        """Load messages from a DynamoDB table"""
        table = dynamodb.Table(DYNAMODB_TABLE_NAME)

        try:
            response = table.get_item(Key={'chat_id': table_id})
        except ClientError as e:
            print(e.response['Error']['Message'])
            messages: List[Dict[str, Any]] = []
        else:
            if 'Item' in response:
                raw_messages = response['Item']["messages"].split("\n\n")
                messages = [self._decode_message(message, index) for index, message in enumerate(raw_messages)]
            else:
                messages = []

        return messages

    def reset_chat(self, table_id):
        """Reset a chat in a DynamoDB table"""
        table = dynamodb.Table(DYNAMODB_TABLE_NAME)
        response = table.delete_item(Key={'chat_id': table_id})
        return response
