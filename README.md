# Stock AI System

最小可上线股票 AI 辅助分析系统。

## 本地运行后端

```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload
```

后端默认地址：

```text
http://127.0.0.1:8000
```

## 本地运行前端

直接打开 `frontend/index.html`，或用任意静态服务器托管 `frontend/`。

如果 Render 后端地址不是默认本地地址，修改 `frontend/app.js`：

```js
const API_BASE = "https://你的-render-后端地址.onrender.com";
```

也可以在浏览器控制台执行：

```js
localStorage.setItem("STOCK_API_BASE", "https://你的-render-后端地址.onrender.com")
```

## 部署

1. 后端部署到 Render，根目录选择 `backend/`，或使用 `backend/render.yaml`。
2. 拿到 Render 地址。
3. 替换 `frontend/app.js` 的 `API_BASE`。
4. 前端部署到 Vercel，根目录选择 `frontend/`。

## 风险声明

本系统仅供学习和辅助分析，不构成投资建议，不自动交易。
