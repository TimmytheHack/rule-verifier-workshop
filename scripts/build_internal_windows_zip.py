"""生成 Windows 内测 zip 包。"""

from __future__ import annotations

import argparse
import hashlib
import shutil
import sys
import zipfile
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.build_local_user_app import (  # noqa: E402
    APP_SUPPORT_DIR_NAME,
    APP_VERSION,
    DEFAULT_APP_NAME,
    _build_frontend,
    _copy_runtime_source,
    _write_runtime_version,
)


DEFAULT_OUTPUT_DIR = ROOT / "outputs" / "local_user_app"
README_NAME = "内测说明-Windows.md"
FORBIDDEN_PACKAGE_NAMES = {
    ".env",
    "uploaded_datasets",
    "local_settings",
    "tool_audit",
}


@dataclass(frozen=True)
class WindowsZipArtifacts:
    """Windows zip 构建产物路径。"""

    zip_path: Path
    checksum_path: Path
    readme_path: Path
    package_dir: Path

    def to_dict(self) -> dict[str, str]:
        return {
            "zip_path": str(self.zip_path),
            "checksum_path": str(self.checksum_path),
            "readme_path": str(self.readme_path),
            "package_dir": str(self.package_dir),
        }


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    artifacts = build_internal_windows_zip(
        repo_root=_resolve_path(args.repo_root),
        output_dir=_resolve_path(args.output_dir),
        app_name=args.app_name,
        version=args.version,
        build_frontend=not args.skip_frontend_build,
        keep_staging=args.keep_staging,
    )
    print(f"已生成 Windows zip：{artifacts.zip_path}")
    print(f"SHA256：{artifacts.checksum_path}")
    print(f"说明：{artifacts.readme_path}")
    return 0


def build_internal_windows_zip(
    *,
    repo_root: Path = ROOT,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    app_name: str = DEFAULT_APP_NAME,
    version: str = APP_VERSION,
    build_frontend: bool = True,
    keep_staging: bool = False,
) -> WindowsZipArtifacts:
    """构建 Windows 内测 zip，并写出 sidecar README 和 SHA256。"""

    repo_root = repo_root.resolve()
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    if build_frontend:
        _build_frontend(repo_root)

    package_stem = f"{app_name}-{version}-windows-internal"
    zip_path = output_dir / f"{package_stem}.zip"
    checksum_path = output_dir / f"{package_stem}.sha256"
    readme_path = output_dir / f"{package_stem}.README.md"
    staging_dir = output_dir / f".{package_stem}-staging"
    package_dir = staging_dir / package_stem
    source_dir = package_dir / "workbench_source"

    if staging_dir.exists():
        shutil.rmtree(staging_dir)
    package_dir.mkdir(parents=True)
    try:
        source_dir.mkdir(parents=True)
        _write_windows_app_launcher(source_dir / "launch_app.py")
        _copy_runtime_source(repo_root, source_dir)
        _write_runtime_version(source_dir)
        _write_batch_launcher(package_dir / "start_local_user_web.bat")
        _write_readme(package_dir / README_NAME, app_name=app_name, version=version)
        _validate_staging(package_dir)
        _create_zip(staging_dir, zip_path)
    finally:
        if not keep_staging and staging_dir.exists():
            shutil.rmtree(staging_dir)

    digest = _sha256_file(zip_path)
    checksum_path.write_text(f"{digest}  {zip_path.name}\n", encoding="utf-8")
    _write_readme(
        readme_path,
        app_name=app_name,
        version=version,
        zip_name=zip_path.name,
        sha256=digest,
    )
    return WindowsZipArtifacts(
        zip_path=zip_path,
        checksum_path=checksum_path,
        readme_path=readme_path,
        package_dir=package_dir,
    )


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="生成 Windows 内测 zip 包。")
    parser.add_argument("--repo-root", default=str(ROOT))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--app-name", default=DEFAULT_APP_NAME)
    parser.add_argument("--version", default=APP_VERSION)
    parser.add_argument(
        "--skip-frontend-build",
        action="store_true",
        help="跳过 frontend-user/dist 构建，只复制现有产物。",
    )
    parser.add_argument(
        "--keep-staging",
        action="store_true",
        help="保留 zip staging 目录，供人工排查。",
    )
    return parser.parse_args(argv)


