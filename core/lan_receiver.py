"""
Secure Mobile Mic Receiver (Wi-Fi HTTPS / WSS LAN Bridge).
Generates an automatic local SSL certificate using 'cryptography'
so Android Chrome and iOS Safari allow 'navigator.mediaDevices.getUserMedia'
over local LAN IPs without security blocks.
"""

import asyncio
import datetime
import json
import os
import socket
import ssl
import threading
from typing import Callable, Optional, Tuple
import websockets
from http.server import HTTPServer, BaseHTTPRequestHandler

from core.paths import resolve_path

try:
    from cryptography import x509
    from cryptography.x509.oid import NameOID
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    CRYPTO_AVAILABLE = True
except ImportError:
    CRYPTO_AVAILABLE = False


def get_local_lan_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def ensure_ssl_certificates(lan_ip: str) -> Tuple[str, str]:
    """Generates a self-signed SSL cert/key for HTTPS LAN access if missing."""
    ssl_dir = resolve_path("config/ssl")
    os.makedirs(ssl_dir, exist_ok=True)
    cert_path = os.path.join(ssl_dir, "cert.pem")
    key_path = os.path.join(ssl_dir, "key.pem")

    if os.path.exists(cert_path) and os.path.exists(key_path):
        return cert_path, key_path

    if not CRYPTO_AVAILABLE:
        return "", ""

    try:
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        subject = issuer = x509.Name([
            x509.NameAttribute(NameOID.COMMON_NAME, lan_ip),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "SmartHomeVoiceHub")
        ])

        cert = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(issuer)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(datetime.datetime.now(datetime.timezone.utc))
            .not_valid_after(datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=365))
            .sign(key, hashes.SHA256())
        )

        with open(key_path, "wb") as f:
            f.write(key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.TraditionalOpenSSL,
                encryption_algorithm=serialization.NoEncryption()
            ))

        with open(cert_path, "wb") as f:
            f.write(cert.public_bytes(serialization.Encoding.PEM))

        return cert_path, key_path
    except Exception as e:
        print(f"[SSL Gen Error] {e}")
        return "", ""


MOBILE_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
  <title>Smart Home Mobile Mic (HTTPS Secure)</title>
  <style>
    body {
      margin: 0; padding: 20px; background: #0d1117; color: #f0f6fc;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      text-align: center; display: flex; flex-direction: column; align-items: center; min-height: 100vh;
      box-sizing: border-box;
    }
    h1 { font-size: 22px; margin-bottom: 5px; color: #58a6ff; }
    p { font-size: 13px; color: #8b949e; margin-top: 0; }
    .status-badge {
      display: inline-block; padding: 6px 14px; border-radius: 20px; font-size: 13px;
      font-weight: bold; background: #238636; margin-bottom: 25px;
    }
    .mic-btn {
      width: 170px; height: 170px; border-radius: 50%; border: none;
      background: linear-gradient(135deg, #1f6feb, #238636); color: white; font-size: 18px;
      font-weight: bold; cursor: pointer; box-shadow: 0 10px 30px rgba(31, 111, 235, 0.4);
      display: flex; flex-direction: column; align-items: center; justify-content: center;
      margin-bottom: 25px; -webkit-tap-highlight-color: transparent; transition: all 0.2s ease;
    }
    .mic-btn.active {
      transform: scale(0.95); background: linear-gradient(135deg, #da3633, #f85149);
      box-shadow: 0 0 35px rgba(248, 81, 73, 0.6);
    }
    .mic-icon { font-size: 48px; margin-bottom: 8px; }
    .transcript-box {
      width: 100%; max-width: 360px; background: #161b22; border: 1px solid #30363d;
      border-radius: 12px; padding: 15px; min-height: 70px; font-size: 16px; color: #7ee787;
      margin-bottom: 20px; box-sizing: border-box;
    }
    .quick-cmds { display: flex; flex-wrap: wrap; gap: 10px; justify-content: center; max-width: 360px; }
    .cmd-chip {
      background: #21262d; border: 1px solid #30363d; color: #c9d1d9;
      padding: 10px 14px; border-radius: 8px; font-size: 13px; cursor: pointer;
    }
  </style>
</head>
<body>
  <h1>🔒 مايك الموبايل المشفر (HTTPS)</h1>
  <p>متصل بلابتوب RTX 4050: <span id="server-ip">HOST_IP_PLACEHOLDER</span></p>
  <div class="status-badge" id="conn-status">متصل بالسيرفر المشفر 🟢</div>

  <button class="mic-btn" id="mic-btn">
    <div class="mic-icon">🎙️</div>
    <span id="btn-text">اضغط للتحدث</span>
  </button>

  <div class="transcript-box" id="transcript">الأمر الصوتي أو كلام الـ AI هيظهر هنا...</div>

  <div class="quick-cmds">
    <button class="cmd-chip" onclick="sendCmd('افتح النور')">💡 افتح النور</button>
    <button class="cmd-chip" onclick="sendCmd('اقفل النور')">🌑 اقفل النور</button>
    <button class="cmd-chip" onclick="sendCmd('وطي الصوت')">🔉 وطي الصوت</button>
    <button class="cmd-chip" onclick="sendCmd('شغل التكييف على 22')">❄️ تكييف 22</button>
    <button class="cmd-chip" onclick="sendCmd('بطارية اللابتوب كام')">🔋 البطارية</button>
    <button class="cmd-chip" onclick="sendCmd('إزيك يا بطل احكيلي نكتة')">🤖 شات ذكي</button>
  </div>

  <script>
    const host = window.location.hostname;
    const wsPort = WS_PORT_PLACEHOLDER;
    const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    let ws;

    const transcriptEl = document.getElementById('transcript');
    const statusEl = document.getElementById('conn-status');
    const micBtn = document.getElementById('mic-btn');
    const btnText = document.getElementById('btn-text');

    function connectWS() {
      ws = new WebSocket(proto + '//' + host + ':' + wsPort);
      ws.onopen = () => {
        statusEl.innerText = 'متصل بالسيرفر المشفر 🟢';
        statusEl.style.background = '#238636';
      };
      ws.onclose = () => {
        statusEl.innerText = 'جاري إعادة الاتصال... 🔴';
        statusEl.style.background = '#da3633';
        setTimeout(connectWS, 2000);
      };
    }
    connectWS();

    function sendCmd(text) {
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: 'command', text: text }));
        transcriptEl.innerText = 'تم الإرسال: ' + text;
      }
    }

    // Web Speech API / MediaDevices access unlocked via HTTPS
    let recognition;
    let isListening = false;
    if ('webkitSpeechRecognition' in window || 'SpeechRecognition' in window) {
      const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
      recognition = new SpeechRecognition();
      recognition.lang = 'ar-EG';
      recognition.continuous = false;
      recognition.interimResults = false;

      recognition.onstart = () => {
        isListening = true;
        micBtn.classList.add('active');
        btnText.innerText = 'سامعك.. اتكلم';
        transcriptEl.innerText = 'جاري الاستماع لمايك الموبايل...';
      };

      recognition.onresult = (e) => {
        const text = e.results[0][0].transcript;
        transcriptEl.innerText = text;
        sendCmd(text);
      };

      recognition.onerror = () => {
        micBtn.classList.remove('active');
        btnText.innerText = 'اضغط للتحدث';
        isListening = false;
      };

      recognition.onend = () => {
        micBtn.classList.remove('active');
        btnText.innerText = 'اضغط للتحدث';
        isListening = false;
      };
    }

    micBtn.addEventListener('click', () => {
      if (!recognition) {
        // Fallback prompt
        const promptText = prompt('اكتب الأمر الصوتي للتحكم بالسمارت هوم:');
        if (promptText) sendCmd(promptText);
        return;
      }
      if (isListening) {
        recognition.stop();
      } else {
        recognition.start();
      }
    });
  </script>
