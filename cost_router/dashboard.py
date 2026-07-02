from __future__ import annotations

from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.resources
import json
from pathlib import Path
import threading
from typing import Any
from urllib.parse import parse_qs, urlparse
import webbrowser

from .analytics import AnalyticsStore


STATIC_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
}


def serve_dashboard(
    memory_path: Path,
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
    open_browser: bool = True,
) -> None:
    store = AnalyticsStore(memory_path)
    store.metadata()
    handler = _handler(store)
    server = ThreadingHTTPServer((host, port), handler)
    display_host = "127.0.0.1" if host == "0.0.0.0" else host
    url = f"http://{display_host}:{server.server_port}"
    print(f"Cost Router Dashboard: {url}")
    print(f"Ledger: {memory_path.resolve()}")
    if open_browser:
        threading.Timer(0.35, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nDashboard stopped.")
    finally:
        server.server_close()


def _handler(store: AnalyticsStore) -> type[BaseHTTPRequestHandler]:
    class DashboardHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            try:
                if parsed.path.startswith("/api/"):
                    self._api(parsed.path, parse_qs(parsed.query))
                else:
                    self._static(parsed.path)
            except (ValueError, TypeError) as error:
                self._json({"error": str(error)}, HTTPStatus.BAD_REQUEST)
            except Exception as error:  # pragma: no cover - defensive server boundary
                self._json({"error": f"dashboard error: {error}"}, HTTPStatus.INTERNAL_SERVER_ERROR)

        def log_message(self, format: str, *args: Any) -> None:
            return

        def _api(self, path: str, query: dict[str, list[str]]) -> None:
            value = lambda key, default="": query.get(key, [default])[0]
            if path == "/api/metadata":
                payload = {**store.metadata(), "filters": store.filter_options()}
            elif path == "/api/overview":
                payload = store.overview(value("range", "30d"), value("timezone", "UTC"))
            elif path == "/api/timeseries":
                payload = store.timeseries(
                    value("range", "30d"),
                    value("bucket", "day"),
                    value("metric", "delegated_tokens"),
                    value("timezone", "UTC"),
                )
            elif path == "/api/calls":
                payload = store.calls(
                    range_name=value("range", "all"),
                    backend=value("backend"),
                    model=value("model"),
                    status=value("status"),
                    project=value("project"),
                    query=value("query"),
                    page=int(value("page", "1")),
                    page_size=int(value("page_size", "20")),
                )
            elif path.startswith("/api/calls/"):
                subtask_id = int(path.rsplit("/", 1)[-1])
                payload = store.call_detail(subtask_id)
                if payload is None:
                    self._json({"error": "call not found"}, HTTPStatus.NOT_FOUND)
                    return
            else:
                self._json({"error": "not found"}, HTTPStatus.NOT_FOUND)
                return
            self._json(payload)

        def _static(self, path: str) -> None:
            name = "index.html" if path in {"", "/"} else path.lstrip("/")
            if name not in {"index.html", "app.js", "styles.css"}:
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            resource = importlib.resources.files("cost_router.web").joinpath(name)
            data = resource.read_bytes()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", STATIC_TYPES[Path(name).suffix])
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def _json(self, payload: Any, status: HTTPStatus = HTTPStatus.OK) -> None:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

    return DashboardHandler