def _resolve_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else (ROOT / path).resolve()


def _write_batch_launcher(path: Path) -> None:
    path.write_text(
        f"""@echo off
setlocal EnableExtensions
chcp 65001 >nul

set "PACKAGE_DIR=%~dp0"
set "SOURCE_ROOT=%PACKAGE_DIR%workbench_source"
if "%LOCALAPPDATA%"=="" (
  set "APP_SUPPORT_DIR=%USERPROFILE%\\AppData\\Local\\{APP_SUPPORT_DIR_NAME}"
) else (
  set "APP_SUPPORT_DIR=%LOCALAPPDATA%\\{APP_SUPPORT_DIR_NAME}"
)
set "APP_ROOT=%APP_SUPPORT_DIR%\\runtime\\workbench"
set "LOG_DIR=%APP_SUPPORT_DIR%\\logs"
mkdir "%LOG_DIR%" >nul 2>nul

call :run >> "%LOG_DIR%\\app.log" 2>&1
set "EXIT_CODE=%ERRORLEVEL%"
if not "%EXIT_CODE%"=="0" (
  echo 本地表格工作台启动失败，日志位置：
  echo %LOG_DIR%\\app.log
  pause
)
exit /b %EXIT_CODE%

:run
echo ==== %DATE% %TIME% 启动 Windows 本地用户 Web ====
if not exist "%SOURCE_ROOT%\\launch_app.py" (
  echo 缺少 package source snapshot：%SOURCE_ROOT%
  exit /b 1
)

call :find_python
if not "%ERRORLEVEL%"=="0" (
  echo 缺少 Python 3.11+，无法初始化本地运行时。
  echo 请先安装 Python 3.11 或联系内测维护者。
  exit /b 1
)

set "NEEDS_REFRESH=0"
if not exist "%APP_ROOT%\\.venv\\Scripts\\python.exe" set "NEEDS_REFRESH=1"
if not exist "%APP_ROOT%\\runtime_version.txt" set "NEEDS_REFRESH=1"
if "%NEEDS_REFRESH%"=="0" (
  fc /b "%SOURCE_ROOT%\\runtime_version.txt" "%APP_ROOT%\\runtime_version.txt" >nul 2>nul
  if errorlevel 1 set "NEEDS_REFRESH=1"
)

if "%NEEDS_REFRESH%"=="1" (
  if exist "%APP_ROOT%" rmdir /s /q "%APP_ROOT%"
  mkdir "%APP_ROOT%" >nul 2>nul
  robocopy "%SOURCE_ROOT%" "%APP_ROOT%" /MIR /NFL /NDL /NJH /NJS /NP
  if errorlevel 8 exit /b %ERRORLEVEL%
  "%BOOTSTRAP_PYTHON_EXE%" %BOOTSTRAP_PYTHON_ARGS% -m venv "%APP_ROOT%\\.venv"
  if errorlevel 1 exit /b %ERRORLEVEL%
  "%APP_ROOT%\\.venv\\Scripts\\python.exe" -m pip install -r "%APP_ROOT%\\requirements.txt"
  if errorlevel 1 exit /b %ERRORLEVEL%
)

set "PYTHON_BIN=%APP_ROOT%\\.venv\\Scripts\\python.exe"
if not exist "%PYTHON_BIN%" (
  echo 缺少本机 Python 运行时：%PYTHON_BIN%
  exit /b 1
)
set "PYTHONDONTWRITEBYTECODE=1"
cd /d "%APP_ROOT%"
"%PYTHON_BIN%" "%APP_ROOT%\\launch_app.py"
exit /b %ERRORLEVEL%

:find_python
set "BOOTSTRAP_PYTHON_EXE="
set "BOOTSTRAP_PYTHON_ARGS="
for /f "delims=" %%I in ('where py 2^>nul') do (
  "%%I" -3.11 -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>nul
  if not errorlevel 1 (
    set "BOOTSTRAP_PYTHON_EXE=%%I"
    set "BOOTSTRAP_PYTHON_ARGS=-3.11"
    exit /b 0
  )
)
for %%P in (python python3) do (
  for /f "delims=" %%I in ('where %%P 2^>nul') do (
    "%%I" -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>nul
    if not errorlevel 1 (
      set "BOOTSTRAP_PYTHON_EXE=%%I"
      set "BOOTSTRAP_PYTHON_ARGS="
      exit /b 0
    )
  )
)
exit /b 1
""",
        encoding="utf-8",
    )


