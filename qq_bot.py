"""
QQ 频道机器人 - WebSocket 长连接模式
参考: https://q.qq.com/wiki/develop/gateway/
"""
import asyncio
import json
import threading
import time
import websocket
import logging

APPID = "1903792273"
APPSECRET = "NgmeIhsAJEvOdeS2"
BOT_TOKEN = None  # 先通过 OAuth2 获取

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("qq_bot")


def get_bot_token() -> str:
    """获取 Bot Token"""
    import urllib.request
    url = f"https://api.sgroup.qq.com/oauth2/access_token"
    data = urllib.parse.urlencode({
        "grant_type": "client_credentials",
        "client_id": APPID,
        "client_secret": APPSECRET,
    }).encode()
    req = urllib.request.Request(url, data=data)
    with urllib.request.urlopen(req) as resp:
        result = json.loads(resp.read())
    token = result.get("access_token")
    if not token:
        raise Exception(f"获取token失败: {result}")
    logger.info(f"[QQ] Bot Token 获取成功")
    return token


class QQBot:
    def __init__(self, on_message_callback):
        self.on_message = on_message_callback
        self.token = None
        self.ws = None
        self.session_id = None
        self.sequence = None
        self.url = None
        self.connected = False
        self._thread = None

    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        logger.info("[QQ] 机器人启动中...")

    def _run(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(self._connect_loop())

    async def _connect_loop(self):
        while True:
            try:
                await self._connect()
            except Exception as e:
                logger.error(f"[QQ] 连接断开: {e}，5秒后重连...")
                await asyncio.sleep(5)

    async def _connect(self):
        self.token = get_bot_token()

        # 获取 gateway
        import urllib.request
        req = urllib.request.Request(
            "https://api.sgroup.qq.com/gateway",
            headers={"Authorization": f"Bot {APPID}.{self.token}"}
        )
        with urllib.request.urlopen(req) as resp:
            result = json.loads(resp.read())
        self.url = result["url"]
        logger.info(f"[QQ] Gateway: {self.url}")

        self.ws = websocket.WebSocketApp(
            self.url,
            on_open=self._on_open,
            on_message=self._on_msg,
            on_error=self._on_err,
            on_close=self._on_close,
        )
        self.ws.run_forever(ping_interval=30)

    def _on_open(self, ws):
        logger.info("[QQ] WebSocket 已连接")

    def _on_msg(self, ws, message):
        data = json.loads(message)
        op = data.get("op")

        if op == 0:  # Dispatches
            self.sequence = data.get("s")
            t = data.get("t")
            d = data.get("d", {})

            if t == "READY":
                logger.info(f"[QQ] 机器人已就绪: {d}")

            elif t == "GROUP_AT_MESSAGE_CREATE":  # 频道内@机器人消息
                msg_text = d.get("content", "")
                msg_id = d.get("id")
                group_id = d.get("group_id")
                user_id = d.get("author", {}).get("id")
                self.on_message(
                    text=msg_text,
                    msg_id=msg_id,
                    channel_id=group_id,
                    user_id=user_id,
                )

            elif t == "DIRECT_MESSAGE_CREATE":  # 私信
                msg_text = d.get("content", "")
                msg_id = d.get("id")
                user_id = d.get("author", {}).get("id")
                self.on_message(
                    text=msg_text,
                    msg_id=msg_id,
                    channel_id=user_id,
                    user_id=user_id,
                    is_private=True,
                )

        elif op == 1:  # Heartbeat
            self.ws.send(json.dumps({"op": 1, "d": self.sequence or 0}))

        elif op == 10:  # Hello
            interval = data.get("d", {}).get("heartbeat_interval", 30000) / 1000
            logger.info(f"[QQ] 心跳间隔: {interval}s")
            asyncio.ensure_future(self._heartbeat(interval))

        elif op == 11:  # Heartbeat ACK
            pass

    async def _heartbeat(self, interval):
        while True:
            await asyncio.sleep(interval)
            try:
                self.ws.send(json.dumps({"op": 1, "d": self.sequence or 0}))
            except Exception:
                break

    def _on_err(self, ws, err):
        logger.error(f"[QQ] WebSocket 错误: {err}")

    def _on_close(self, ws, code, reason):
        logger.warning(f"[QQ] 连接关闭: {code} {reason}")
        self.connected = False

    def send_message(self, channel_id: str, content: str):
        """发送频道消息"""
        import urllib.request
        url = f"https://api.sgroup.qq.com/v2/channels/{channel_id}/messages"
        headers = {
            "Authorization": f"Bot {APPID}.{self.token}",
            "Content-Type": "application/json",
        }
        import uuid
        body = json.dumps({
            "content": content,
            "msg_id": str(uuid.uuid4()),
        }).encode()
        req = urllib.request.Request(url, data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req) as resp:
                result = json.loads(resp.read())
                logger.info(f"[QQ] 发送成功: {result}")
        except Exception as e:
            logger.error(f"[QQ] 发送失败: {e}")


# 独立运行测试
if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(__file__).rsplit("/", 1)[0])

    def on_qq_message(text, msg_id, channel_id, user_id, **kwargs):
        print(f"[收到 QQ 消息] channel={channel_id} user={user_id} text={text}")

    bot = QQBot(on_message_callback=on_qq_message)
    bot.start()
    print("按 Ctrl+C 退出")
    while True:
        time.sleep(1)
