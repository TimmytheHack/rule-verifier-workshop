"""生成 macOS 本地用户 Web app 和 Library 运行时。"""

from __future__ import annotations

import argparse
import hashlib
import plistlib
import shutil
import stat
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = ROOT / "outputs" / "local_user_app"
DEFAULT_APP_NAME = "本地表格工作台"
EXECUTABLE_NAME = "launch"
APP_SUPPORT_DIR_NAME = "SZU Local Workbench"
DEFAULT_APP_RUNTIME_DIR = (
    Path.home() / "Library/Application Support" / APP_SUPPORT_DIR_NAME / "runtime/workbench"
)
RUNTIME_SCRIPT_FILES = [
    "__init__.py",
    "generate_domain_pack.py",
    "review_domain_pack.py",
]
EXCLUDED_TOOL_SCHEMA_FILES = {"quality.run.json", "pilot.run.json"}


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    app_path = build_app(
        repo_root=_resolve_path(args.repo_root),
        output_dir=_resolve_path(args.output_dir),
        app_name=args.app_name,
        build_frontend=not args.skip_frontend_build,
        include_runtime=not args.skip_runtime_copy,
        install_app_runtime=not args.skip_app_runtime_install,
        app_runtime_dir=_resolve_user_path(args.app_runtime_dir),
    )
    print(f"已生成：{app_path}")
    return 0


def build_app(
    *,
    repo_root: Path,
    output_dir: Path,
    app_name: str,
    build_frontend: bool = True,
    include_runtime: bool = True,
    install_app_runtime: bool = True,
    app_runtime_dir: Path = DEFAULT_APP_RUNTIME_DIR,
) -> Path:
    _validate_app_name(app_name)
    output_dir = output_dir.resolve()
    app_runtime_dir = app_runtime_dir.expanduser().resolve()
    _validate_app_runtime_dir(app_runtime_dir)
    app_path = output_dir / f"{app_name}.app"
    _validate_app_output_path(app_path, output_dir)
    contents_dir = app_path / "Contents"
    macos_dir = contents_dir / "MacOS"
    resources_dir = contents_dir / "Resources"
    source_dir = resources_dir / "workbench_source"

    if app_path.exists():
        if app_path.suffix != ".app":
            raise SystemExit(f"拒绝覆盖非 app 路径：{app_path}")
        shutil.rmtree(app_path)

    if build_frontend:
        _build_frontend(repo_root)

    macos_dir.mkdir(parents=True)
    resources_dir.mkdir(parents=True)
    _write_info_plist(contents_dir / "Info.plist", app_name)
    (contents_dir / "PkgInfo").write_text("APPL????", encoding="ascii")
    _write_shell_launcher(macos_dir / EXECUTABLE_NAME)
    _write_bootstrap_python(resources_dir / "bootstrap_python.txt")
    if include_runtime:
        source_dir.mkdir(parents=True)
        _write_app_launcher(source_dir / "launch_app.py")
        _copy_runtime_source(repo_root, source_dir)
        _write_runtime_version(source_dir)
        if install_app_runtime:
            _install_app_runtime(source_dir, app_runtime_dir)
    return app_path


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="生成 macOS 本地用户 Web app。")
    parser.add_argument("--repo-root", default=str(ROOT))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--app-name", default=DEFAULT_APP_NAME)
    parser.add_argument(
        "--skip-frontend-build",
        action="store_true",
        help="跳过 frontend-user/dist 构建，只复制现有产物。",
    )
    parser.add_argument(
        "--skip-runtime-copy",
        action="store_true",
        help="只生成 app 壳，供单元测试使用。",
    )
    parser.add_argument(
        "--skip-app-runtime-install",
        action="store_true",
        help="跳过安装 Library 运行时，供单元测试使用。",
    )
    parser.add_argument("--app-runtime-dir", default=str(DEFAULT_APP_RUNTIME_DIR))
    return parser.parse_args(argv)


def _resolve_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else (ROOT / path).resolve()


def _resolve_user_path(value: str) -> Path:
    return Path(value).expanduser().resolve()


