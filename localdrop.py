#!/usr/bin/env python3
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""WarpCoil 1.3.2 — resumable LAN uploads with speed diagnostics."""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import socket
import sys
import threading
import time
from collections import defaultdict, deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit
import webbrowser


APP_DIR = Path(__file__).resolve().parent
CHUNK_MAX = 2 * 1024 * 1024
SYNC_EVERY = 64 * 1024 * 1024  # Do not force a disk flush after every 2 MiB chunk.
MAX_FILE_SIZE = 4 * 1024**4  # 4 TiB; real limit is disk capacity.
ID_RE = re.compile(r"^[a-f0-9]{64}$")
CLIENT_RE = re.compile(r"^[a-f0-9]{32}$")
FINGERPRINT_RE = re.compile(r"^[a-f0-9]{16}$")
BAD_NAME = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def safe_filename(value: str) -> str:
    value = value.replace("\\", "/").split("/")[-1]
    value = BAD_NAME.sub("_", value).strip(" .")
    if not value or value.upper().split(".")[0] in {
        "CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)),
        *(f"LPT{i}" for i in range(1, 10)),
    }:
        value = "fisier_" + (value or "fara_nume")
    # Limit UTF-8 byte count, preserving extension where possible.
    stem, dot, ext = value.rpartition(".")
    if not dot:
        stem, ext = value, ""
    ext = ext[:24]
    allowance = 180 - len(ext.encode("utf-8")) - (1 if ext else 0)
    while len(stem.encode("utf-8")) > max(20, allowance):
        stem = stem[:-1]
    return stem + ("." + ext if ext else "")


def lan_ip() -> str:
    # UDP connect selects the local network interface; no packet is sent.
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("192.0.2.1", 80))
            ip = sock.getsockname()[0]
            if ip and not ip.startswith("127."):
                return ip
    except OSError:
        pass
    try:
        for result in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = result[4][0]
            if not ip.startswith("127."):
                return ip
    except OSError:
        pass
    return "127.0.0.1"


class State:
    def __init__(self, destination: Path, pin: str | None = None):
        self.destination = destination.resolve()
        self.destination.mkdir(parents=True, exist_ok=True)
        self.parts = self.destination / ".localdrop-parts"
        self.parts.mkdir(exist_ok=True)
        self.token = secrets.token_urlsafe(32)
        self.pin = pin or f"{secrets.randbelow(900000) + 100000}"
        self.locks_guard = threading.Lock()
        self.locks: dict[str, threading.Lock] = {}
        self.destination_lock = threading.Lock()
        self.attempts: dict[str, deque[float]] = defaultdict(deque)
        self.attempts_lock = threading.Lock()
        self.recent: deque[dict] = deque(maxlen=15)

    def lock_for(self, upload_id: str) -> threading.Lock:
        with self.locks_guard:
            if upload_id not in self.locks:
                self.locks[upload_id] = threading.Lock()
            return self.locks[upload_id]

    def pair(self, ip: str, entered: str) -> bool:
        now = time.monotonic()
        with self.attempts_lock:
            attempts = self.attempts[ip]
            while attempts and now - attempts[0] > 600:
                attempts.popleft()
            if len(attempts) >= 10:
                return False
            if not hmac.compare_digest(entered, self.pin):
                attempts.append(now)
                return False
            attempts.clear()
            return True

    def paths(self, upload_id: str) -> tuple[Path, Path]:
        if not ID_RE.fullmatch(upload_id):
            raise ValueError("Invalid identifier")
        return self.parts / f"{upload_id}.json", self.parts / f"{upload_id}.part"

    def init_upload(self, data: dict) -> dict:
        name = data.get("name")
        size = data.get("size")
        client = data.get("client")
        mtime = data.get("mtime")
        fingerprint = data.get("fingerprint")
        if not isinstance(name, str) or not name or len(name) > 1024:
            raise ValueError("Invalid file name")
        if type(size) is not int or not (0 <= size <= MAX_FILE_SIZE):
            raise ValueError("Invalid size")
        if not isinstance(client, str) or not CLIENT_RE.fullmatch(client):
            raise ValueError("Invalid session")
        if type(mtime) is not int or mtime < 0:
            raise ValueError("Invalid file date")
        if not isinstance(fingerprint, str) or not FINGERPRINT_RE.fullmatch(fingerprint):
            raise ValueError("Invalid file fingerprint")
        name = safe_filename(name)
        signature = json.dumps([client, name, size, fingerprint], ensure_ascii=False)
        upload_id = hashlib.sha256(signature.encode("utf-8")).hexdigest()
        meta_path, part_path = self.paths(upload_id)
        with self.lock_for(upload_id):
            if meta_path.exists():
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                if (meta["name"], meta["size"], meta["fingerprint"]) != (name, size, fingerprint):
                    raise ValueError("Transfer metadata does not match")
                if not part_path.exists():
                    part_path.touch()
            else:
                if not part_path.exists():
                    part_path.touch()
                meta = {"name": name, "size": size, "mtime": mtime,
                        "fingerprint": fingerprint}
                meta_path.write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
            offset = part_path.stat().st_size
            if offset > size:
                raise ValueError("Partial transfer has an invalid size")
        return {"id": upload_id, "offset": offset, "chunkSize": CHUNK_MAX}

    def status(self, upload_id: str) -> dict:
        meta_path, part_path = self.paths(upload_id)
        with self.lock_for(upload_id):
            if not meta_path.is_file() or not part_path.is_file():
                raise FileNotFoundError("Transfer no longer exists")
            return {"offset": part_path.stat().st_size}

    def append_chunk(self, upload_id: str, offset: int, length: int, input_stream) -> dict:
        meta_path, part_path = self.paths(upload_id)
        if length <= 0 or length > CHUNK_MAX or offset < 0:
            raise ValueError("Invalid chunk size")
        with self.lock_for(upload_id):
            if not meta_path.is_file() or not part_path.is_file():
                raise FileNotFoundError("Transfer does not exist")
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            actual = part_path.stat().st_size
            if actual != offset:
                return {"conflict": True, "offset": actual}
            if offset + length > meta["size"]:
                raise ValueError("Chunk exceeds file size")
            read_s = write_s = sync_s = 0.0
            with part_path.open("r+b") as output:
                output.seek(offset)
                remaining = length
                while remaining:
                    t = time.perf_counter()
                    block = input_stream.read(min(256 * 1024, remaining))
                    read_s += time.perf_counter() - t
                    if not block:
                        break
                    t = time.perf_counter()
                    output.write(block)
                    write_s += time.perf_counter() - t
                    remaining -= len(block)
                t = time.perf_counter()
                output.flush()
                write_s += time.perf_counter() - t
                # Sync occasionally, and always at finish. In 1.2 a sync after
                # EACH chunk could introduce major delays on some Windows disks.
                if (offset + length) // SYNC_EVERY > offset // SYNC_EVERY:
                    t = time.perf_counter()
                    os.fsync(output.fileno())
                    sync_s = time.perf_counter() - t
            if remaining:
                raise ValueError("Connection was interrupted during the chunk")
            return {"offset": offset + length,
                    "serverReadMs": round(read_s * 1000, 1),
                    "serverWriteMs": round(write_s * 1000, 1),
                    "serverSyncMs": round(sync_s * 1000, 1)}

    def finish_upload(self, upload_id: str) -> dict:
        meta_path, part_path = self.paths(upload_id)
        with self.lock_for(upload_id):
            if not meta_path.is_file() or not part_path.is_file():
                raise FileNotFoundError("Transfer does not exist")
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            if part_path.stat().st_size != meta["size"]:
                raise ValueError("Transfer is not complete")
            # Ensure all content is committed before marking the file complete.
            with part_path.open("r+b") as output:
                output.flush()
                os.fsync(output.fileno())
            with self.destination_lock:
                original = Path(meta["name"])
                candidate = self.destination / original.name
                n = 2
                while candidate.exists():
                    candidate = self.destination / f"{original.stem} ({n}){original.suffix}"
                    n += 1
                # Reserve name exclusively; don't overwrite existing files.
                with candidate.open("xb"):
                    pass
                try:
                    os.replace(part_path, candidate)
                except Exception:
                    candidate.unlink(missing_ok=True)
                    raise
            try:
                timestamp = meta["mtime"] / 1000
                if 946684800 <= timestamp <= 4102444800:
                    os.utime(candidate, (time.time(), timestamp))
            except OSError:
                pass
            meta_path.unlink(missing_ok=True)
            result = {"name": candidate.name, "size": meta["size"]}
            self.recent.appendleft(result)
            return result


class AppHandler(BaseHTTPRequestHandler):
    server_version = "WarpCoil/1.3.2"
    # A fresh connection for each chunk avoids stale persistent sockets on iOS.
    protocol_version = "HTTP/1.0"

    def setup(self):
        super().setup()
        self.connection.settimeout(50)

    def handle(self):
        # Browsers routinely close idle HTTP/1.1 sockets. On Windows these
        # disconnects otherwise print intimidating WinError 10054 tracebacks.
        try:
            super().handle()
        except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError):
            pass

    @property
    def state(self) -> State:
        return self.server.state  # type: ignore[attr-defined]

    def log_message(self, format, *args):
        # No tokens or filenames in console logs.
        return

    def respond(self, status: int, payload: dict):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        if status >= 400:
            # An early rejection may leave unread request bytes in the socket.
            self.send_header("Connection", "close")
            self.close_connection = True
        self.end_headers()
        self.wfile.write(body)

    def read_json(self) -> dict:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            raise ValueError("Content-Length invalid") from None
        if not 0 < length <= 32768:
            raise ValueError("Invalid request size")
        data = json.loads(self.rfile.read(length))
        if not isinstance(data, dict):
            raise ValueError("Invalid data")
        return data

    def authorized(self) -> bool:
        provided = self.headers.get("X-LocalDrop-Token", "")
        if not hmac.compare_digest(provided, self.state.token):
            self.respond(401, {"error": "Pair again using the code shown on the computer"})
            return False
        return True

    def serve_file(self, path: Path, mime: str, boot: bool = False):
        content = path.read_bytes()
        if boot:
            # Only the loopback PC browser receives the automatic login token.
            loopback = self.client_address[0] in ("127.0.0.1", "::1")
            config = json.dumps({"token": self.state.token if loopback else None,
                                 "local": loopback}, ensure_ascii=False)
            content = content.replace(b"/*__BOOT__*/", f"window.LOCALDROP_BOOT = {config};".encode("utf-8"))
        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self'; img-src 'self' data:; connect-src 'self'; object-src 'none'; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(content)

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == "/":
            return self.serve_file(APP_DIR / "index.html", "text/html; charset=utf-8", True)
        if path == "/app.js":
            return self.serve_file(APP_DIR / "app.js", "text/javascript; charset=utf-8")
        if path == "/style.css":
            return self.serve_file(APP_DIR / "style.css", "text/css; charset=utf-8")
        if not self.authorized():
            return
        try:
            if path == "/api/info":
                return self.respond(200, {
                    "device": socket.gethostname(),
                    "folder": str(self.state.destination),
                    "ip": self.server.lan_ip,  # type: ignore[attr-defined]
                    "port": self.server.server_port,
                    "pin": self.state.pin if self.client_address[0] in ("127.0.0.1", "::1") else None,
                    "free": shutil.disk_usage(self.state.destination).free,
                    "recent": list(self.state.recent),
                })
            if path.startswith("/api/status/"):
                return self.respond(200, self.state.status(path.rsplit("/", 1)[-1]))
            return self.respond(404, {"error": "Page not found"})
        except (ValueError, FileNotFoundError) as exc:
            return self.respond(404, {"error": str(exc)})

    def do_POST(self):
        path = urlsplit(self.path).path
        try:
            if path == "/api/pair":
                data = self.read_json()
                pin = data.get("pin", "")
                if not isinstance(pin, str) or not self.state.pair(self.client_address[0], pin):
                    return self.respond(403, {"error": "Wrong code or too many attempts"})
                return self.respond(200, {"token": self.state.token})
            if not self.authorized():
                return
            if path == "/api/init":
                return self.respond(200, self.state.init_upload(self.read_json()))
            if path.startswith("/api/finish/"):
                return self.respond(200, self.state.finish_upload(path.rsplit("/", 1)[-1]))
            return self.respond(404, {"error": "Unknown operation"})
        except (ValueError, KeyError, json.JSONDecodeError) as exc:
            return self.respond(400, {"error": str(exc)})
        except FileNotFoundError as exc:
            return self.respond(404, {"error": str(exc)})
        except OSError as exc:
            return self.respond(507, {"error": f"Cannot write to disk: {exc.strerror}"})

    def do_PUT(self):
        path = urlsplit(self.path)
        if not self.authorized():
            return
        if path.path == "/api/bench":
            # Consume data over LAN without writing it to the disk. Helps
            # distinguish network/HTTP delays from file reading or storage.
            try:
                length = int(self.headers.get("Content-Length", "-1"))
                if not 0 < length <= CHUNK_MAX:
                    raise ValueError("Invalid test size")
                remaining = length
                start = time.perf_counter()
                while remaining:
                    block = self.rfile.read(min(256 * 1024, remaining))
                    if not block:
                        raise ValueError("Incomplete test data")
                    remaining -= len(block)
                return self.respond(200, {"bytes": length,
                                          "serverReadMs": round((time.perf_counter() - start) * 1000, 1)})
            except (ValueError, OSError, TimeoutError) as exc:
                return self.respond(400, {"error": str(exc)})
        if not path.path.startswith("/api/upload/"):
            return self.respond(404, {"error": "Unknown operation"})
        try:
            length = int(self.headers.get("Content-Length", "-1"))
            offset = int(parse_qs(path.query).get("offset", ["-1"])[0])
            start = time.perf_counter()
            result = self.state.append_chunk(path.path.rsplit("/", 1)[-1], offset, length, self.rfile)
            result["serverTotalMs"] = round((time.perf_counter() - start) * 1000, 1)
            if result.get("conflict"):
                return self.respond(409, result)
            if result["offset"] <= 16 * 1024 * 1024 or result["offset"] % (32 * 1024 * 1024) == 0:
                print(f"[WarpCoil] {path.path.rsplit('/', 1)[-1][:8]}: "
                      f"{result['offset']:,} bytes; "
                      f"LAN read {result['serverReadMs']} ms, "
                      f"disk {result['serverWriteMs']} ms, "
                      f"sync {result['serverSyncMs']} ms", flush=True)
            return self.respond(200, result)
        except (ValueError, KeyError) as exc:
            return self.respond(400, {"error": str(exc)})
        except FileNotFoundError as exc:
            return self.respond(404, {"error": str(exc)})
        except (OSError, TimeoutError) as exc:
            try:
                return self.respond(507, {"error": "Connection interrupted or disk write failed"})
            except (OSError, BrokenPipeError):
                return


class AppServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address, state):
        super().__init__(address, AppHandler)
        self.state = state
        self.lan_ip = lan_ip()


def main():
    parser = argparse.ArgumentParser(description="WarpCoil — iPhone to PC transfer over Wi-Fi")
    parser.add_argument("--port", type=int, default=8765, help="Port local (implicit 8765)")
    parser.add_argument("--folder", type=Path, default=Path.home() / "Videos" / "LocalDrop",
                        help="Folder where received files are saved")
    parser.add_argument("--no-browser", action="store_true", help="Do not open the browser automatically")
    args = parser.parse_args()
    try:
        state = State(args.folder)
        server = AppServer(("0.0.0.0", args.port), state)
    except OSError as exc:
        print(f"Startup error: {exc}", file=sys.stderr)
        return 1
    url = f"http://{server.lan_ip}:{server.server_port}"
    print("\n  WARPCOIL — direct iPhone to PC transfer")
    print("  -------------------------------------")
    print(f"  On iPhone, open Safari: {url}")
    print(f"  Pairing code: {state.pin}")
    print(f"  Files saved in: {state.destination}")
    print("  The PC may be wired while the iPhone is on Wi-Fi (same network).")
    print("  Close with Ctrl+C; internet is not required.\n")
    if not args.no_browser:
        webbrowser.open(f"http://127.0.0.1:{server.server_port}")
    try:
        server.serve_forever(poll_interval=0.2)
    except KeyboardInterrupt:
        print("\nWarpCoil stopped.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
