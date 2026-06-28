"""启动同端口本地用户 Web 和 API。"""

from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import webbrowser
from collections.abc import Mapping
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8001
DEFAULT_FRONTEND_DIST = ROOT / "frontend-user" / "dist"
DEFAULT_DEV_OPERATOR_TOKEN = "operator-token"
DEFAULT_DEV_AUTH_TOKENS = {
    DEFAULT_DEV_OPERATOR_TOKEN: {
        "actor_id": "operator",
        "permission_scopes": [
            "read_only",
            "query",
            "confirm",
            "dataset_write",
            "review_admin",
            "warehouse_admin",
            "diagnostics",
        ],
    },
    "agent-token": {
        "actor_id": "agent",
        "permission_scopes": ["read_only", "query", "confirm"],
    },
}


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    dist_path = _resolve_frontend_dist(args.frontend_dist)

    if not args.skip_build and not args.dry_run:
        _build_frontend()

    port = _choose_port(args.host, args.port, args.auto_port)
    url = f"http://{args.host}:{port}"
    env = launcher_environment(os.environ, dist_path, host=args.host)

    if args.dry_run:
        print(
            json.dumps(
                {
                    "url": url,
                    "frontend_dist": str(dist_path),
                    "auto_auth_cookie": bool(env.get("LOCAL_USER_AUTO_AUTH_TOKEN")),
                    "distribution_mode": env.get("APP_DISTRIBUTION_MODE"),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    print(f"本地用户 Web 已准备启动：{url}", flush=True)
    print("按 Ctrl+C 停止服务。", flush=True)
    if not args.no_open:
        webbrowser.open(url)
    return _run_uvicorn(args.host, port, env)


def launcher_environment(
    base_env: Mapping[str, str],
    dist_path: Path,
    *,
    host: str = DEFAULT_HOST,
) -> dict[str, str]:
    env = dict(base_env)
    if not env.get("AUTH_TOKENS_JSON"):
        if not _is_loopback_host(host):
            raise SystemExit(
                "未配置 AUTH_TOKENS_JSON 时，只能在 127.0.0.1 或 localhost 启动。"
            )
        env["AUTH_TOKENS_JSON"] = json.dumps(
            DEFAULT_DEV_AUTH_TOKENS,
            separators=(",", ":"),
        )
        env.setdefault("LOCAL_USER_AUTO_AUTH_TOKEN", DEFAULT_DEV_OPERATOR_TOKEN)
    env.setdefault("APP_DISTRIBUTION_MODE", "user_upload_only")
    env["FRONTEND_USER_DIST"] = str(dist_path)
    return env


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="启动本地用户 Web。")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--frontend-dist", default=str(DEFAULT_FRONTEND_DIST))
    parser.add_argument("--skip-build", action="store_true")
    parser.add_argument("--no-open", action="store_true")
    parser.add_argument("--no-auto-port", dest="auto_port", action="store_false")
    parser.add_argument("--dry-run", action="store_true")
    parser.set_defaults(auto_port=True)
    return parser.parse_args(argv)


def _resolve_frontend_dist(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else (ROOT / path).resolve()


def _build_frontend() -> None:
    _run_checked(["npm", "install"], cwd=ROOT / "frontend-user")
    _run_checked(["npm", "run", "build"], cwd=ROOT / "frontend-user")


def _run_checked(command: list[str], *, cwd: Path) -> None:
    try:
        subprocess.run(command, cwd=cwd, check=True)
    except FileNotFoundError as exc:
        raise SystemExit(
            f"找不到命令：{command[0]}。请先安装 Node.js 和 npm。"
        ) from exc
    except subprocess.CalledProcessError as exc:
        raise SystemExit(f"命令执行失败：{' '.join(command)}") from exc


def _choose_port(host: str, requested_port: int, auto_port: bool) -> int:
    if _port_available(host, requested_port):
        return requested_port
    if not auto_port:
        raise SystemExit(f"端口 {requested_port} 已被占用。")
    for port in range(requested_port + 1, requested_port + 100):
        if _port_available(host, port):
            print(f"端口 {requested_port} 已被占用，改用 {port}。", flush=True)
            return port
    raise SystemExit("没有找到可用端口。")


def _port_available(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((host, port))
        except OSError:
            return False
    return True


def _is_loopback_host(host: str) -> bool:
    return host in {"127.0.0.1", "localhost", "::1"}


def _run_uvicorn(host: str, port: int, env: dict[str, str]) -> int:
    command = [
        sys.executable,
        "-m",
        "uvicorn",
        "src.api.server:app",
        "--host",
        host,
        "--port",
        str(port),
    ]
    try:
        return subprocess.call(command, cwd=ROOT, env=env)
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