def _validate_app_name(app_name: str) -> None:
    if not app_name or app_name.strip() != app_name:
        raise SystemExit("app_name 不能为空或包含首尾空白。")
    if "/" in app_name or "\\" in app_name or app_name in {".", ".."}:
        raise SystemExit(f"app_name 不能包含路径分隔符：{app_name}")


def _validate_app_output_path(app_path: Path, output_dir: Path) -> None:
    resolved_output_dir = output_dir.resolve()
    resolved_app_path = app_path.resolve()
    if resolved_app_path.parent != resolved_output_dir:
        raise SystemExit(f"拒绝生成到 output_dir 之外：{app_path}")
    if resolved_app_path.suffix != ".app":
        raise SystemExit(f"输出路径必须是 .app：{app_path}")


def _validate_app_runtime_dir(runtime_dir: Path) -> None:
    runtime_root = (
        Path.home()
        / "Library/Application Support"
        / APP_SUPPORT_DIR_NAME
        / "runtime"
    ).resolve()
    if runtime_dir == runtime_root or runtime_root not in runtime_dir.parents:
        raise SystemExit(f"拒绝使用非应用 runtime 目录：{runtime_dir}")


def _build_frontend(repo_root: Path) -> None:
    frontend_root = repo_root / "frontend-user"
    _run_checked(["npm", "install"], cwd=frontend_root)
    _run_checked(["npm", "run", "build"], cwd=frontend_root)


def _run_checked(command: list[str], *, cwd: Path) -> None:
    try:
        subprocess.run(command, cwd=cwd, check=True)
    except FileNotFoundError as exc:
        raise SystemExit(
            f"找不到命令：{command[0]}。请先安装 Node.js 和 npm。"
        ) from exc
    except subprocess.CalledProcessError as exc:
        raise SystemExit(f"命令执行失败：{' '.join(command)}") from exc


def _copy_runtime_source(repo_root: Path, source_dir: Path) -> None:
    _copy_required_dir(repo_root / "src", source_dir / "src")
    _copy_tool_schemas(
        repo_root / "schemas" / "tools",
        source_dir / "schemas" / "tools",
    )
    _copy_runtime_scripts(repo_root / "scripts", source_dir / "scripts")
    _copy_required_dir(
        repo_root / "frontend-user" / "dist",
        source_dir / "frontend-user" / "dist",
    )
    requirements_path = repo_root / "requirements.txt"
    if requirements_path.exists():
        shutil.copy2(requirements_path, source_dir / "requirements.txt")


def _install_app_runtime(source_dir: Path, runtime_dir: Path) -> None:
    _validate_app_runtime_dir(runtime_dir)
    temp_runtime_dir = runtime_dir.with_name(f".{runtime_dir.name}.tmp")
    if temp_runtime_dir.exists():
        shutil.rmtree(temp_runtime_dir)
    if runtime_dir.parent.exists() and not runtime_dir.parent.is_dir():
        raise SystemExit(f"runtime 父路径不是目录：{runtime_dir.parent}")
    if runtime_dir.exists() and not runtime_dir.is_dir():
        raise SystemExit(f"runtime 路径不是目录：{runtime_dir}")
    runtime_dir.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source_dir, temp_runtime_dir, symlinks=True)
    python_bin = temp_runtime_dir / ".venv/bin/python"
    _run_checked(
        [
            str(Path(sys.executable).resolve()),
            "-m",
            "venv",
            str(temp_runtime_dir / ".venv"),
        ],
        cwd=temp_runtime_dir,
    )
    _run_checked(
        [
            str(python_bin),
            "-m",
            "pip",
            "install",
            "-r",
            str(temp_runtime_dir / "requirements.txt"),
        ],
        cwd=temp_runtime_dir,
    )
    if runtime_dir.exists():
        shutil.rmtree(runtime_dir)
    temp_runtime_dir.rename(runtime_dir)


