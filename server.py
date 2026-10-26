"""
server.py: سيرفر الموقع. بيعتمد على مكتبات بايثون الأساسية بس (مفيش تثبيت).

التشغيل:
    python server.py
    python server.py --port 8080
"""

import argparse
import os
import importlib.util
import json
import sys
import threading
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
INDEX_PATH = ROOT / "index.html"
BRAIN_PATH = ROOT / "brain.py"

MAX_BODY = 512 * 1024   # أقصى حجم للطلب بالبايت
MAX_MESSAGE = 4000      # أقصى طول للرسالة الواحدة بالحروف
MAX_HISTORY = 20        # عدد الرسائل السابقة اللي بتتبعت للعقل

_brain = None
_brain_stamp = None
_brain_lock = threading.Lock()


def _brain_stamp_now():
    """بصمة بتتغير لما brain.py أو أي ملف .py جنبه (غير server.py) يتعدّل."""
    stamps = []
    for path in sorted(ROOT.glob("*.py")):
        if path.name != Path(__file__).name:
            stamps.append((path.name, path.stat().st_mtime_ns))
    return tuple(stamps)


def load_brain():
    """يحمّل brain.py، ويعيد تحميله لو هو أو أي ملف جنبه اتغيّر من آخر مرة."""
    global _brain, _brain_stamp
    stamp = _brain_stamp_now()
    with _brain_lock:
        if _brain is None or stamp != _brain_stamp:
            for name in [p.stem for p in ROOT.glob("*.py")]:
                if name != "server":
                    sys.modules.pop(name, None)
            spec = importlib.util.spec_from_file_location("brain", BRAIN_PATH)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            if not callable(getattr(module, "think", None)):
                raise RuntimeError("brain.py لازم يحتوي على دالة اسمها think(message, history)")
            _brain, _brain_stamp = module, stamp
        return _brain


def brain_info(brain):
    """بيانات اللوحة اللي فوق في الموقع. العقل يقدر يحدّدها بدالة describe()."""
    info = {
        "name": str(getattr(brain, "NAME", "عقلي")),
        "version": str(getattr(brain, "VERSION", "")),
        "placeholder": bool(getattr(brain, "IS_PLACEHOLDER", False)),
    }
    describe = getattr(brain, "describe", None)
    if callable(describe):
        extra = describe()
        if isinstance(extra, dict):
            info.update(extra)
    return info


def clean_history(raw):
    if not isinstance(raw, list):
        return []
    cleaned = []
    for item in raw[-MAX_HISTORY:]:
        if (
            isinstance(item, dict)
            and item.get("role") in ("user", "assistant")
            and isinstance(item.get("content"), str)
        ):
            cleaned.append({"role": item["role"], "content": item["content"][:MAX_MESSAGE]})
    return cleaned


class Handler(BaseHTTPRequestHandler):
    server_version = "MyAISite/0.1"

    def _send(self, status, body, content_type, extra_headers=None):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        for key, value in (extra_headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self._send(status, body, "application/json; charset=utf-8")

    def do_GET(self):
        path = self.path.split("?", 1)[0]

        if path in ("/", "/index.html"):
            try:
                body = INDEX_PATH.read_bytes()
            except OSError:
                return self._json(500, {"error": "ملف index.html مش موجود جنب server.py"})
            return self._send(200, body, "text/html; charset=utf-8")

        if path == "/api/brain":
            try:
                info = brain_info(load_brain())
            except Exception as exc:
                traceback.print_exc()
                return self._json(500, {"error": f"{type(exc).__name__}: {exc}"})
            return self._json(200, info)

        if path == "/favicon.ico":
            return self._send(204, b"", "image/x-icon")

        self._json(404, {"error": "الصفحة مش موجودة"})

    def do_POST(self):
        if self.path.split("?", 1)[0] != "/api/chat":
            return self._json(404, {"error": "الصفحة مش موجودة"})

        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        if length <= 0:
            return self._json(400, {"error": "الطلب فاضي"})
        if length > MAX_BODY:
            return self._json(413, {"error": "الطلب أكبر من الحجم المسموح"})

        try:
            data = json.loads(self.rfile.read(length).decode("utf-8"))
            if not isinstance(data, dict):
                raise ValueError("not an object")
        except (ValueError, UnicodeDecodeError):
            return self._json(400, {"error": "صيغة الطلب غلط"})

        message = data.get("message")
        if not isinstance(message, str) or not message.strip():
            return self._json(400, {"error": "اكتب رسالة الأول"})
        if len(message) > MAX_MESSAGE:
            return self._json(413, {"error": f"الرسالة أطول من {MAX_MESSAGE} حرف"})

        history = clean_history(data.get("history"))

        try:
            brain = load_brain()
            reply = brain.think(message.strip(), history)
        except Exception as exc:
            if getattr(exc, "user_facing", False):
                # خطأ رسالته مكتوبة للمستخدم (مفتاح غلط، رصيد خلص، النت واقع...)
                print(f"brain: {str(exc).splitlines()[0]}")
                return self._json(502, {"error": str(exc)})
            traceback.print_exc()
            return self._json(500, {"error": f"العقل فيه مشكلة: {type(exc).__name__}: {exc}"})

        self._json(200, {"reply": reply if isinstance(reply, str) else str(reply)})


def main():
    parser = argparse.ArgumentParser(description="Chat website server")
    parser.add_argument("--host", default=os.environ.get("HOST", "127.0.0.1"), help="bind address")
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8000")))
    args = parser.parse_args()

    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

    try:
        httpd = ThreadingHTTPServer((args.host, args.port), Handler)
    except OSError as exc:
        print(f"Cannot start on port {args.port}: {exc}")
        print(f"Try another port: python server.py --port {args.port + 1}")
        sys.exit(1)

    try:
        info = brain_info(load_brain())
        print(f"Brain loaded (placeholder={info['placeholder']})")
    except Exception:
        print("brain.py has a problem (the site will show the error):")
        traceback.print_exc()

    print(f"Open http://{args.host}:{args.port} in your browser (Ctrl+C to stop)")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped")
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
