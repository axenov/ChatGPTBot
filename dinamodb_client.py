import os
import boto3

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
            'messages': "\n\n".join(messages),
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
            return []
        else:
            return response['Item']["messages"]["S"].split("\n\n")