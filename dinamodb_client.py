import os
import boto3
import json

from botocore.exceptions import ClientError

DYNAMODB_TABLE_NAME = os.environ.get('DYNAMODB_TABLE_NAME') 

dynamodb = boto3.resource('dynamodb')

class dynamoDBClient:
    def __init__(self) -> None:
        pass
    
    def save_messages(self, table_id, messages):
        """ Save messages to a DynamoDB table"""
        data = {
            'chat_id': table_id,
            'messages': "\n\n".join([json.dumps(message) for message in messages])
        }
        table = dynamodb.Table(DYNAMODB_TABLE_NAME)
        response = table.put_item(Item=data)
        return response

    def load_messages(self, table_id):
        """ Load messages from a DynamoDB table"""
        table = dynamodb.Table(DYNAMODB_TABLE_NAME)

        try:
            response = table.get_item(Key={'chat_id': table_id})
        except ClientError as e:
            print(e.response['Error']['Message'])
            messages = []
        else:
            if 'Item' in response:
                messages = response['Item']["messages"].split("\n\n")
            else:
                messages =  []
                    
        messages = [json.loads(message) for message in messages]
        return messages