def _write_windows_app_launcher(path: Path) -> None:
    path.write_text(
        f'''"""Windows 本地用户 Web 的内置启动器。"""

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
APP_SUPPORT_DIR_NAME = "{APP_SUPPORT_DIR_NAME}"
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
    app_support_dir = default_app_support_dir()
    data_root = app_support_dir / "uploaded_datasets"
    output_root = app_support_dir / "outputs"
    settings_path = app_support_dir / "local_settings" / "llm.json"
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
                        "actor_id": "local_windows_app",
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


def default_app_support_dir() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data) / APP_SUPPORT_DIR_NAME
    return Path.home() / "AppData" / "Local" / APP_SUPPORT_DIR_NAME


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


def _write_readme(
    path: Path,
    *,
    app_name: str,
    version: str,
    zip_name: str | None = None,
    sha256: str | None = None,
) -> None:
    checksum_block = ""
    if zip_name and sha256:
        checksum_block = f"""
## 校验

下载后可在 PowerShell 运行：

```powershell
Get-FileHash "{zip_name}" -Algorithm SHA256
```

期望 SHA256：

```text
{sha256}  {zip_name}
```
"""
    path.write_text(
        f"""# {app_name} {version} Windows 内测包

这是 Windows portable zip 内测包，只建议发给受信任测试用户。

## 打开方式

1. 解压 `{app_name}-{version}-windows-internal.zip`。
2. 双击 `start_local_user_web.bat`。
3. 页面打开后进入“设置”，选择 LLM provider，填入自己的 API key。
4. 上传 Excel/CSV 后，系统会在本机生成规则和结构化存储；关闭后再次打开仍会保留。

## 本机数据

- 上传表格、规则、warehouse、日志和 LLM 设置默认保存在 `%LOCALAPPDATA%\\{APP_SUPPORT_DIR_NAME}\\`。
- zip 不包含仓库 `.env`、真实上传表格、旧 mock/demo 数据或临时 `outputs` 产物。
- API key 存在本机设置文件中，页面和 API 不回显明文。
- 启用 LLM 后，用户 query 和必要 schema/候选上下文会发送给所选 provider；系统不把整张表默认上传给 provider。

## 内测限制

- 当前包要求 Windows 10/11，并且首次启动时本机需要可用的 Python 3.11+ 来初始化运行时。
- 首次启动需要安装 Python 依赖，可能需要几分钟和网络访问。
- 这不是正式安装器；正式发版前仍需要 Windows 签名、安装器和更完整的自动升级策略。

## 清理

退出 app 后，可删除 `%LOCALAPPDATA%\\{APP_SUPPORT_DIR_NAME}\\` 来清空本机上传数据、规则、日志和 LLM 设置。
{checksum_block}""",
        encoding="utf-8",
    )


def _validate_staging(package_dir: Path) -> None:
    for path in package_dir.rglob("*"):
        relative_parts = set(path.relative_to(package_dir).parts)
        forbidden = relative_parts & FORBIDDEN_PACKAGE_NAMES
        if forbidden:
            raise SystemExit(
                f"Windows zip staging 包含禁止发布的路径：{path.relative_to(package_dir)}"
            )


def _create_zip(staging_dir: Path, zip_path: Path) -> None:
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(staging_dir.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(staging_dir).as_posix())


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
