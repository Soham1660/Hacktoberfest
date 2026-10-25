"""`python -m pr_checker` starts the server."""
from __future__ import annotations

import argparse
import os
import socket


def main() -> None:
    parser = argparse.ArgumentParser(prog="pr-checker", description="Audit a pull request against its description with a local open-weight model.")
    parser.add_argument("--host", default="127.0.0.1", help="interface to bind (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT") or 8787), help="port (default: $PORT or 8787)")
    parser.add_argument("--reload", action="store_true", help="restart on code changes (development)")
    args = parser.parse_args()

    probe = socket.socket()
    try:
        probe.bind((args.host, args.port))
    except OSError:
        raise SystemExit(
            f"Port {args.port} is already in use. Stop whatever is listening there "
            f"(find it with: lsof -nP -iTCP:{args.port} -sTCP:LISTEN) or pick another port: python -m pr_checker --port {args.port + 1}"
        )
    finally:
        probe.close()

    os.environ["PORT"] = str(args.port)
    import uvicorn

    uvicorn.run("pr_checker.server:app", host=args.host, port=args.port, reload=args.reload, log_level="warning")


if __name__ == "__main__":
    main()
