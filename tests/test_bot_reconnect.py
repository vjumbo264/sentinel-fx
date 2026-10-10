"""FIX-A evidence: the bot survives a mid-run websocket drop, requests a FRESH
OTP, reconnects and keeps looping — and always releases the D1 lock.

Runs the real bot.main loop against a local mock Deriv stack (REST accounts +
OTP endpoint, websocket server) and a local mock Worker. The mock WS server
forcibly drops the first connection after the first balance reply.
"""
import asyncio
import json
import os
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
import websockets

os.environ.update({
    "WORKER_URL": "http://127.0.0.1:18901",
    "BOT_SHARED_SECRET": "test-secret",
    "DERIV_BEARER_TOKEN": "test-token",
    "DERIV_APP_ID": "9999",
    "DERIV_REST_BASE": "http://127.0.0.1:18902",
    "DERIV_WS_OVERRIDE": "",          # unused; kept for clarity
    "GH_CHAIN_PAT": "",
    "BOT_WALL_SECONDS": "10",
    "BOT_POLL_SECONDS": "1",
    "BOT_HANDOFF_LEAD_S": "9999",     # never chain during the test
    "BOT_STOP_OPEN_LEAD_S": "9999",
    "NEWS_REFRESH_SECONDS": "9999",
})

STATE = {
    "otp_calls": 0,
    "ws_connections": 0,
    "balances_served": 0,
    "lock_owner": None,
    "unlocked": False,
    "heartbeats": [],
    "logs": [],
    "news_posts": 0,
}


class WorkerMock(BaseHTTPRequestHandler):
    def _reply(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass

    def do_GET(self):
        if self.path == "/api/bot/state":
            self._reply({"settings": {"mode": "demo"}, "pairs": [],
                         "heartbeat": None, "lagos_date": "2026-10-10"})
        elif self.path == "/api/bot/trades/open":
            self._reply({"open": []})
        else:
            self._reply({})

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(n) or b"{}")
        if self.path == "/api/bot/lock":
            STATE["lock_owner"] = body.get("owner")
            self._reply({"acquired": True, "lease_until": "2099-01-01T00:00:00Z"})
        elif self.path == "/api/bot/unlock":
            STATE["unlocked"] = True
            self._reply({"ok": True})
        elif self.path == "/api/bot/heartbeat":
            STATE["heartbeats"].append(body)
            self._reply({"ok": True})
        elif self.path == "/api/bot/log":
            STATE["logs"].append(body)
            self._reply({"ok": True})
        elif self.path == "/api/bot/news":
            STATE["news_posts"] += 1
            self._reply({"ok": True})
        elif self.path == "/api/bot/settings":
            self._reply({"ok": True})
        else:
            self._reply({"ok": True})


class DerivRestMock(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _reply(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/trading/v1/options/accounts":
            self._reply({"data": [{"account_id": "VRTC123456",
                                   "account_type": "demo",
                                   "currency": "USD"}]})
        else:
            self._reply({}, 404)

    def do_POST(self):
        if self.path.endswith("/otp"):
            STATE["otp_calls"] += 1
            self._reply({"data": {"url": "ws://127.0.0.1:18903/ws"}})
        else:
            self._reply({}, 404)


async def ws_handler(ws):
    STATE["ws_connections"] += 1
    conn_no = STATE["ws_connections"]
    try:
        async for raw in ws:
            msg = json.loads(raw)
            if "balance" in msg:
                STATE["balances_served"] += 1
                await ws.send(json.dumps({
                    "req_id": msg.get("req_id"),
                    "balance": {"balance": 1000.0, "currency": "USD",
                                "loginid": "VRTC123456"}}))
                if conn_no == 1:
                    # simulate the production failure: drop mid-run, no close frame
                    await ws.close(code=1006)
                    return
            elif "ping" in msg:
                await ws.send(json.dumps({"req_id": msg.get("req_id"),
                                          "ping": "pong"}))
            else:
                await ws.send(json.dumps({"req_id": msg.get("req_id"),
                                          "msg_type": "ok"}))
    except websockets.exceptions.ConnectionClosed:
        pass


@pytest.fixture(scope="module")
def servers():
    w = ThreadingHTTPServer(("127.0.0.1", 18901), WorkerMock)
    d = ThreadingHTTPServer(("127.0.0.1", 18902), DerivRestMock)
    threading.Thread(target=w.serve_forever, daemon=True).start()
    threading.Thread(target=d.serve_forever, daemon=True).start()

    loop = asyncio.new_event_loop()
    holder = {}

    def run_ws():
        asyncio.set_event_loop(loop)
        async def boot():
            holder["srv"] = await websockets.serve(ws_handler, "127.0.0.1", 18903)
        loop.run_until_complete(boot())
        loop.run_forever()

    threading.Thread(target=run_ws, daemon=True).start()
    time.sleep(0.8)
    yield
    w.shutdown()
    d.shutdown()
    loop.call_soon_threadsafe(loop.stop)


def test_reconnect_with_fresh_otp_and_lock_release(servers, monkeypatch):
    import bot.main as bm

    async def fake_news(self):
        self.events = []
        self.news_ts = time.time()

    monkeypatch.setattr(bm.Bot, "refresh_news", fake_news)
    asyncio.run(bm.main())

    assert STATE["otp_calls"] >= 2, \
        f"expected a FRESH OTP after the drop, got {STATE['otp_calls']}"
    assert STATE["ws_connections"] >= 2, \
        f"expected a reconnect, got {STATE['ws_connections']} connection(s)"
    assert STATE["balances_served"] >= 3, \
        "bot did not continue its loop after reconnecting"
    assert STATE["unlocked"] is True, "D1 lock was not released at end of run"
    notes = [h.get("note") for h in STATE["heartbeats"]]
    assert "reconnecting" in notes, "no 'reconnecting' heartbeat was emitted"
