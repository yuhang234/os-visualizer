# os-visualizer · 操作系统可视化教学平台

用可视化方式讲解操作系统核心原理的全栈教学平台：**页面置换算法**（FIFO / LRU / OPT / CLOCK）、**银行家算法**（安全性检查 + 资源请求判定）、**多线程同步互斥**（有界缓冲区生产者-消费者 / mutex + empty + full），配套**多模型 AI 助教**（12 家厂商模板 + 自定义中转 + 本地部署 + 4 款内置离线小模型）与**用户登录**，全站支持**深色 / 浅色双主题**（跟随系统 / 深色 / 浅色三态）。

设计契约（实现依据，逐字节入库）：[`docs/design-spec.md`](docs/design-spec.md)、[`docs/mockup.html`](docs/mockup.html)。

<p align="center">
  <img alt="双主题" src="https://img.shields.io/badge/theme-dark%20%2F%20light-2f81f7">
  <img alt="Python" src="https://img.shields.io/badge/Python-3.11%2B-3776ab">
  <img alt="React" src="https://img.shields.io/badge/React-19-61dafb">
  <img alt="FastAPI" src="https://img.shields.io/badge/FastAPI-SSE%20streaming-009688">
  <img alt="tests" src="https://img.shields.io/badge/tests-335%20passed-2ea043">
</p>

## 目录

