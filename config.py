import os

API_KEY = os.environ.get("MINILOBSTER_API_KEY", "")
ANTHROPIC_BASE_URL = "https://api.minimaxi.com/anthropic"
MODEL = "claude-sonnet-4-6"

AVAILABLE_MODELS = [
    {"id": "MiniMax-2.7-Flash", "name": "MiniMax-2.7-Flash"},
]
