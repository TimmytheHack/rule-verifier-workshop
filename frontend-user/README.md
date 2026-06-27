# 本地用户 Web

这是独立于现有研发前端的本地用户 Web。页面不读取旧 mock/demo 数据，不展示内部 admissions 数据源，只消费本机后端返回的数据源和能力摘要。

## 本地运行

需要 Node.js `^20.19.0 || >=22.12.0`。

```bash
npm install
npm run dev
```

后端默认代理到 `http://127.0.0.1:8001`，可用 `VITE_API_PROXY_TARGET` 覆盖。

## 验证

```bash
npm run test:unit
npm run build
```
