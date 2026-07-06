"""Standard-library HTTP server for the local dashboard."""

from __future__ import annotations

from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.resources
import json
import secrets
from pathlib import Path
import threading
from typing import Any
from urllib.parse import parse_qs, urlparse
import webbrowser

from ..usage.aggregation import AnalyticsStore
from ..config.workers import WorkerManifestStore, builtin_workers


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
    handler = _handler(
        store,
        worker_store=WorkerManifestStore(),
        config_write_enabled=host in {"127.0.0.1", "::1", "localhost"},
    )
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


def _handler(
    store: AnalyticsStore,
    *,
    worker_store: WorkerManifestStore | None = None,
    config_write_enabled: bool = True,
) -> type[BaseHTTPRequestHandler]:
    workers = worker_store or WorkerManifestStore()
    csrf_token = secrets.token_urlsafe(24)

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

        def do_PUT(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path != "/api/workers":
                self._json({"error": "not found"}, HTTPStatus.NOT_FOUND)
                return
            if not config_write_enabled:
                self._json({"error": "worker configuration writes require loopback binding"}, HTTPStatus.FORBIDDEN)
                return
            if self.headers.get("X-C4-CSRF") != csrf_token:
                self._json({"error": "invalid CSRF token"}, HTTPStatus.FORBIDDEN)
                return
            try:
                content_type = self.headers.get("Content-Type", "")
                if not content_type.lower().startswith("application/json"):
                    raise TypeError("worker manifest requires application/json")
                length = int(self.headers.get("Content-Length", "0"))
                if length < 1 or length > 256 * 1024:
                    raise ValueError("worker manifest request must be between 1 byte and 256KB")
                payload = json.loads(self.rfile.read(length))
                expected = str(payload.get("revision", ""))
                saved = workers.save(payload, expected_revision=expected)
                self._json({**saved, "csrf_token": csrf_token, "write_enabled": True})
            except json.JSONDecodeError as error:
                self._json({"error": f"invalid JSON: {error}"}, HTTPStatus.BAD_REQUEST)
            except TypeError as error:
                self._json({"error": str(error)}, HTTPStatus.BAD_REQUEST)
            except ValueError as error:
                status = HTTPStatus.CONFLICT if "revision conflict" in str(error) else HTTPStatus.UNPROCESSABLE_ENTITY
                self._json({"error": str(error)}, status)

        def log_message(self, format: str, *args: Any) -> None:
            return

        def _api(self, path: str, query: dict[str, list[str]]) -> None:
            value = lambda key, default="": query.get(key, [default])[0]
            if path == "/api/metadata":
                payload = {
                    **store.metadata(),
                    "filters": store.filter_options(),
                    "csrf_token": csrf_token,
                    "worker_config_write_enabled": config_write_enabled,
                }
            elif path == "/api/workers":
                payload = {
                    **workers.load_document(),
                    "defaults": builtin_workers(),
                    "csrf_token": csrf_token,
                    "write_enabled": config_write_enabled,
                    "path": str(workers.path),
                }
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
