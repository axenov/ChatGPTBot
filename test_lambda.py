import os
import json
from lambda_function import lambda_handler

lambda_handler({"body":os.environ["TELEGRAM_MESSAGE"].replace("'", '"')}, {})
