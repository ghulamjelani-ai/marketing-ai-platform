"""Local sandbox inbox for development and tests. Nothing is ever delivered to a real address.

It listens like Mailpit: SMTP on localhost:1025 and a web inbox on http://localhost:8025.
Point the backend at it with APP_ENV=development, SMTP_HOST=localhost, SMTP_PORT=1025,
SMTP_USE_TLS=false. Mail is kept in memory only and is gone when this stops.

Run from the project root:
    backend\\venv\\Scripts\\python backend\\tools\\dev_mailbox.py

API (used by the browser tests): GET /api/messages (newest first), DELETE /api/messages.
"""

import argparse
import html
import json
import threading
import time
from email import message_from_bytes, policy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from aiosmtpd.controller import Controller

_lock = threading.Lock()
_messages: list[dict] = []


class _Store:
    async def handle_DATA(self, server, session, envelope):
        parsed = message_from_bytes(envelope.content, policy=policy.default)
        plain = parsed.get_body(preferencelist=("plain",))
        rich = parsed.get_body(preferencelist=("html",))

        with _lock:
            _messages.insert(0, {
                "id": len(_messages) + 1,
                "received": time.strftime("%Y-%m-%d %H:%M:%S"),
                "from": str(parsed.get("From", "")),
                "to": list(envelope.rcpt_tos),
                "subject": str(parsed.get("Subject", "")),
                "text": plain.get_content() if plain else "",
                "html": rich.get_content() if rich else "",
            })

        return "250 Message accepted for delivery"


def _messages_copy() -> list[dict]:
    with _lock:
        return list(_messages)


class _Web(BaseHTTPRequestHandler):
    def _send(self, status, body, content_type):
        data = body.encode()
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path.startswith("/api/messages"):
            self._send(200, json.dumps(_messages_copy()), "application/json")
            return

        rows = "".join(
            f"<article><p class=m>{html.escape(m['received'])} &middot; to {html.escape(', '.join(m['to']))}</p>"
            f"<h2>{html.escape(m['subject'])}</h2><pre>{html.escape(m['text'])}</pre></article>"
            for m in _messages_copy()
        ) or "<p>No messages yet. Request a sign-in code in the app.</p>"

        self._send(
            200,
            "<!doctype html><meta charset=utf-8><meta http-equiv=refresh content=5>"
            "<title>Sandbox inbox</title><style>body{font-family:Arial;max-width:760px;margin:24px auto;padding:0 16px}"
            "article{border:1px solid #ddd;border-radius:8px;padding:12px 16px;margin:12px 0}"
            ".m{color:#777;font-size:13px;margin:0}h2{font-size:17px;margin:6px 0}pre{white-space:pre-wrap}</style>"
            "<h1>Sandbox inbox</h1><p>Development only. These emails were not sent to anyone.</p>" + rows,
            "text/html; charset=utf-8",
        )

    def do_DELETE(self):
        with _lock:
            _messages.clear()

        self._send(200, "{}", "application/json")

    def log_message(self, *args):
        pass


def start(smtp_port: int = 1025, web_port: int = 8025):
    """Starts both servers in the background and returns a function that stops them."""

    controller = Controller(_Store(), hostname="127.0.0.1", port=smtp_port)
    controller.start()

    web = ThreadingHTTPServer(("127.0.0.1", web_port), _Web)
    threading.Thread(target=web.serve_forever, daemon=True).start()

    def stop():
        controller.stop()
        web.shutdown()

    return stop


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--smtp-port", type=int, default=1025)
    parser.add_argument("--web-port", type=int, default=8025)
    args = parser.parse_args()

    stop = start(args.smtp_port, args.web_port)
    print(f"Sandbox inbox: SMTP on localhost:{args.smtp_port}, web inbox at http://localhost:{args.web_port}")
    print("Press Ctrl+C to stop.")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        stop()
