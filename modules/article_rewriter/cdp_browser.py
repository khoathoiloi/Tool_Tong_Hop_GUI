# -*- coding: utf-8 -*-
"""
modules/article_rewriter/cdp_browser.py
Trình điều khiển Chrome DevTools Protocol (CDP) độc lập qua WebSocket/Socket thuần Python.
Không phụ thuộc Selenium/Playwright, tự cô lập Profile Chrome riêng biệt.
"""
import os
import sys
import time
import json
import random
import socket
import struct
import string
import base64
import subprocess
import threading
import urllib.request
from urllib.parse import urlparse, unquote

DEFAULT_PORT = 9222

def host_of(url: str) -> str:
    try:
        return urlparse(url).hostname or ""
    except Exception:
        return ""

def root_domain(host: str) -> str:
    parts = (host or "").split(".")
    if len(parts) <= 2:
        return host or ""
    if parts[-2] in ("com", "net", "org", "co", "gov", "edu", "ac", "pro"):
        return ".".join(parts[-3:])
    return ".".join(parts[-2:])

def _same_site(cookie_domain: str, host: str) -> bool:
    if not cookie_domain or not host:
        return False
    cd = cookie_domain.lstrip(".").lower()
    h = host.lower()
    return h == cd or h.endswith("." + cd) or cd.endswith("." + h) or root_domain(cd) == root_domain(h)

def find_chrome(manual: str = "") -> str:
    if manual and os.path.exists(manual):
        return manual
    candidates = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
        r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        os.path.expandvars(r"%PROGRAMFILES(X86)%\Microsoft\Edge\Application\msedge.exe")
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    return ""

def find_free_port(start: int = DEFAULT_PORT) -> int:
    for port in range(start, start + 50):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    return start

def new_profile_dir(base_dir: str = None) -> str:
    if not base_dir:
        base_dir = os.path.join(os.path.expanduser("~"), ".kilo_token_tool", "profiles")
    os.makedirs(base_dir, exist_ok=True)
    slug = "".join(random.choices(string.ascii_lowercase + string.digits, k=8))
    p = os.path.join(base_dir, f"run_{int(time.time())}_{slug}")
    os.makedirs(p, exist_ok=True)
    return p

def _write_profile_prefs(profile_dir: str):
    d = os.path.join(profile_dir, "Default")
    os.makedirs(d, exist_ok=True)
    prefs_file = os.path.join(d, "Preferences")
    prefs = {
        "profile": {"password_manager_enabled": False},
        "credentials_enable_service": False,
        "autofill": {"profile_enabled": False, "credit_card_enabled": False},
    }
    try:
        with open(prefs_file, "w", encoding="utf-8") as f:
            json.dump(prefs, f)
    except Exception:
        pass

def launch_chrome_debug(chrome_path: str, profile_dir: str, debug_port: int, url: str = "about:blank") -> subprocess.Popen:
    _write_profile_prefs(profile_dir)
    args = [
        chrome_path,
        f"--remote-debugging-port={debug_port}",
        f"--user-data-dir={profile_dir}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-background-networking",
        "--disable-client-side-phishing-detection",
        "--disable-default-apps",
        "--disable-extensions",
        "--disable-hang-monitor",
        "--disable-popup-blocking",
        "--disable-prompt-on-repost",
        "--disable-sync",
        "--disable-translate",
        "--metrics-recording-only",
        "--no-service-autorun",
        "--password-store=basic",
        "--window-size=1280,800",
        url
    ]
    creationflags = 0
    return subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=creationflags)

def _http_json(port: int, path: str, timeout: float = 5.0):
    url = f"http://127.0.0.1:{port}{path}"
    req = urllib.request.Request(url, headers={"User-Agent": "CDP-Client"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))

