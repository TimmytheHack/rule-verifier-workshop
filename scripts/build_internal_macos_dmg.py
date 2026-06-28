"""生成 macOS 内测 DMG 包。"""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.build_local_user_app import APP_VERSION, DEFAULT_APP_NAME, build_app

DEFAULT_OUTPUT_DIR = ROOT / "outputs" / "local_user_app"
README_NAME = "内测说明.md"
FORBIDDEN_PACKAGE_NAMES = {
    ".env",
    "uploaded_datasets",
    "local_settings",
    "tool_audit",
}


@dataclass(frozen=True)
class DmgArtifacts:
    """DMG 构建产物路径。"""

    app_path: Path
    dmg_path: Path
    checksum_path: Path
    readme_path: Path

    def to_dict(self) -> dict[str, str]:
        return {
            "app_path": str(self.app_path),
            "dmg_path": str(self.dmg_path),
            "checksum_path": str(self.checksum_path),
            "readme_path": str(self.readme_path),
        }


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    artifacts = build_internal_dmg(
        repo_root=_resolve_path(args.repo_root),
        output_dir=_resolve_path(args.output_dir),
        app_name=args.app_name,
        version=args.version,
        build_app_bundle=not args.skip_app_build,
        install_local_runtime=args.install_local_runtime,
        keep_staging=args.keep_staging,
    )
    print(f"已生成 DMG：{artifacts.dmg_path}")
    print(f"SHA256：{artifacts.checksum_path}")
    print(f"说明：{artifacts.readme_path}")
    return 0


def build_internal_dmg(
    *,
    repo_root: Path = ROOT,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    app_name: str = DEFAULT_APP_NAME,
    version: str = APP_VERSION,
    build_app_bundle: bool = True,
    install_local_runtime: bool = False,
    keep_staging: bool = False,
) -> DmgArtifacts:
    """构建内测 DMG，并写出 sidecar README 和 SHA256。"""

    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    app_path = output_dir / f"{app_name}.app"
    if build_app_bundle:
        app_path = build_app(
            repo_root=repo_root.resolve(),
            output_dir=output_dir,
            app_name=app_name,
            build_frontend=True,
            include_runtime=True,
            install_app_runtime=install_local_runtime,
        )
    if not app_path.is_dir():
        raise SystemExit(f"缺少 app bundle：{app_path}")

    package_stem = f"{app_name}-{version}-macos-internal"
    dmg_path = output_dir / f"{package_stem}.dmg"
    checksum_path = output_dir / f"{package_stem}.sha256"
    readme_path = output_dir / f"{package_stem}.README.md"
    staging_dir = output_dir / f".{package_stem}-staging"

    if staging_dir.exists():
        shutil.rmtree(staging_dir)
    staging_dir.mkdir(parents=True)
    try:
        staged_app = staging_dir / app_path.name
        shutil.copytree(app_path, staged_app, symlinks=True)
        _write_readme(staging_dir / README_NAME, app_name=app_name, version=version)
        _add_applications_link(staging_dir)
        _validate_staging(staging_dir)
        _create_dmg(staging_dir, dmg_path, app_name=app_name, version=version)
    finally:
        if not keep_staging and staging_dir.exists():
            shutil.rmtree(staging_dir)

    digest = _sha256_file(dmg_path)
    checksum_path.write_text(f"{digest}  {dmg_path.name}\n", encoding="utf-8")
    _write_readme(
        readme_path,
        app_name=app_name,
        version=version,
        dmg_name=dmg_path.name,
        sha256=digest,
    )
    return DmgArtifacts(
        app_path=app_path,
        dmg_path=dmg_path,
        checksum_path=checksum_path,
        readme_path=readme_path,
    )


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="生成 macOS 内测 DMG 包。")
    parser.add_argument("--repo-root", default=str(ROOT))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--app-name", default=DEFAULT_APP_NAME)
    parser.add_argument("--version", default=APP_VERSION)
    parser.add_argument(
        "--skip-app-build",
        action="store_true",
        help="跳过 .app 重建，直接使用 output-dir 中现有 app。",
    )
    parser.add_argument(
        "--install-local-runtime",
        action="store_true",
        help="同时刷新当前机器 Library runtime；默认只生成可分发 app bundle。",
    )
    parser.add_argument(
        "--keep-staging",
        action="store_true",
        help="保留 DMG staging 目录，供人工排查。",
    )
    return parser.parse_args(argv)