- [1. 环境要求](#1-环境要求)
- [2. 安装](#2-安装)
- [3. 启动](#3-启动)
- [4. 测试](#4-测试)
- [5. 环境变量](#5-环境变量)
- [6. 目录结构](#6-目录结构)
- [7. 主要功能与页面](#7-主要功能与页面)
- [8. 无密钥也能端到端体验 AI 对话](#8-无密钥也能端到端体验-ai-对话)
- [9. 安全说明](#9-安全说明)
- [10. 备注](#10-备注)

---

## 1. 环境要求

| 组件 | 版本 | 说明 |
| :--- | :--- | :--- |
| Python | 3.11+（开发验证环境 3.13.5） | 后端 FastAPI + SQLite |
| Node.js | 20+（开发验证环境 22.x） | 前端 React 19 + Vite |

无需显卡：内置小模型走 CPU 推理；无任何厂商 API Key 时 AI 对话仍可用内置 mock 引擎端到端跑通。

## 2. 安装

```bash
# 后端
cd backend
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt -r requirements-dev.txt

# 前端
cd ../frontend
npm install
```

## 3. 启动

### 3.1 一键（两个终端）

```bash
# 终端 1：后端 API（默认 http://127.0.0.1:8000）
cd backend
.venv/bin/python -m uvicorn app.main:app --port 8000

# 终端 2：前端开发服务器（默认 http://127.0.0.1:5173，已把 /api 反向代理到 :8000）
cd frontend
npm run dev
```

浏览器打开 <http://127.0.0.1:5173> 即可（`/` 会自动跳转到页面置换算法页；未登录即游客模式，算法全部开放）。

### 3.2 生产构建

```bash
cd frontend
npm run build          # tsc -b + vite build，产物在 frontend/dist
npm run preview        # 本地预览构建产物（:4173）
```

构建产物为纯静态文件，部署时由 Nginx / Caddy 托管 `dist/` 并把 `/api` 前缀转发到后端 `:8000` 即可（同前缀、无跨域）。后端 CORS 白名单可用 `OSVIS_CORS_ORIGINS` 覆盖。

## 4. 测试

```bash
cd backend
.venv/bin/python -m pytest tests/ -q          # 335 passed
```

覆盖：FIFO / LRU / OPT / CLOCK 四种置换算法与 Belady 异常、银行家安全性判定与安全序列/请求回滚、生产者-消费者不变量（容量不越界、不覆盖未消费项、mutex 唯一占用、empty/full 守恒）、四类算法的轨迹可回放性、全部 HTTP 接口契约（含 400/401/404 边界）、SSE 帧协议、密钥掩码与不落明文、模型五态生命周期与断点续传（含 SHA-256 校验失败路径）。

```bash
cd frontend
npm run typecheck      # tsc 类型检查
npm run build          # 构建（含类型检查）
```

## 5. 环境变量

后端读取 `backend/.env`（可选，全部有安全默认值），完整样例见 [`backend/.env.example`](backend/.env.example)：

| 变量 | 默认值 | 说明 |
| :--- | :--- | :--- |
| `OSVIS_JWT_SECRET` | 自动生成并持久化 | 留空时在 `backend/data/jwt_secret.key` 生成随机密钥（权限 600） |
| `OSVIS_DATA_DIR` / `OSVIS_MODELS_DIR` | `backend/data`、`backend/models_cache` | SQLite 库与内置模型缓存位置 |
| `OSVIS_GUEST_DAILY_CHAT_LIMIT` | `5` | 游客使用**服务端默认 Key** 时的每日对话上限（自配 Key / 本地部署 / 内置 mock 不受限） |
| `OSVIS_DEFAULT_PROVIDER` / `OSVIS_DEFAULT_MODEL` / `OSVIS_SERVER_API_KEY` / `OSVIS_SERVER_BASE_URL` | 空 | 服务端兜底云端模型（仅 OpenAI 兼容端点）；Key 只存在于后端进程，永不返回前端 |
| `OSVIS_LOCAL_PROBE_TIMEOUT` | `2.5` | 本地推理服务在线探测超时（秒） |
| `OSVIS_DOWNLOAD_ALLOW_HOSTS` | HuggingFace / ModelScope / ollama.com / GitHub | 内置模型下载主机白名单（防 SSRF） |
| `OSVIS_CORS_ORIGINS` | `localhost:5173` 等 | 允许的前端来源 |
| `OSVIS_MOCK_CHUNK_DELAY` | `0.018` | 内置 mock 引擎每个流式分片的间隔（秒），仅用于本地演示节奏 |

## 6. 目录结构

```
backend/
  app/
    api/v1/           algorithms.py（轨迹生成） ai_proxy.py（SSE 对话 + 厂商配置）
                      auth.py（注册/登录/鉴权） engine_manager.py（探测 + 模型下载管理）
    engine/           page_replacement.py  banker.py  threads_simulator.py  trace.py
    providers/        catalog.py（12 厂商模板 + mock） client.py（OpenAI 兼容流式客户端）
                      local_runtimes.py（Ollama / LM Studio / llama.cpp / vLLM 探测）
    local_models/     catalog.py（4 款模型字段 + SHA-256） downloader.py（五态 + 断点续传）
                      runtime.py（本地装载 / 内存态）
    core/             config.py（环境变量 + 路径脱敏） crypto.py（Fernet） db.py（SQLite）
                      security.py（PBKDF2 + JWT）
    schemas/          algorithms.py  auth.py  engine.py  common.py
  tests/              test_page_replacement.py  test_banker.py  test_threads.py  test_api.py
  data/               运行期生成：SQLite 库、JWT 密钥、加密主密钥（已 gitignore）
  models_cache/       运行期生成：内置小模型文件（已 gitignore）
frontend/
  src/
    views/            三个算法页 + AiChatView + EngineSettingsView + SettingsView + LoginView
    components/       shell（侧边栏/顶栏/播放条） common（主题、密码框、Markdown、模态）
                      visualizer（页框、时钟表盘、缓冲区、日志台、指标环）
    hooks/            useTheme  usePlayback  useAiStream  useAudioSynth  useAuth
    services/         后端 API 客户端（含 SSE 流式读取）
    styles/           tokens.css（深/浅两套同名令牌）app.css（手写样式，全部引用令牌）
docs/                 design-spec.md（设计契约）mockup.html（交互原型）
```

## 7. 主要功能与页面

| 路由 | 页面 | 说明 |
| :--- | :--- | :--- |
| `/algorithms/page-replacement` | 页面置换算法 | 4 算法 × 参考串 × 页框数；页框二维网格、命中/缺页/淘汰高亮、CLOCK 指针表盘、实时指标环、控制台日志 |
| `/algorithms/banker` | 银行家算法 | 进程/资源数可调、Max/Allocation/Need 三矩阵可编辑、安全性检查推导表、资源请求判定与回滚、云端案例保存（登录后） |
| `/algorithms/threads` | 多线程并发 | 有界缓冲区环形槽位、生产者/消费者时间轴、mutex/empty/full 原语状态、不变量校验、吞吐与上下文切换指标 |
| `/ai-assistant` | AI 助教对话 | 引擎切换、SSE 流式 Markdown + KaTeX、可挂载当前算法状态快照作为上下文 |
| `/settings/engine` | 模型引擎设置 | 12 家厂商模板 + 自定义中转 + 本地部署探测/一键连接 + 内置小模型五态下载管理 |
| `/settings` | 系统通用设置 | 三态主题、音效与音量、本地缓存清理、账号、后端服务状态 |
| `/login` | 登录 / 注册 | 账号密码（PBKDF2 加盐哈希）、游客一键体验 |

三个算法页共用**吸底播放条**：跳至起始 / 单步后退 / 自动播放 / 单步前进 / 跳至最终 + 进度条 + 倍速（0.5x / 1x / 2x / 4x / 8x）。轨迹由后端一次性算完下发，前端在内存中回放，回退是 O(1) 取快照。

## 8. 无密钥也能端到端体验 AI 对话

- **内置 mock 引擎**（引擎标识 `builtin-mock`）：无需任何密钥/网络，直接流式返回针对当前算法状态的讲解，用于课堂演示与自检；
- **本地部署**：装了 Ollama / LM Studio / llama.cpp / vLLM 后，在「模型引擎设置 → 本地部署接入」一键探测并连接，对话完全不限额；
- **自定义中转 / 自配厂商 Key**：填入 base URL 与 Key（界面只显示掩码，落库加密），「测试连通性」通过即可作为对话引擎；
- **内置离线小模型**：4 款真实小模型一键下载（后端流式管道 + SHA-256 校验 + 断点续传），下载完成后可装载为对话引擎（需要本机具备 Ollama 或 llama.cpp 运行时）。

## 9. 安全说明

- 所有对上游模型的请求都由后端代理转发，浏览器只与本站 `/api` 通信；**API Key 只存在于后端**，接口一律返回掩码值（`sk-…abcd`）。
- 厂商 Key 以 Fernet 对称加密落库（主密钥 `backend/data/secret.key`，权限 600，已 gitignore）；用户口令用 PBKDF2-SHA256 加盐哈希（20 万次迭代）存储。
- 服务器绝对路径（数据目录、模型缓存目录）不下发到浏览器，接口只返回相对标签（如 `backend/models_cache`）。
- 内置模型下载受主机白名单与目标目录白名单约束，只写入 `models_cache` 且文件名取自固定清单。

## 10. 备注

- 数据库、密钥与模型缓存位于 `backend/data/`、`backend/models_cache/`，均已被 `.gitignore` 忽略；首次启动自动创建，无需手工初始化。
- 内置 4 款模型的字节数与设计文档中的「约 xx MB」估算存在差异（文档为估算值），实际以下载清单中的精确 `bytesTotal` / SHA-256 为准，详见交付报告。

## 11. 许可证

本项目以 MIT 许可证发布，详见 [`LICENSE`](LICENSE)。

## 12. 参与贡献

提交前请确保：后端 `pytest` 全绿、前端 `npm run typecheck` 与 `npm run build` 通过。设计层面的改动请先更新 [`docs/design-spec.md`](docs/design-spec.md)，实现与契约同行。
