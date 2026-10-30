"""Exercise the frozen executable, its bundled UI, and a real small upload."""
from __future__ import annotations
import http.client
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

def request(port, method, endpoint, token=None, body=None):
    conn = http.client.HTTPConnection('127.0.0.1', port, timeout=10)
    headers = {'X-LocalDrop-Token': token} if token else {}
    if body is not None:
        headers['Content-Type'] = 'application/octet-stream'
    try:
        conn.request(method, endpoint, body=body, headers=headers)
        response = conn.getresponse()
        data = response.read()
        status = response.status
    finally:
        conn.close()
    try:
        return status, json.loads(data)
    except (ValueError, UnicodeDecodeError):
        return status, data

def main():
    binary = Path('dist/WarpCoil.exe' if os.name == 'nt' else 'dist/WarpCoil').resolve()
    if not binary.is_file():
        raise RuntimeError(f'Missing built binary: {binary}')
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    with tempfile.TemporaryDirectory() as tmp:
        proc = subprocess.Popen(
            [str(binary), '--no-browser', '--port', str(port), '--folder', str(Path(tmp) / 'inbox')],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        try:
            page = None
            for _ in range(100):
                if proc.poll() is not None:
                    raise RuntimeError('WarpCoil exited before serving HTTP')
                try:
                    with urllib.request.urlopen(f'http://127.0.0.1:{port}/', timeout=1) as res:
                        page = res.read().decode('utf-8')
                    break
                except (OSError, urllib.error.URLError):
                    time.sleep(.25)
            if not page:
                raise RuntimeError('Server never served the bundled HTML')
            assert 'WarpCoil' in page
            prefix = 'window.LOCALDROP_BOOT = '
            if prefix not in page:
                raise RuntimeError('Local browser bootstrap not found')
            token = json.loads(page.split(prefix, 1)[1].split(';', 1)[0])['token']
            if not token:
                raise RuntimeError('Local browser did not receive a pairing token')
            for endpoint in ('/app.js', '/style.css'):
                status, data = request(port, 'GET', endpoint)
                assert status == 200 and len(data) > 100, (endpoint, status)
            status, _ = request(port, 'GET', '/api/info')
            assert status == 401
            status, info = request(port, 'GET', '/api/info', token)
            assert status == 200 and 'folder' in info
            payload = b'WarpCoil binary smoke test'
            meta = {'name': 'binary-smoke-test.mov', 'size': len(payload),
                    'mtime': 0, 'fingerprint': '12345678abcdef01', 'client': 'a'*32}
            conn = http.client.HTTPConnection('127.0.0.1', port, timeout=10)
            conn.request('POST', '/api/init', json.dumps(meta).encode('utf-8'),
                         {'X-LocalDrop-Token': token, 'Content-Type': 'application/json'})
            rsp = conn.getresponse()
            init = json.loads(rsp.read())
            assert rsp.status == 200, init
            conn.close()
            ident = init['id']
            status, uploaded = request(port, 'PUT', f'/api/upload/{ident}?offset=0', token, payload)
            assert status == 200 and uploaded['offset'] == len(payload), (status, uploaded)
            status, result = request(port, 'POST', f'/api/finish/{ident}', token, b'{}')
            assert status == 200, (status, result)
            saved = Path(tmp) / 'inbox' / result['name']
            assert saved.read_bytes() == payload
            print('PASS: frozen binary serves bundled UI, protects API, writes file, and completes transfer')
        finally:
            # A PyInstaller one-file build creates a child process on Windows.
            # Terminating only the bootloader parent can leave that child alive
            # and the redirected pipe open. Stop the process tree instead.
            if os.name == 'nt':
                subprocess.run(['taskkill', '/PID', str(proc.pid), '/T', '/F'],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                               timeout=10, check=False)
            else:
                proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=10)

if __name__ == '__main__':
    main()
