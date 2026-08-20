import requests

API_ROOT = "https://api.telegram.org/bot{token}/{method}"


class TelegramAPI:
    def __init__(self, token):
        self.token = token

    def _call(self, method, **params):
        url = API_ROOT.format(token=self.token, method=method)
        r = requests.post(url, json=params, timeout=30)
        r.raise_for_status()
        data = r.json()
        if not data.get("ok"):
            raise RuntimeError(f"Telegram API error on {method}: {data}")
        return data["result"]

    def get_updates(self, offset=None, timeout=0):
        params = {"timeout": timeout, "allowed_updates": ["message"]}
        if offset is not None:
            params["offset"] = offset
        return self._call("getUpdates", **params)

    def send_message(self, chat_id, text, message_thread_id=None, reply_to_message_id=None):
        params = {"chat_id": chat_id, "text": text}
        if message_thread_id is not None:
            params["message_thread_id"] = message_thread_id
        if reply_to_message_id is not None:
            params["reply_to_message_id"] = reply_to_message_id
        return self._call("sendMessage", **params)
