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

    def get_updates(self, offset=None, timeout=0, allowed_updates=None):
        params = {
            "timeout": timeout,
            "allowed_updates": allowed_updates or ["message", "callback_query"],
        }
        if offset is not None:
            params["offset"] = offset
        return self._call("getUpdates", **params)

    def send_message(self, chat_id, text, message_thread_id=None, reply_to_message_id=None, reply_markup=None):
        params = {"chat_id": chat_id, "text": text}
        if message_thread_id is not None:
            params["message_thread_id"] = message_thread_id
        if reply_to_message_id is not None:
            params["reply_to_message_id"] = reply_to_message_id
        if reply_markup is not None:
            params["reply_markup"] = reply_markup
        return self._call("sendMessage", **params)

    def edit_message_text(self, chat_id, message_id, text, reply_markup=None):
        params = {"chat_id": chat_id, "message_id": message_id, "text": text}
        params["reply_markup"] = reply_markup if reply_markup is not None else {"inline_keyboard": []}
        return self._call("editMessageText", **params)

    def answer_callback_query(self, callback_query_id, text=None):
        params = {"callback_query_id": callback_query_id}
        if text:
            params["text"] = text
        return self._call("answerCallbackQuery", **params)