def _write_runtime_version(source_dir: Path) -> None:
    digest = hashlib.sha256()
    for path in sorted(source_dir.rglob("*")):
        if not path.is_file() or path.name == "runtime_version.txt":
            continue
        digest.update(str(path.relative_to(source_dir)).encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    (source_dir / "runtime_version.txt").write_text(
        digest.hexdigest() + "\n",
        encoding="ascii",
    )


def _copy_required_dir(source: Path, target: Path) -> None:
    if not source.exists():
        raise SystemExit(f"缺少运行时目录：{source}")
    shutil.copytree(source, target, symlinks=True, ignore=_ignore_runtime_files)


def _copy_runtime_scripts(source: Path, target: Path) -> None:
    if not source.exists():
        raise SystemExit(f"缺少运行时目录：{source}")
    target.mkdir(parents=True, exist_ok=True)
    for name in RUNTIME_SCRIPT_FILES:
        script_path = source / name
        if not script_path.exists():
            raise SystemExit(f"缺少运行时脚本：{script_path}")
        shutil.copy2(script_path, target / name)


def _copy_tool_schemas(source: Path, target: Path) -> None:
    if not source.exists():
        raise SystemExit(f"缺少 tool schema 目录：{source}")
    target.mkdir(parents=True, exist_ok=True)
    for schema_path in sorted(source.glob("*.json")):
        if schema_path.name in EXCLUDED_TOOL_SCHEMA_FILES:
            continue
        shutil.copy2(schema_path, target / schema_path.name)


def _ignore_runtime_files(_directory: str, names: list[str]) -> set[str]:
    ignored = {
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        ".DS_Store",
    }
    return {
        name
        for name in names
        if name in ignored or name.endswith((".pyc", ".pyo"))
    }


def _write_info_plist(path: Path, app_name: str) -> None:
    payload = {
        "CFBundleDisplayName": app_name,
        "CFBundleExecutable": EXECUTABLE_NAME,
        "CFBundleIdentifier": "local.szu.table-workbench",
        "CFBundleName": app_name,
        "CFBundlePackageType": "APPL",
        "CFBundleShortVersionString": "0.2.0",
        "CFBundleVersion": "2",
        "LSMinimumSystemVersion": "12.0",
    }
    with path.open("wb") as handle:
        plistlib.dump(payload, handle, sort_keys=True)


def _write_bootstrap_python(path: Path) -> None:
    path.write_text(str(Path(sys.executable).resolve()) + "\n", encoding="utf-8")


def _write_shell_launcher(path: Path) -> None:
    path.write_text(
        f"""#!/bin/zsh
set -e

RESOURCE_DIR="$(cd "$(dirname "$0")/../Resources" && pwd)"
SOURCE_ROOT="$RESOURCE_DIR/workbench_source"
APP_SUPPORT_DIR="$HOME/Library/Application Support/{APP_SUPPORT_DIR_NAME}"
APP_ROOT="$APP_SUPPORT_DIR/runtime/workbench"
LOG_DIR="$APP_SUPPORT_DIR/logs"
mkdir -p "$LOG_DIR"

{{
  echo "==== $(date '+%Y-%m-%d %H:%M:%S') 启动本地用户 Web app ===="
  if [ ! -d "$SOURCE_ROOT" ]; then
    echo "缺少 app source snapshot：$SOURCE_ROOT"
    exit 1
  fi
  SOURCE_VERSION="$(cat "$SOURCE_ROOT/runtime_version.txt" 2>/dev/null || true)"
  RUNTIME_VERSION="$(cat "$APP_ROOT/runtime_version.txt" 2>/dev/null || true)"
  if [ ! -x "$APP_ROOT/.venv/bin/python" ] || [ "$SOURCE_VERSION" != "$RUNTIME_VERSION" ]; then
    BOOTSTRAP_PYTHON="$(cat "$RESOURCE_DIR/bootstrap_python.txt" 2>/dev/null || true)"
    if [ ! -x "$BOOTSTRAP_PYTHON" ]; then
      echo "缺少可用 Python：$BOOTSTRAP_PYTHON"
      echo "请重新运行 make macos-app。"
      exit 1
    fi
    rm -rf "$APP_ROOT"
    mkdir -p "$(dirname "$APP_ROOT")"
    /usr/bin/ditto "$SOURCE_ROOT" "$APP_ROOT"
    "$BOOTSTRAP_PYTHON" -m venv "$APP_ROOT/.venv"
    "$APP_ROOT/.venv/bin/python" -m pip install -r "$APP_ROOT/requirements.txt"
  fi
  PYTHON_BIN="$APP_ROOT/.venv/bin/python"
  if [ ! -x "$PYTHON_BIN" ]; then
    echo "缺少本机 Python 运行时：$PYTHON_BIN"
    exit 1
  fi
  export PYTHONDONTWRITEBYTECODE=1
  cd "$APP_ROOT"
  "$PYTHON_BIN" "$APP_ROOT/launch_app.py"
}} >> "$LOG_DIR/app.log" 2>&1
""",
        encoding="utf-8",
    )
    _mark_executable(path)


def _write_app_launcher(path: Path) -> None:
    path.write_text(
        f'''"""本地用户 Web app 的内置启动器。"""

from __future__ import annotations

import json
import os
import secrets
import socket
import subprocess
import sys
import webbrowser
from pathlib import Path


APP_ROOT = Path(__file__).resolve().parent
HOST = "127.0.0.1"
DEFAULT_PORT = 8001
APP_SUPPORT_DIR = Path.home() / "Library/Application Support/{APP_SUPPORT_DIR_NAME}"
PERMISSION_SCOPES = [
    "read_only",
    "query",
    "confirm",
    "dataset_write",
    "review_admin",
    "warehouse_admin",
    "diagnostics",
]


def main() -> int:
    data_root = APP_SUPPORT_DIR / "uploaded_datasets"
    output_root = APP_SUPPORT_DIR / "outputs"
    settings_path = APP_SUPPORT_DIR / "local_settings" / "llm.json"
    audit_path = output_root / "tool_audit" / "audit.jsonl"
    for directory in [
        data_root,
        output_root,
        settings_path.parent,
        audit_path.parent,
    ]:
        directory.mkdir(parents=True, exist_ok=True)

    token = secrets.token_urlsafe(24)
    env = dict(os.environ)
    env.update(
        {{
            "APP_DISTRIBUTION_MODE": "user_upload_only",
            "PYTHONDONTWRITEBYTECODE": "1",
            "AUTH_TOKENS_JSON": json.dumps(
                {{
                    token: {{
                        "actor_id": "local_app",
                        "permission_scopes": PERMISSION_SCOPES,
                    }}
                }},
                separators=(",", ":"),
            ),
            "LOCAL_USER_AUTO_AUTH_TOKEN": token,
            "DATA_ROOT": str(data_root),
            "OUTPUT_ROOT": str(output_root),
            "TOOL_AUDIT_LOG_PATH": str(audit_path),
            "LOCAL_SETTINGS_PATH": str(settings_path),
            "FRONTEND_USER_DIST": str(APP_ROOT / "frontend-user" / "dist"),
        }}
    )

    port = choose_port(HOST, DEFAULT_PORT)
    url = f"http://{{HOST}}:{{port}}"
    print(f"本地用户 Web 已准备启动：{{url}}", flush=True)
    webbrowser.open(url)
    return run_uvicorn(port, env)


def choose_port(host: str, requested_port: int) -> int:
    if port_available(host, requested_port):
        return requested_port
    for port in range(requested_port + 1, requested_port + 100):
        if port_available(host, port):
            print(f"端口 {{requested_port}} 已被占用，改用 {{port}}。", flush=True)
            return port
    raise SystemExit("没有找到可用端口。")


def port_available(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((host, port))
        except OSError:
            return False
    return True


def run_uvicorn(port: int, env: dict[str, str]) -> int:
    command = [
        sys.executable,
        "-m",
        "uvicorn",
        "src.api.server:app",
        "--host",
        HOST,
        "--port",
        str(port),
    ]
    try:
        return subprocess.call(command, cwd=APP_ROOT, env=env)
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
''',
        encoding="utf-8",
    )


def _mark_executable(path: Path) -> None:
    current_mode = stat.S_IMODE(path.stat().st_mode)
    path.chmod(current_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


if __name__ == "__main__":
    raise SystemExit(main())