class _WS:
    """Client WebSocket thuần Python (RFC 6455) không cần thư viện ngoài"""
    def __init__(self, ws_url: str, timeout: float = 15.0):
        self.ws_url = ws_url
        self.timeout = timeout
        parsed = urlparse(ws_url)
        self.host = parsed.hostname or "127.0.0.1"
        self.port = parsed.port or 80
        self.path = parsed.path + (("?" + parsed.query) if parsed.query else "")
        self.sock = socket.create_connection((self.host, self.port), timeout=timeout)
        self.sock.settimeout(timeout)
        self._buf = bytearray()
        self._handshake()

    def _handshake(self):
        sec_key = base64.b64encode(os.urandom(16)).decode("ascii")
        req = (
            f"GET {self.path} HTTP/1.1\r\n"
            f"Host: {self.host}:{self.port}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {sec_key}\r\n"
            "Sec-WebSocket-Version: 13\r\n\r\n"
        )
        self.sock.sendall(req.encode("ascii"))
        head = bytearray()
        while b"\r\n\r\n" not in head:
            chunk = self.sock.recv(1024)
            if not chunk:
                raise ConnectionError("WebSocket handshake failed")
            head.extend(chunk)
        status = head.split(b"\r\n")[0]
        if b"101" not in status:
            raise ConnectionError(f"Handshake rejected: {status.decode('utf-8', errors='ignore')}")

    def send(self, text: str):
        payload = text.encode("utf-8")
        mask = os.urandom(4)
        n = len(payload)
        frame = bytearray([0x81])
        if n < 126:
            frame.append(0x80 | n)
        elif n <= 0xFFFF:
            frame.append(0x80 | 126)
            frame.extend(struct.pack("!H", n))
        else:
            frame.append(0x80 | 127)
            frame.extend(struct.pack("!Q", n))
        frame.extend(mask)
        masked = bytearray(b ^ mask[i % 4] for i, b in enumerate(payload))
        frame.extend(masked)
        self.sock.sendall(frame)

    def _pull(self):
        try:
            c = self.sock.recv(4096)
            if not c:
                return False
            self._buf.extend(c)
            return True
        except socket.timeout:
            return True
        except Exception:
            return False

    def _one_frame(self):
        if len(self._buf) < 2:
            return None
        b1, b2 = self._buf[0], self._buf[1]
        opcode = b1 & 0x0F
        masked = bool(b2 & 0x80)
        plen = b2 & 0x7F
        idx = 2
        if plen == 126:
            if len(self._buf) < 4: return None
            plen = struct.unpack("!H", self._buf[2:4])[0]
            idx = 4
        elif plen == 127:
            if len(self._buf) < 10: return None
            plen = struct.unpack("!Q", self._buf[2:10])[0]
            idx = 10
        mask = None
        if masked:
            if len(self._buf) < idx + 4: return None
            mask = self._buf[idx:idx+4]
            idx += 4
        if len(self._buf) < idx + plen:
            return None
        payload = self._buf[idx:idx+plen]
        del self._buf[:idx+plen]
        if mask:
            payload = bytearray(b ^ mask[i % 4] for i, b in enumerate(payload))
        return opcode, bytes(payload)

    def recv(self, timeout: float = 20.0):
        start = time.time()
        while time.time() - start < timeout:
            frame = self._one_frame()
            if frame is not None:
                op, data = frame
                if op == 0x01: # Text
                    return data.decode("utf-8", errors="replace")
                elif op == 0x09: # Ping
                    self._send_ctrl(0x0A, data)
                elif op == 0x08: # Close
                    return None
            else:
                if not self._pull():
                    return None
            time.sleep(0.01)
        return None

    def _send_ctrl(self, opcode: int, data: bytes = b""):
        mask = os.urandom(4)
        frame = bytearray([0x80 | (opcode & 0x0F), 0x80 | len(data)])
        frame.extend(mask)
        frame.extend(b ^ mask[i % 4] for i, b in enumerate(data))
        try:
            self.sock.sendall(frame)
        except Exception:
            pass

    def close(self):
        try:
            self._send_ctrl(0x08)
            self.sock.close()
        except Exception:
            pass

