import os
import json
from lambda_function import lambda_handler

lambda_handler({"body":{"message": json.loads(os.environ["TELEGRAM_MESSAGE"].replace("'", '"'))}}, {})
