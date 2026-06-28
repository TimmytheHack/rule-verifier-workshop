# 本地用户 Web

这是独立于现有研发前端的本地用户 Web。页面不读取旧 mock/demo 数据，不展示内部领域数据源，只消费本机后端返回的数据源和能力摘要。

## 本地运行

需要 Node.js `^20.19.0 || >=22.12.0`。

普通用户入口建议从仓库根目录启动：

```bash
make serve-user
```

然后打开 `http://127.0.0.1:8001`。该模式会把当前前端构建产物交给 FastAPI 同端口托管。
如果未设置自定义 `AUTH_TOKENS_JSON`，仓库根目录的 `make serve-user` 会为本机页面设置 HttpOnly 开发 cookie，使页面可以访问本机 API。

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
