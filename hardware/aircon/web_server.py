"""
Minimal async HTTP server.

Routes:
  GET  /           → serves static/index.html
  GET  /state      → JSON snapshot of controller state
  POST /set/<attr> → set a writable attribute; body is plain text value

The HTML file is read from /static/index.html on the Pico filesystem.
"""

import asyncio
import gc
import json
import config
import log

_active = 0  # currently open handler coroutines

_HTML_PATH = '/static/index.html'
_HTML_CACHE = None  # loaded and encoded once on first request


def _load_html():
    global _HTML_CACHE
    if _HTML_CACHE is None:
        try:
            with open(_HTML_PATH) as f:
                _HTML_CACHE = f.read().encode()
        except Exception:
            _HTML_CACHE = (
                b'<!DOCTYPE html><html><body>'
                b'<h1>UI not found</h1>'
                b'<p>Copy static/index.html to /static/index.html on the Pico.</p>'
                b'</body></html>'
            )
    return _HTML_CACHE


def _response(writer, status, content_type, body: bytes):
    writer.write(
        f'HTTP/1.1 {status}\r\n'
        f'Content-Type: {content_type}\r\n'
        f'Content-Length: {len(body)}\r\n'
        'Connection: close\r\n'
        'Access-Control-Allow-Origin: *\r\n'
        '\r\n'
    )
    writer.write(body)


async def _handle(reader, writer, ctrl):
    global _active
    _active += 1
    if _active > 1:
        log.log('web', f'concurrent handlers: {_active}  mem_free={gc.mem_free()}')
    try:
        # Request line
        line = await asyncio.wait_for(reader.readline(), 5)
        parts = line.decode().split()
        if len(parts) < 2:
            return
        method, path = parts[0], parts[1].split('?')[0]

        # Headers — collect Content-Length
        content_length = 0
        while True:
            hdr = await asyncio.wait_for(reader.readline(), 5)
            if hdr in (b'\r\n', b''):
                break
            hdr_lower = hdr.decode().lower()
            if hdr_lower.startswith('content-length:'):
                try:
                    content_length = int(hdr_lower.split(':', 1)[1].strip())
                except ValueError:
                    pass

        # Body (POST only)
        body = b''
        if content_length > 0:
            body = await asyncio.wait_for(reader.readexactly(content_length), 5)

        # ── Route dispatch ────────────────────────────────────────────────────

        if method == 'GET' and path == '/':
            _response(writer, '200 OK', 'text/html; charset=utf-8', _load_html())

        elif method == 'GET' and path == '/repl':
            try:
                import os
                size = os.stat('/static/webrepl.html')[6]
                writer.write(
                    f'HTTP/1.1 200 OK\r\n'
                    f'Content-Type: text/html; charset=utf-8\r\n'
                    f'Content-Length: {size}\r\n'
                    'Cache-Control: public, max-age=31536000, immutable\r\n'
                    'Connection: close\r\n'
                    'Access-Control-Allow-Origin: *\r\n'
                    '\r\n'
                )
                with open('/static/webrepl.html', 'rb') as f:
                    while True:
                        chunk = f.read(2048)
                        if not chunk:
                            break
                        writer.write(chunk)
                        await asyncio.wait_for(writer.drain(), 5)
            except Exception as e:
                log.log('web', f'repl: {e}')
                _response(writer, '404 Not Found', 'text/plain', b'not found')

        elif method == 'GET' and path == '/aircon.png':
            try:
                import os
                size = os.stat('/static/aircon.png')[6]
                writer.write(
                    f'HTTP/1.1 200 OK\r\n'
                    f'Content-Type: image/png\r\n'
                    f'Content-Length: {size}\r\n'
                    'Cache-Control: public, max-age=31536000, immutable\r\n'
                    'Connection: close\r\n'
                    'Access-Control-Allow-Origin: *\r\n'
                    '\r\n'
                )
                with open('/static/aircon.png', 'rb') as f:
                    while True:
                        chunk = f.read(2048)
                        if not chunk:
                            break
                        writer.write(chunk)
                        await asyncio.wait_for(writer.drain(), 5)
            except Exception as e:
                log.log('web', f'aircon.png: {e}')
                _response(writer, '404 Not Found', 'text/plain', b'not found')

        elif method == 'POST' and path == '/restart':
            _response(writer, '200 OK', 'text/plain', b'restarting')
            await asyncio.wait_for(writer.drain(), 5)
            log.log('web', 'restart requested')
            import machine
            machine.reset()
            return

        elif method == 'GET' and path == '/state':
            data = json.dumps(ctrl.get_state()).encode()
            _response(writer, '200 OK', 'application/json', data)

        elif method == 'POST' and path.startswith('/set/'):
            attr  = path[5:]
            value = body.decode().strip()

            if attr == 'settings':
                if await ctrl.set_settings(json.loads(body.decode()), 'web'):
                    _response(writer, '200 OK', 'text/plain', b'OK')
                else:
                    _response(writer, '400 Bad Request', 'text/plain', b'invalid settings')
                await asyncio.wait_for(writer.drain(), 5)
                return

            setters = {
                'mode':        ctrl.set_mode,
                'fan':         ctrl.set_fan,
                'setpoint':    ctrl.set_setpoint,
                'circulation': ctrl.set_circulation,
                'panel_temp':  ctrl.set_panel_temp,
                'delta':       ctrl.set_delta,
                'ble_name':    ctrl.set_ble_name,
                'ble_notify':  ctrl.set_ble_notify,
            }
            setter = setters.get(attr)
            if setter and await setter(value, 'web'):
                _response(writer, '200 OK', 'text/plain', b'OK')
            else:
                _response(writer, '400 Bad Request', 'text/plain', b'invalid attribute or value')

        else:
            _response(writer, '404 Not Found', 'text/plain', b'not found')

        await asyncio.wait_for(writer.drain(), 5)

    except Exception as e:
        log.log('web', f'handler error: {e}  active={_active}  mem_free={gc.mem_free()}')
    finally:
        _active -= 1
        try:
            writer.close()
            await asyncio.wait_for(writer.wait_closed(), 2)
        except Exception:
            pass


class WebServer:

    def __init__(self, controller, port=None):
        self._ctrl = controller
        self._port = port or config.WEB_PORT

    async def run(self):
        ctrl = self._ctrl

        async def handle(reader, writer):
            await _handle(reader, writer, ctrl)

        await asyncio.start_server(handle, '0.0.0.0', self._port)
        log.log('web', f'listening on port {self._port}')
        # Keep the coroutine alive — the server runs in the background.
        while True:
            await asyncio.sleep(3600)
