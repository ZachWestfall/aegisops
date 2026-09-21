from typing import Optional

try:
    from slack_bolt.async_app import AsyncApp
except Exception:  # pragma: no cover
    AsyncApp = None  # optional dependency

class SlackBot:
    def __init__(self, token: str, signing_secret: str):
        if AsyncApp is None:
            raise RuntimeError("slack_bolt is not installed. `pip install slack_bolt`")
        self.app = AsyncApp(token=token, signing_secret=signing_secret)

    async def post_message(self, channel: str, text: str):
        await self.app.client.chat_postMessage(channel=channel, text=text)
