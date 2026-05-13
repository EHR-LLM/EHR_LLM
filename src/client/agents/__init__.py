try:
    from .fastchat_client import FastChatAgent
except ImportError:
    FastChatAgent = None  # fastchat/torch not available; only HTTPAgent will work
from .http_agent import HTTPAgent