</body>
</html>
"""


class SecureMobileHTTPHandler(BaseHTTPRequestHandler):
    lan_ip = "127.0.0.1"
    ws_port = 8765

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        html = MOBILE_HTML_TEMPLATE.replace("HOST_IP_PLACEHOLDER", self.lan_ip)
        html = html.replace("WS_PORT_PLACEHOLDER", str(self.ws_port))
        self.wfile.write(html.encode("utf-8"))

    def log_message(self, format, *args):
        pass


class MobileMicLANBridge:
    def __init__(self, port: int = 8765):
        self.port = port
        self.http_port = port + 1
        self.lan_ip = get_local_lan_ip()
        self.is_running = False
        self.active_clients = 0

        self.on_command_received: Optional[Callable[[str], None]] = None
        self.on_client_count_change: Optional[Callable[[int], None]] = None

        self._ws_server = None
        self._http_server = None
        self._loop = None
        self._thread = None
        self.cert_path, self.key_path = ensure_ssl_certificates(self.lan_ip)

    def start(self):
        if self.is_running:
            return

        self.is_running = True
        self.lan_ip = get_local_lan_ip()

        # 1. Start HTTPS Web Server
        def _http_worker():
            SecureMobileHTTPHandler.lan_ip = self.lan_ip
            SecureMobileHTTPHandler.ws_port = self.port
            self._http_server = HTTPServer(("0.0.0.0", self.http_port), SecureMobileHTTPHandler)
            if self.cert_path and self.key_path and os.path.exists(self.cert_path):
                ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
                ssl_context.load_cert_chain(self.cert_path, self.key_path)
                self._http_server.socket = ssl_context.wrap_socket(self._http_server.socket, server_side=True)
            self._http_server.serve_forever()

        t_http = threading.Thread(target=_http_worker, daemon=True)
        t_http.start()

        # 2. Start Secure WebSocket Server (WSS)
        def _ws_worker():
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)

            async def _handler(websocket):
                self.active_clients += 1
                if self.on_client_count_change:
                    self.on_client_count_change(self.active_clients)

                try:
                    async for message in websocket:
                        try:
                            data = json.loads(message)
                            if data.get("type") == "command" and "text" in data:
                                text = data["text"].strip()
                                if text and self.on_command_received:
                                    self.on_command_received(text)
                        except Exception:
                            pass
                finally:
                    self.active_clients = max(0, self.active_clients - 1)
                    if self.on_client_count_change:
                        self.on_client_count_change(self.active_clients)

            async def _main():
                ssl_ctx = None
                if self.cert_path and self.key_path and os.path.exists(self.cert_path):
                    ssl_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
                    ssl_ctx.load_cert_chain(self.cert_path, self.key_path)

                async with websockets.serve(_handler, "0.0.0.0", self.port, ssl=ssl_ctx):
                    while self.is_running:
                        await asyncio.sleep(1)

            try:
                self._loop.run_until_complete(_main())
            except Exception as e:
                print(f"[WSS Server Error] {e}")

        self._thread = threading.Thread(target=_ws_worker, daemon=True)
        self._thread.start()

    def stop(self):
        self.is_running = False
        if self._http_server:
            try:
                self._http_server.shutdown()
            except Exception:
                pass
