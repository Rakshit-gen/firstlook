"""A stand-in Prometheus server for tests: answers from a dict of canned
results and records the queries it was asked."""

import json
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer


class FakeProm:
    def __init__(self, answers: dict):
        self.answers = answers  # promql -> result list, or an exception message
        self.asked: list[dict] = []
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                url = urllib.parse.urlparse(self.path)
                q = {k: v[0] for k, v in urllib.parse.parse_qs(url.query).items()}
                fake.asked.append({"path": url.path, **q})
                result = fake.answers.get(q.get("query"), [])
                if isinstance(result, str):
                    code = 400
                    body = {"status": "error", "errorType": "bad_data", "error": result}
                else:
                    code = 200
                    kind = "matrix" if url.path.endswith("query_range") else "vector"
                    body = {"status": "success", "data": {"resultType": kind, "result": result}}
                data = json.dumps(body).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *args):
                pass

        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_port}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()