class CDP:
    """Chrome DevTools Protocol (CDP) Controller"""
    def __init__(self, port: int):
        self.port = int(port)
        self.ws = None
        self._seq = 0
        self._lock = threading.Lock()
        self._replies = {}
        self._events = []
        self._stop = False
        self._reader = None

    def connect(self, timeout: float = 30.0):
        start = time.time()
        ws_url = None
        while time.time() - start < timeout:
            try:
                pages = _http_json(self.port, "/json")
                for p in pages:
                    if p.get("type") == "page" and p.get("webSocketDebuggerUrl"):
                        ws_url = p["webSocketDebuggerUrl"]
                        break
                if ws_url:
                    break
            except Exception:
                pass
            time.sleep(0.3)
        if not ws_url:
            raise TimeoutError(f"Không thể lấy webSocketDebuggerUrl từ cổng {self.port}")
        self.ws = _WS(ws_url, timeout=20)
        self._reader = threading.Thread(target=self._read_loop, daemon=True)
        self._reader.start()
        self.call("Page.enable")
        self.call("Network.enable")
        self.call("Runtime.enable")

    def _read_loop(self):
        while not self._stop:
            try:
                raw = self.ws.recv(timeout=1.0)
            except Exception:
                break
            if not raw:
                continue
            try:
                msg = json.loads(raw)
            except Exception:
                continue
            mid = msg.get("id")
            if mid is not None:
                with self._lock:
                    self._replies[mid] = msg
            else:
                with self._lock:
                    self._events.append(msg)

    def call(self, method: str, params: dict = None, timeout: float = 20.0) -> dict:
        with self._lock:
            self._seq += 1
            seq = self._seq
        msg = {"id": seq, "method": method, "params": params or {}}
        self.ws.send(json.dumps(msg))
        start = time.time()
        while time.time() - start < timeout:
            with self._lock:
                if seq in self._replies:
                    return self._replies.pop(seq)
            time.sleep(0.02)
        return {"error": {"message": f"Timeout calling {method}"}}

    def events(self, method: str = None):
        with self._lock:
            if not method:
                return list(self._events)
            return [e for e in self._events if e.get("method") == method]

    def clear_events(self):
        with self._lock:
            self._events.clear()

    def navigate(self, url: str):
        return self.call("Page.navigate", {"url": url})

    def eval(self, expr: str, await_promise: bool = False, timeout: float = 20.0):
        res = self.call("Runtime.evaluate", {
            "expression": expr,
            "awaitPromise": await_promise,
            "returnByValue": True
        }, timeout=timeout)
        val = res.get("result", {}).get("result", {}).get("value")
        return val

    def wait_ready(self, timeout: float = 40.0):
        start = time.time()
        while time.time() - start < timeout:
            try:
                st = self.eval("document.readyState")
                if st in ("complete", "interactive"):
                    return True
            except Exception:
                pass
            time.sleep(0.4)
        return False

    def all_cookies(self) -> list:
        res = self.call("Network.getAllCookies")
        return res.get("result", {}).get("cookies", [])

    def close(self):
        self._stop = True
        if self.ws:
            try: self.ws.close()
            except Exception: pass

# JavaScript Automation Snippets
_FILL_JS = """
(function(){
  var u = __USER__, p = __PASS__;
  var userIn = document.querySelector('input[type="text"], input[type="email"], input[name*="user"], input[name*="email"], input[name*="login"], input[id*="user"], input[id*="email"]');
  var passIn = document.querySelector('input[type="password"], input[name*="pass"], input[id*="pass"]');
  var filled = {user: false, pass: false, nUser: userIn ? 1 : 0};
  if(userIn){
    userIn.focus();
    userIn.value = u;
    userIn.dispatchEvent(new Event('input', {bubbles:true}));
    userIn.dispatchEvent(new Event('change', {bubbles:true}));
    filled.user = true;
  }
  if(passIn){
    passIn.focus();
    passIn.value = p;
    passIn.dispatchEvent(new Event('input', {bubbles:true}));
    passIn.dispatchEvent(new Event('change', {bubbles:true}));
    filled.pass = true;
  }
  return JSON.stringify(filled);
})()
"""

