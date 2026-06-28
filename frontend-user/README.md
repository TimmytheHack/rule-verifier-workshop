# 本地用户 Web

这是独立于现有研发前端的本地用户 Web。页面不读取旧 mock/demo 数据，不展示内部领域数据源，只消费本机后端返回的数据源和能力摘要。

一键导入会把上传表格在本机生成可查询数据源。通用表格只自动批准后端判定安全的枚举、数值和标识字段操作；自由文本、高基数名称、备注和潜在 PII 字段不会自动进入 SQL 筛选。查询页字段、预检摘要和结果卡片使用后端 profile 的源列名展示，不暴露 `field_XX` 这类内部字段 id。

设置页支持 OpenAI-compatible provider 模板：DeepSeek、通义千问 / DashScope、Kimi / Moonshot、智谱 GLM、百度千帆和腾讯混元。密钥只保存在本机，页面不会回显明文。

## 本地运行

需要 Node.js `^20.19.0 || >=22.12.0`。

普通用户入口建议从仓库根目录启动：

```bash
make serve-user
```

macOS 也可以双击仓库根目录的 `start_local_user_web.command`，或运行 `make macos-app` 生成 `outputs/local_user_app/本地表格工作台.app` 后双击 app。然后打开 `http://127.0.0.1:8001`。该模式会把当前前端构建产物交给 FastAPI 同端口托管。
`.app` 包内放上传数据流所需的源码快照、tool contract 和前端构建产物；构建时会把可运行的 Python runtime 安装到 `~/Library/Application Support/SZU Local Workbench/runtime/workbench/`。它不包含内置 admissions/housing/products domain pack 或质量/pilot 诊断工具；上传数据、LLM 设置、生成规则和日志写入 `~/Library/Application Support/SZU Local Workbench/`。如果未设置自定义 `AUTH_TOKENS_JSON`，仓库根目录的 `make serve-user` 会为本机页面设置 HttpOnly 开发 cookie，使页面可以访问本机 API；`.app` 每次启动会生成一次性本机 token。
该 `.app` 是同机本地启动包；如果要换机器使用，需要在目标机器从项目重新运行 `make macos-app`。

前端开发时使用：

```bash
npm install
npm run dev
```

开发服务器默认代理到 `http://127.0.0.1:8001`，可用 `VITE_API_PROXY_TARGET` 覆盖。

## 验证

```bash
npm run test:unit
npm run build
```
