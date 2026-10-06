"""仅合成资料HTTP子进程；用于真实断开连接，不启动学校客户端。"""

import json
import multiprocessing
from http.server import BaseHTTPRequestHandler, HTTPServer


def serve(connection):
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            self.rfile.read(int(self.headers.get("Content-Length", "0")))
            body = json.dumps({"student_id": "synthetic", "school": "test",
                               "credential_status": "active", "credential_version": 1}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    connection.send(server.server_port)
    connection.close()
    server.serve_forever()


class AdapterProcess:
    def __enter__(self):
        context = multiprocessing.get_context("spawn")
        parent, child = context.Pipe(duplex=False)
        self.process = context.Process(target=serve, args=(child,), daemon=True)
        self.process.start()
        child.close()
        try:
            if not parent.poll(10):
                raise RuntimeError("合成Adapter进程启动超时")
            self.url = f"http://127.0.0.1:{parent.recv()}"
        except BaseException:
            self.stop()
            raise
        finally:
            parent.close()
        return self

    def stop(self):
        self.process.terminate()
        self.process.join(5)
        if self.process.is_alive():
            self.process.kill()
            self.process.join(5)
        assert not self.process.is_alive()

    def __exit__(self, *args):
        self.stop()
