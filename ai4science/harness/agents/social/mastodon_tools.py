"""In-sandbox Mastodon HTTP client, spoken over the egress unix socket.

These helpers build ``argv`` lists of the shape ``["python3", "-c",
<script>, ...]`` where ``<script>`` is a small, dependency-free Python
program that talks raw HTTP/1.1 to ``/run/egress.sock`` (an
``AF_UNIX`` socket). The egress proxy on the other end of that socket
is responsible for routing the request to the real Mastodon instance
and injecting the ``Authorization`` header — the script generated here
never sees, holds, or transmits a token/secret of any kind.

Two commands are provided:

- ``timeline_command(host)``: GET ``/api/v1/timelines/home``.
- ``post_command(host, text)``: POST ``/api/v1/statuses`` with a
  urlencoded ``status=<text>`` body. ``text`` is passed to the sandboxed
  process as ``sys.argv[1]`` (an actual argv element) rather than being
  string-interpolated into the script source, so arbitrary post text
  (quotes, newlines, shell metacharacters, ...) can never break the
  generated script or leak into a shell.

Only the standard library (``socket``, ``sys``, ``urllib.parse``) is
used inside the generated scripts, so they run under any sandbox
image that ships a stock ``python3``.
"""

from __future__ import annotations

EGRESS_SOCKET = "/run/egress.sock"

_READ_RESPONSE_BODY = '''
data = b""
while True:
    chunk = s.recv(4096)
    if not chunk:
        break
    data += chunk
s.close()

parts = data.split(b"\\r\\n\\r\\n", 1)
body = parts[1] if len(parts) > 1 else b""
sys.stdout.buffer.write(body)
'''


def timeline_command(host: str) -> list[str]:
    """Build the argv for fetching the Mastodon home timeline.

    Returns ``["python3", "-c", <script>]`` where ``<script>`` connects
    to the egress unix socket and issues a GET
    ``/api/v1/timelines/home`` request for ``host``, printing the
    response body to stdout.
    """
    request = (
        "GET /api/v1/timelines/home HTTP/1.1\r\n"
        f"Host: {host}\r\n"
        "Connection: close\r\n"
        "\r\n"
    )
    script = f'''import socket, sys

req = {request!r}

s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
s.connect({EGRESS_SOCKET!r})
s.sendall(req.encode())
{_READ_RESPONSE_BODY}'''
    return ["python3", "-c", script]


def post_command(host: str, text: str) -> list[str]:
    """Build the argv for posting a status to Mastodon.

    Returns ``["python3", "-c", <script>, text]`` where ``<script>``
    connects to the egress unix socket and issues a POST
    ``/api/v1/statuses`` request for ``host`` with a urlencoded
    ``status=<text>`` body, printing the response body to stdout.
    The post text is read by the script from ``sys.argv[1]`` at run
    time, not interpolated into the script source.
    """
    header_prefix = (
        "POST /api/v1/statuses HTTP/1.1\r\n"
        f"Host: {host}\r\n"
        "Content-Type: application/x-www-form-urlencoded\r\n"
    )
    script = f'''import socket, sys
from urllib.parse import urlencode

text = sys.argv[1]
body = urlencode({{"status": text}}).encode()

header_prefix = {header_prefix!r}
headers = header_prefix + "Content-Length: " + str(len(body)) + "\\r\\nConnection: close\\r\\n\\r\\n"

s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
s.connect({EGRESS_SOCKET!r})
s.sendall(headers.encode() + body)
{_READ_RESPONSE_BODY}'''
    return ["python3", "-c", script, text]