_SUBMIT_JS = """
(function(){
  var btn = document.querySelector('button[type="submit"], input[type="submit"], button.btn-primary, button:has-text("Login"), button:has-text("Đăng nhập")') || document.querySelector('button, input[type="button"]');
  if(btn){ btn.click(); return btn.innerText || 'submit-btn'; }
  var form = document.querySelector('form');
  if(form){ form.submit(); return 'form-submit'; }
  return '';
})()
"""

_CSRF_JS = """
(function(){
  var meta = document.querySelector('meta[name="csrf-token"], meta[name="csrf_token"], meta[name="_token"], meta[name="csrf"]');
  var csrf = meta ? meta.getAttribute('content') : '';
  var input = document.querySelector('input[name="_token"], input[name="csrf_token"], input[name="csrf"]');
  if(!csrf && input) csrf = input.value;
  return JSON.stringify({csrf: csrf || '', title: document.title, url: location.href});
})()
"""

class CDPBrowser:
    """Lớp bọc điều khiển Chrome Browser qua CDP an toàn & tự động"""
    def __init__(self, chrome_path: str = "", profile_dir: str = "", debug_port: int = DEFAULT_PORT, log_cb=None):
        self.chrome_path = chrome_path or find_chrome()
        self.profile_dir = profile_dir or new_profile_dir()
        self.port = find_free_port(debug_port)
        self.log = log_cb or (lambda m, lv="INFO": None)
        self.proc = None
        self.cdp = None

    def open(self, url: str):
        if not self.chrome_path or not os.path.exists(self.chrome_path):
            raise FileNotFoundError("Không tìm thấy đường dẫn Chrome hợp lệ trên máy!")
        self.log(f"Khởi chạy Chrome riêng (Port: {self.port})...", "INFO")
        self.proc = launch_chrome_debug(self.chrome_path, self.profile_dir, self.port, url=url)
        time.sleep(1.0)
        self.cdp = CDP(self.port)
        self.cdp.connect(timeout=30)
        self.cdp.navigate(url)
        self.cdp.wait_ready(timeout=40)

    def autofill_and_login(self, user: str, password: str) -> bool:
        if not self.cdp:
            return False
        fj = _FILL_JS.replace("__USER__", json.dumps(user or "")).replace("__PASS__", json.dumps(password or ""))
        for _ in range(3):
            try:
                raw = self.cdp.eval(fj)
                status = json.loads(raw) if raw else {}
                if status.get("user") and status.get("pass"):
                    break
            except Exception:
                pass
            time.sleep(1.0)
        time.sleep(0.5)
        try:
            self.cdp.eval(_SUBMIT_JS)
            self.log("Đã điền thông tin và bấm Đăng nhập!", "INFO")
            return True
        except Exception as e:
            self.log(f"Lỗi bấm đăng nhập: {e}", "WARNING")
            return False

    def get_cookies_for(self, url: str) -> list:
        if not self.cdp: return []
        host = host_of(url)
        return [c for c in self.cdp.all_cookies() if _same_site(c.get("domain"), host)]

    def get_cookie_header_str(self, url: str) -> str:
        cookies = self.get_cookies_for(url)
        return "; ".join([f"{c['name']}={c['value']}" for c in cookies])

    def get_csrf_token(self) -> str:
        if not self.cdp: return ""
        try:
            raw = self.cdp.eval(_CSRF_JS)
            data = json.loads(raw) if raw else {}
            return data.get("csrf", "")
        except Exception:
            return ""

    def close(self):
        if self.cdp:
            try: self.cdp.close()
            except Exception: pass
        if self.proc:
            try: self.proc.terminate()
            except Exception: pass
