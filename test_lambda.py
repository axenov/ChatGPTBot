import os
from lambda_function import lambda_handler
lambda_handler({"body": {"message": {"from": {"is_bot": False}, "chat": {"id": os.environ['TELEGRAM_CHAT_ID']}, "text": "test bot"}}}, {})
