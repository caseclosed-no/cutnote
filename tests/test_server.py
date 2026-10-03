import json
import threading
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from cutnote import RenderOptions, render_note
from cutnote.server import make_server


@pytest.fixture(scope="module")
def server():
    with make_server() as instance:
        thread = threading.Thread(target=instance.serve_forever, daemon=True)
        thread.start()
        yield instance
        instance.shutdown()
        thread.join(timeout=5)


def request(server, path="/", payload=None, headers=None):
    body = json.dumps(payload).encode() if payload is not None else None
    request_headers = {"Content-Type": "application/json"} if body is not None else {}
    request_headers.update(headers or {})
    req = Request(server.origin + path, data=body, headers=request_headers)
    try:
        response = urlopen(req, timeout=10)
    except HTTPError as exc:
        response = exc
    with response:
        return response.status, response.headers, response.read()


@pytest.mark.parametrize(
    "path,mime",
    [
        ("/", "text/html"),
        ("/app.css", "text/css"),
        ("/app.js", "text/javascript"),
        ("/logo.svg", "image/svg+xml"),
    ],
)
def test_assets_are_bundled_and_served_with_security_headers(server, path, mime):
    status, headers, body = request(server, path)
    assert status == 200
    assert headers["Content-Type"].startswith(mime)
    assert "frame-ancestors 'none'" in headers["Content-Security-Policy"]
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert body


def test_render_api_matches_cli_renderer(server):
    options = {"seed": 42, "preset": "mixed", "background": "transparent"}
    status, _, body = request(
        server, "/api/render", {"text": "Follow the crumbs.", "options": options}
    )
    assert status == 200
    result = json.loads(body)
    expected = render_note("Follow the crumbs.", RenderOptions(**options))
    assert result == {
        "svg": expected.svg,
        "seed": expected.seed,
        "width": expected.width,
        "height": expected.height,
    }


@pytest.mark.parametrize(
    "headers",
    [
        {"Origin": "https://external.example"},
        {"Host": "external.example"},
        {"Sec-Fetch-Site": "cross-site"},
    ],
)
def test_external_requests_rejected(server, headers):
    status, _, _ = request(server, "/api/render", {"text": "Hello", "options": {}}, headers)
    assert status == 403


@pytest.mark.parametrize(
    "payload",
    [
        {},
        [],
        {"text": "Hello", "options": []},
        {"text": "", "options": {}},
        {"text": None, "options": {}},
        {"text": "Hello", "options": {"unknown": True}},
        {"text": "Hello", "options": {"seed": True}},
        {"text": "Hello", "options": {"width": "invalid"}},
    ],
)
def test_invalid_render_payloads(server, payload):
    status, _, body = request(server, "/api/render", payload)
    assert status == 400
    assert json.loads(body)["error"]


def test_unknown_routes_and_wrong_content_type(server):
    assert request(server, "/../pyproject.toml")[0] == 404
    assert request(server, "/api/unknown", {"text": "Hello"})[0] == 404
    assert request(server, "/api/render", {}, {"Content-Type": "text/plain"})[0] == 415


def test_body_size_limit(server):
    status, _, _ = request(server, "/api/render", {"text": "x" * 70000, "options": {}})
    assert status == 413