def _resolve_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else (ROOT / path).resolve()


def _write_readme(
    path: Path,
    *,
    app_name: str,
    version: str,
    dmg_name: str | None = None,
    sha256: str | None = None,
) -> None:
    checksum_block = ""
    if dmg_name and sha256:
        checksum_block = f"""
## 校验

下载后可运行：

```bash
shasum -a 256 "{dmg_name}"
```

期望 SHA256：

```text
{sha256}  {dmg_name}
```
"""
    path.write_text(
        f"""# {app_name} {version} 内测包

这是未签名、未 notarize 的 macOS 内测包，只建议发给受信任测试用户。

## 打开方式

1. 双击 `.dmg`，把 `{app_name}.app` 拖到“应用程序”或桌面。
2. 第一次打开如果被 macOS 拦截，请在 Finder 里右键 app，选择“打开”。
3. 页面打开后进入“设置”，选择 LLM provider，填入自己的 API key。
4. 上传 Excel/CSV 后，系统会在本机生成规则和结构化存储；关闭后再次打开仍会保留。

## 本机数据

- 上传表格、规则、warehouse、日志和 LLM 设置默认保存在 `~/Library/Application Support/SZU Local Workbench/`。
- DMG 不包含仓库 `.env`、真实上传表格、旧 mock/demo 数据或临时 `outputs` 产物。
- API key 存在本机设置文件中，页面和 API 不回显明文。
- 启用 LLM 后，用户 query 和必要 schema/候选上下文会发送给所选 provider；系统不把整张表默认上传给 provider。

## 内测数据

- 内测包不附带招生大表、用户上传表格或任何真实业务数据。
- 内测用户需要自己上传 Excel/CSV；上传后的原表、字段能力、规则、warehouse、LLM 设置和日志都只保存在当前 Mac。
- 反馈问题时不要直接回传原始 Excel/CSV、`.duckdb`、`local_settings/llm.json` 或完整 `uploaded_datasets/` 目录。
- 建议只反馈页面截图、行列数、字段名摘要、错误码、`EvidencePack` 摘要和不含敏感值的最小样例表。

## 内测限制

- 当前包要求 macOS 12+，并且首次启动时本机需要可用的 Python 3.11+ 来初始化运行时。
- 首次启动需要安装 Python 依赖，可能需要几分钟和网络访问。
- 这不是正式签名包；正式发版前仍需要签名、notarize 和更完整的自动升级策略。

## 清理

退出 app 后，可删除 `~/Library/Application Support/SZU Local Workbench/` 来清空本机上传数据、规则、日志和 LLM 设置。
{checksum_block}""",
        encoding="utf-8",
    )


def _add_applications_link(staging_dir: Path) -> None:
    link = staging_dir / "Applications"
    try:
        os.symlink("/Applications", link)
    except FileExistsError:
        return
    except OSError:
        return


def _validate_staging(staging_dir: Path) -> None:
    for path in staging_dir.rglob("*"):
        relative_parts = set(path.relative_to(staging_dir).parts)
        forbidden = relative_parts & FORBIDDEN_PACKAGE_NAMES
        if forbidden:
            raise SystemExit(
                f"DMG staging 包含禁止发布的路径：{path.relative_to(staging_dir)}"
            )


def _create_dmg(
    staging_dir: Path,
    dmg_path: Path,
    *,
    app_name: str,
    version: str,
) -> None:
    command = [
        "/usr/bin/hdiutil",
        "create",
        "-volname",
        f"{app_name} {version} 内测",
        "-srcfolder",
        str(staging_dir),
        "-ov",
        "-format",
        "UDZO",
        str(dmg_path),
    ]
    try:
        subprocess.run(command, check=True)
    except FileNotFoundError as exc:
        raise SystemExit("找不到 hdiutil；只能在 macOS 上生成 DMG。") from exc
    except subprocess.CalledProcessError as exc:
        raise SystemExit("hdiutil 生成 DMG 失败。") from exc


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
