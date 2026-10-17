# os-visualizer 操作系统核心原理可视化教学平台 —— 前端 UI 设计稿与技术架构规范

> **文档版本**：v1.3.0-definitive  
> **文档定位**：全栈开发实现契约（Implementation Specification & Contract）  
> **面向对象**：下一阶段全栈开发实现者（OpenCode）、系统架构师、船长审批  
> **更新摘要**：在保持 v1.0 全量工程细节与 v1.1 多模型引擎接口（12 厂商模板、本地部署、4 款离线小模型）的基础上，完整融合 **v1.2 双主题（深色 Dark / 浅色 Light）设计令牌与切换规范**。本规范恢复并补齐所有算法布局线框图、控件树、通信协议约定、状态机、音效映射表、目录树、全部 HTTP 接口 JSON Schema 及共享数据契约，确保实现者可直接依照本文档进行开发。

---

## 目录

1. [技术选型与架构分工决策](#1-技术选型与架构分工决策)
2. [页面清单与全局导航体系](#2-页面清单与全局导航体系)
3. [双主题设计令牌体系：深色与浅色规范 (Dual Theme Tokens)](#3-双主题设计令牌体系深色与浅色规范-dual-theme-tokens)
4. [核心交互引擎：步进 / 回退 / 自动播放规范](#4-核心交互引擎步进--回退--自动播放规范)
5. [页面置换算法可视化页面设计（含线框图、控件树与深浅配色）](#5-页面置换算法可视化页面设计含线框图控件树与深浅配色)
6. [银行家算法资源分配与死锁避免页面设计（含线框图、控件树与深浅配色）](#6-银行家算法资源分配与死锁避免页面设计含线框图控件树与深浅配色)
7. [多线程同步互斥（生产者-消费者）页面设计（含线框图、控件树与深浅配色）](#7-多线程同步互斥生产者-消费者页面设计含线框图控件树与深浅配色)
8. [多模型 AI 教学助理与对话交互系统设计](#8-多模型-ai-教学助理与对话交互系统设计)
9. [模型引擎设置页：多厂商模板、自定义中转与本地部署规范](#9-模型引擎设置页多厂商模板自定义中转与本地部署规范)
10. [内置小模型离线下载与生命周期管理机制](#10-内置小模型离线下载与生命周期管理机制)
11. [用户登录与鉴权体系设计](#11-用户登录与鉴权体系设计)
12. [Web Audio 程序化音效反馈系统](#12-web-audio-程序化音效反馈系统)
13. [落地映射与工程实现契约 (Implementation Contract)](#13-落地映射与工程实现契约-implementation-contract)
14. [端到端目标执行链 (End-to-End Execution Flow)](#14-端到端目标执行链-end-to-end-execution-flow)
15. [项目分期实施计划与风险评估](#15-项目分期实施计划与风险评估)

---

## 1. 技术选型与架构分工决策

### 1.1 前端方案选型

- **主推方案**：`React 19 + TypeScript + Vite + Tailwind CSS (v4) + Lucide Icons`
- **选型理由**：
  1. **状态快照与时间旅行机制**：操作系统算法教学的核心是“单步前进、逐步回退、状态重现”。React 的纯函数式组件配合不可变快照（Immutable Snapshots）是实现时间旅行（Time-Travel Playback）最自然的技术底座。每次回退直接以 $O(1)$ 复杂度切换当前快照索引，视图自动做最小 DOM Diff 更新。
  2. **高性能表格与流式渲染**：银行家算法涉及 4 组动态矩阵（Max, Allocation, Need, Available），多线程涉及多条并发时间轴与高频日志追加。React 19 的 Concurrent 模式与轻量虚拟 DOM 能保障在自动播放高倍速（8x，125ms/步）下保持 60fps 丝滑渲染。
  3. **双主题无缝动态切换**：利用 CSS 自定义属性（CSS Variables）挂载于根节点，React 切换主题仅需变更根节点的 `class="light-theme"`，零组件级重新渲染开销。
  4. **生态完备性**：Markdown 渲染（`react-markdown` + `rehype-highlight` + `remark-math`）、Katex 公式排版以及流式文本追加（AI 对话）拥有业界最成熟的开源组件支持。
- **备选方案**：`Vue 3 + TypeScript + Vite + Pinia + UnoCSS`
- **取舍条件**：如果后续实现团队核心成员对 Vue 3 响应式系统更熟练，可平替为 Vue 3。但鉴于 React 社区在算法可视化课件与 AI 对话流处理上的成熟案例更多，推荐锁定 React 19。

---

### 1.2 后端方案选型与算法步进计算归属（核心决策）

#### 核心问题回答：算法步进数据到底在哪一侧计算？

- **明确结论**：**算法核心逻辑由后端统一计算，一次性生成完整的“步骤快照执行轨迹（Execution Trace）”下发给前端；前端作为纯内存驱动的“时间旅行回放引擎（Playback Engine）”执行步进、回退、调速与高亮**。

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                             后端 (FastAPI)                                  │
│  [接收输入参数] ───> [运行 OS 算法模型] ───> [一次性生成全量 StepSnapshot[] 轨迹] ─┐
└─────────────────────────────────────────────────────────────────────────────┘
                                                                              │ REST
                                                                              │ JSON
┌─────────────────────────────────────────────────────────────────────────────▼─┐
│                             前端 (React 引擎)                                 │
│  [内存装载 Trace] ◄── [本地游标 currentIndex 控制] ◄── [用户操作 / 计时器 Tick]│
│         │                                                                     │
│         ├─ Step Forward:  currentIndex++  (O(1) 切换快照, 零网络延迟)         │
│         ├─ Step Backward: currentIndex--  (O(1) 恢复快照, 零状态丢失)         │
│         ├─ Auto Play:     setInterval()   (支持 0.5x~8x 毫秒级极速推进)       │
│         └─ UI 驱动:       页框 / 矩阵 / 线程条 / 日志 / 音效 同步重绘         │
└───────────────────────────────────────────────────────────────────────────────┘
```

#### 决策理由：
1. **彻底消除步进与回退的网络延迟**：如果采用“单步步进调一次后端 API”的 RPC 模式，自动播放必然受到网络抖动与往返 RTT（Round-Trip Time）限制，且后端必须在 Redis 或内存中维持每个用户的会话状态机，不仅实现极其脆弱，而且“后退”时后端必须维护撤销栈。而“后端一次性算完，前端内存快照回放”使单步前进、后退、跳至开头/末尾均完全在浏览器本地内存完成，响应时间为 0ms，彻底杜绝回放卡顿。
2. **前后端职责解耦，算法逻辑严谨**：操作系统核心算法（如银行家安全性检测、改进型 CLOCK、离散事件线程调度模拟）使用 Python 编写，能够充分利用 Python 在数据结构、矩阵计算、类型标注上的严谨性，易于编写完备的自动化单元测试。
3. **数据量开销极其轻量**：在操作系统教学场景下，页面置换参考串长度一般在 10~50 之间，银行家矩阵通常为 5 进程 3 资源，多线程模拟通常在 100~300 个事件步以内。全量步骤的 JSON 体积通常仅为 15KB ~ 80KB，一次 HTTP POST 请求即可在 50ms 内完成传输，完全不存在传输带宽瓶颈。
4. **备选降级与离线保障**：在无后端连接或断网演示时，前端可内置一份 TypeScript 版本的轻量算法 fallback 模块直接在浏览器本地生成 Trace。

- **后端主推技术选型**：`Python 3.11+ / FastAPI + Pydantic v2 + Uvicorn`
- **后端理由**：FastAPI 提供天生异步支持、原生 OpenAPI 文档生成，且 Pydantic v2 具备与前端 TypeScript 严格对齐的数据结构验证能力。同时 Python 处理数据流与调用各类大模型 SDK / Ollama 本地 API 具有最佳兼容性。

---

### 1.3 通信协议规范

1. **普通业务与算法轨迹生成**：`RESTful API + JSON`（`POST /api/v1/algorithms/.../simulate`）。
   - 算法计算一次性返回完整步骤序列，响应头 `Content-Type: application/json`。
2. **AI 对话流式推送**：`Server-Sent Events (SSE)`（`POST /api/v1/ai/chat/stream`）。
   - 响应头 `Content-Type: text/event-stream; charset=utf-8`，`Cache-Control: no-cache`，`Connection: keep-alive`。
   - 客户端单向接收流式 token 分块，传输终止标志为 `data: [DONE]\n\n`。
   - 为什么不用 WebSocket：AI 对话是典型的“客户端一次提交上下文，服务端持续单向推回 token”的场景，SSE 基于标准 HTTP，穿透反向代理（Nginx/Caddy）与云端负载均衡更加原生稳定，无握手协商与心跳保活冗余代码。

---

## 2. 页面清单与全局导航体系

### 2.1 页面清单 (Page Inventory)

| 页面 ID | 路由路径 (`Route`) | 页面中文名称 | 核心功能职责 | 访问控制 |
| :--- | :--- | :--- | :--- | :--- |
| `P-LOGIN` | `/login` | 用户登录 / 注册 | 账号密码登录、新用户注册、游客模式一键体验入口 | 全员开放 |
| `P-PAGE-REP` | `/algorithms/page-replacement` | 页面置换算法 | FIFO/LRU/OPT/CLOCK 模拟、页框可视化、缺页率统计、回放控制器 | 全员开放（未登录可体验） |
| `P-BANKER` | `/algorithms/banker` | 银行家算法 | 4 矩阵编辑与导入、安全性检测、资源请求（Request）动态判定、死锁高亮 | 全员开放（未登录可体验） |
| `P-THREADS` | `/algorithms/threads` | 多线程并发演示 | 生产者-消费者模型、环形缓冲队列、信号量与互斥锁监控、线程状态追踪 | 全员开放（未登录可体验） |
| `P-AI-CHAT` | `/ai-assistant` | AI 教学助教对话 | 多厂商模型切换、OS 原理解析、算法答疑、流式生成、Markdown/公式渲染 | 游客受限，登录/自定义 Key 无限 |
| `P-ENGINE-SETTINGS` | `/settings/engine` | 模型引擎设置 | 12 大模型厂商模板配置、自定义中转 API、本地推理探测 (Ollama 等)、内置小模型下载管理 | 全员开放 |
| `P-SETTINGS` | `/settings` | 系统通用偏好设置 | 主题模式三态切换（系统/深色/浅色）、音量与音效开关、本地缓存清理 | 全员开放 |

---

### 2.2 导航结构与用户状态差异

```
┌──────────────────────────────────────────────────────────────────────────┐
│                             全局 App Shell 结构                           │
├───────────────┬──────────────────────────────────────────────────────────┤
│ 左侧侧边栏     │ 顶部状态栏：[当前页面标题] ─── [☀️/🌙主题切换] ── [音量] ── [登录/用户]│
│ (可收起 250px) ├──────────────────────────────────────────────────────────┤
│               │                                                          │
│ 品牌与 Logo    │                                                          │
│ ───────────── │                       主工作区                           │
│ 算法仿真实验   │                  (Main Content Area)                     │
│  ├─ 页面置换   │                                                          │
│  ├─ 银行家算法 │                                                          │
│  └─ 多线程演示 │                                                          │
│ ───────────── │                                                          │
│ AI 助教与引擎  │                                                          │
│  ├─ AI 助教对话│                                                          │
│  ├─ 模型引擎设置│                                                          │
│  └─ 系统通用设置│                                                          │
│ ───────────── ├──────────────────────────────────────────────────────────┤
│ 用户身份卡片   │ 底部全局时间旅行播放控制条 (Global Playback Control Dock)        │
│ [头像/游客状态]│ [⏮ 上一步] [▶ 播放/暂停] [⏭ 下一步] [进度条] [速度: 1.0x] [🔊 音效] │
│               │ (在算法页面时常驻吸底，在 AI/设置页自动折叠隐藏)            │
└───────────────┴──────────────────────────────────────────────────────────┘
```

#### 登录态差异策略：
1. **未登录状态（游客模式 Guest Mode）**：
   - 侧边栏底部显示 `游客体验中` 徽标与 `点击登录` 按钮。
   - 算法页面全部开放，允许修改参数与体验步进回放。
   - AI 对话若使用云端服务端默认 Key，游客每日限 5 次对话；若用户在“模型引擎设置”中配置了自定义 API Key 或连接了本地 Ollama，则**完全不限制对话次数**。
   - 自定义算法矩阵与配置仅保存在浏览器的临时内存或 `sessionStorage`，刷新可能重置。
2. **已登录状态**：
   - 侧边栏底部显示用户头像、用户名（如 `Student_Linux`）与 `登出` 菜单。
   - 允许将配置好的矩阵、参考串、自定义 API 接入配置与内置小模型偏好安全持久化至云端 SQLite 数据库并在设备间同步。

---

## 3. 双主题设计令牌体系：深色与浅色规范 (Dual Theme Tokens)

系统原生支持**深色模式（Dark Theme）**与**浅色模式（Light Theme）**，所有设计令牌严格保持一一对应、命名完全一致，可直接编译为标准 CSS 变量。

### 3.1 核心颜色令牌一一对应表 (Color Tokens Mapping)

| 令牌名称 (Token Name) | 深色模式值 (Dark Theme) | 浅色模式值 (Light Theme) | 语义与视觉职责 | 浅色对比度与可读性保障设计 |
| :--- | :--- | :--- | :--- | :--- |
| `--color-bg-canvas` | `#0b0f19` (暗蓝黑) | `#f8fafc` (Slate 50 柔和暖白灰) | 全局最底层视口底色 | 避免纯白（#fff）眩光刺眼，降低视疲劳 |
| `--color-bg-surface` | `#111827` (Gray 900) | `#ffffff` (纯白) | 侧边栏主体、顶栏、主工作区卡片底色 | 与 Canvas 形成清晰的明度层级分界 |
| `--color-bg-panel` | `#1e293b` (Slate 800) | `#ffffff` (纯白带微灰边框) | 算法操作台、表格容器、浮层背景 | 在浅色下依靠细边框建立卡片独立感 |
| `--color-bg-subtle` | `#243047` | `#f1f5f9` (Slate 100) | 次级面板底色、按钮与选项的 Hover 悬浮态 | 提供明确的鼠标悬浮触觉反馈 |
| `--color-bg-active` | `#334155` | `#e2e8f0` (Slate 200) | 导航选中态、激活卡片底色 | 产生明确的按压与选定反馈 |
| `--color-border-subtle` | `#1f293d` | `#f1f5f9` (极浅微灰) | 次级分割线、表头与单元格弱线 | 仅区分结构，不产生视觉杂音 |
| `--color-border-default` | `#374151` | `#e2e8f0` (Slate 200) | 标准卡片外框、表格网格框、输入框外线 | 满足 WCAG 3:1 UI 组件轮廓清晰度 |
| `--color-border-strong` | `#4b5563` | `#cbd5e1` (Slate 300) | 聚焦态边框、强调区分线 | 获得视觉焦点 |
| `--color-text-primary` | `#f9fafb` (Gray 50) | `#0f172a` (Slate 900 墨黑) | 页面大标题、核心数值、关键表头 | 对比度达 **14.2:1**，超 WCAG AAA 级 |
| `--color-text-secondary` | `#9ca3af` (Gray 400) | `#475569` (Slate 600 灰蓝) | 正文描述、辅助说明、字段标签 | 对比度达 **7.1:1**，满足正文高清晰度 |
| `--color-text-muted` | `#6b7280` (Gray 500) | `#64748b` (Slate 500) | 时间戳、占位符文字、已完成置灰 | 对比度达 **4.8:1**，满足次级信息标准 |
| `--color-accent-primary` | `#38bdf8` (Sky 400 天蓝) | `#0284c7` (Sky 600 湛蓝) | 品牌主色、主操作按钮、发光焦点 | **关键调整**：浅色加深至 Sky 600，保证文字对比度 > 4.5:1 |
| `--color-accent-hover` | `#0ea5e9` (Sky 500) | `#0369a1` (Sky 700) | 主按钮悬浮态 | 提供深邃反馈 |
| `--color-accent-subtle` | `rgba(56, 189, 248, 0.12)` | `rgba(2, 132, 199, 0.08)` | 选中行浅色高亮遮罩 | 浅色下降低不透明度，防止遮挡文字 |
| `--color-success` | `#10b981` (Emerald 500) | `#059669` (Emerald 600) | 命中 (Hit)、安全状态、运行中徽标 | 浅色下加深饱和度，防止白色底上发虚 |
| `--color-success-bg` | `rgba(16, 185, 129, 0.15)` | `rgba(5, 150, 105, 0.10)` | 命中页框插槽底色、安全行底色 | 形成淡绿舒适感 |
| `--color-warning` | `#f59e0b` (Amber 500) | `#d97706` (Amber 600) | 警告、阻塞、等待信号量徽标 | 避免在浅色背景上变暗黄 |
| `--color-warning-bg` | `rgba(245, 158, 11, 0.15)` | `rgba(217, 119, 6, 0.10)` | 阻塞线程卡片底色 | 淡橙底色 |
| `--color-danger` | `#ef4444` (Red 500) | `#dc2626` (Red 600) | 缺页 (Miss)、死锁、异常警告 | 警示性强烈醒目 |
| `--color-danger-bg` | `rgba(239, 68, 68, 0.15)` | `rgba(220, 38, 38, 0.10)` | 缺页调入插槽底色 | 淡红底色 |
| `--color-info` | `#6366f1` (Indigo 500) | `#4f46e5` (Indigo 600) | 互斥锁、系统通知 | 稳定优雅 |
| `--shadow-panel` | `0 10px 25px -5px rgba(0,0,0,0.6)` | `0 4px 6px -1px rgba(0,0,0,0.06)` | 卡片外浮层投影 | 浅色下采用细柔漫反射投影，干净现代 |

---

### 3.2 字体族与排版规范代码块 (Typography & CSS Tokens)

```css
:root {
  /* 中西文标准界面字体栈 (包含完整的中文跨平台回退链) */
  --font-sans: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", "Noto Sans SC", sans-serif;
  
  /* 代码块、矩阵数值、日志面板等宽字体栈 */
  --font-mono: "JetBrains Mono", "Cascadia Code", "Fira Code", Consolas, "Courier New", monospace;

  /* 字号阶梯 */
  --font-size-xs: 0.75rem;    /* 12px: 标签、状态微章、时间戳 */
  --font-size-sm: 0.875rem;   /* 14px: 正文、按钮、表格数据、控制台日志 */
  --font-size-base: 1rem;     /* 16px: 输入框文本、一级选项 */
  --font-size-lg: 1.125rem;   /* 18px: 卡片小标题、状态大字 */
  --font-size-xl: 1.25rem;    /* 20px: 模块区块标题 */
  --font-size-2xl: 1.5rem;    /* 24px: 核心统计数值 */
  --font-size-3xl: 1.875rem;  /* 30px: 顶级页面大标题 */

  /* 行高阶梯 */
  --line-height-tight: 1.25;
  --line-height-normal: 1.5;
  --line-height-relaxed: 1.625;

  /* 圆角规范 */
  --radius-sm: 4px;
  --radius-md: 8px;
  --radius-lg: 12px;
  --radius-full: 9999px;
}
```

---

### 3.3 几何与排版不变性约束规范 (Invariance Rules)

为了确保用户在频繁切换主题时，**界面绝对不发生任何抖动、重排（Reflow）或位移**，以下规范声明为**绝对不变项**：

1. **几何尺寸与网格不变**：
   - 侧边栏宽度严格锁定为 `250px`。
   - 所有卡片内边距（Padding）严格为 `20px`（大卡片）或 `16px`（小组件）。
   - 圆角规范严格一致：`--radius-sm: 4px`, `--radius-md: 8px`, `--radius-lg: 12px`, `--radius-full: 9999px`。
2. **字号与行高阶梯不变**：
   - 字号与行高完全锁定：`--font-size-xs` (12px), `sm` (14px), `base` (16px), `lg` (18px), `xl` (20px), `2xl` (24px), `3xl` (30px)。
   - 行高比例：紧凑 `1.25`、标准 `1.5`、舒缓 `1.625`。
3. **字体族回退链不变**：
   - 全局界面字体族：`--font-sans`。
   - 等宽字体族：`--font-mono`。

---

### 3.4 主题切换控件位置、状态与持久化机制

1. **入口布局规划**：
   - **顶部 Header 右侧常驻快捷开关**：放置一个紧凑的日/月图标按钮（☀️/🌙），点击时立即在深色与浅色之间无缝切换，伴随微弱的 Web Audio 咔哒触觉声。
   - **系统设置页（`P-SETTINGS`）完整单选组**：提供专业级的三态单选控制器：
     - `( ) 跟随系统 (System)`：根据用户操作系统偏好（`prefers-color-scheme`）自适应切换。
     - `( ) 浅色模式 (Light)`：始终强制启用日光高清晰浅色。
     - `(●) 深色模式 (Dark)`：始终强制启用极夜护眼深色（默认值）。
2. **零白屏闪烁持久化机制 (FOUC Prevention)**：
   - 用户的显式选择写入 `localStorage.setItem('os_theme', 'light' | 'dark' | 'system')`。
   - 在前端 HTML 页面的 `<head>` 首行注入一段行内自执行脚本（Inline Script）：
     ```javascript
     (function() {
       const saved = localStorage.getItem('os_theme') || 'dark';
       const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
       const theme = saved === 'system' ? (prefersDark ? 'dark' : 'light') : saved;
       if (theme === 'light') {
         document.documentElement.classList.add('light-theme');
       } else {
         document.documentElement.classList.remove('light-theme');
       }
     })();
     ```
   - 浏览器在解析渲染 DOM 树之前即完成样式挂载，彻底杜绝刷新页面时出现瞬间白光或黑光爆闪。

---

## 4. 核心交互引擎：步进 / 回退 / 自动播放规范

### 4.1 步骤数据结构设计 (JSON Schema)

一次完整的算法运行产出一个包含所有有序步骤的 `ExecutionTrace` 结构：

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "ExecutionTrace",
  "type": "object",
  "required": ["algorithmId", "totalSteps", "initialState", "steps"],
  "properties": {
    "algorithmId": { "type": "string", "enum": ["fifo", "lru", "opt", "clock", "banker-safety", "banker-request", "threads-pc"] },
    "algorithmName": { "type": "string" },
    "createdAt": { "type": "string", "format": "date-time" },
    "totalSteps": { "type": "integer", "minimum": 1 },
    "initialState": { "type": "object" },
    "steps": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["stepIndex", "title", "description", "snapshot", "logs", "eventTone"],
        "properties": {
          "stepIndex": { "type": "integer", "minimum": 0 },
          "title": { "type": "string" },
          "description": { "type": "string" },
          "snapshot": { "type": "object" },
          "highlights": { "type": "array", "items": { "type": "string" } },
          "logs": {
            "type": "array",
            "items": {
              "type": "object",
              "properties": {
                "timestamp": { "type": "string" },
                "level": { "type": "string", "enum": ["INFO", "SUCCESS", "WARN", "DANGER"] },
                "message": { "type": "string" }
              }
            }
          },
          "eventTone": {
            "type": "string",
            "enum": ["NONE", "STEP", "HIT", "MISS", "SUCCESS", "DANGER", "BLOCK", "WAKEUP"]
          }
        }
      }
    }
  }
}
```

### 4.2 为什么必须采用状态快照（Snapshot）而非重放（Replay）？

- **结论**：**采用绝对状态快照（Full State Snapshots by Index）**。
- **原因**：
  1. 重放模式（Replay）在回退时必须从第 0 步重新向前依次计算至 $N-1$ 步，计算开销为 $O(N)$，且如果涉及随机事件或异步定时器极易发生状态漂移。
  2. 状态快照模式下，回退操作仅为 `currentIndex--`，取 `steps[currentIndex]` 渲染，时间复杂度严格为 $O(1)$，绝对幂等，无论向前进 1 步还是倒退 10 步，界面状态永远 100% 准确对应，不产生任何副作用。

### 4.3 播放器控制器状态机与速度规范

```
        ┌────────────────────────────────────────────────────────┐
        │                                                        │
        ▼                                                        │
    [ IDLE ] ──(点击开始/生成)──> [ LOADING ] ──(计算完成)──> [ READY/PAUSED ]
                                                                 │      ▲
                                                  (点击播放)     │      │ (点击暂停/单步)
                                                                 ▼      │
                                                            [ PLAYING ] ─┘
                                                                 │
                                                       (达到最后一步)
                                                                 ▼
                                                            [ FINISHED ]
```

- **速度档位**：
  - `0.5x`：2000 ms / 步（适合精细教学研讨）
  - `1.0x`：1000 ms / 步（默认标准档位）
  - `2.0x`：500 ms / 步
  - `4.0x`：250 ms / 步
  - `8.0x`：125 ms / 步（极速排查与对比实验）
- **自动播放驱动**：使用 `requestAnimationFrame` + Delta Time 计时累加器，避免 `setInterval` 丢帧。
- **时间轴与日志联动**：横向步骤滑块可直接拖动直达任意步；终端控制台使用 `scrollIntoView({ behavior: 'smooth' })` 平滑置底滚动。

---

## 5. 页面置换算法可视化页面设计（含线框图、控件树与深浅配色）

### 5.1 算法范围与取舍
全面支持操作系统的 **4 大主流置换算法**：FIFO、LRU、OPT、CLOCK。

### 5.2 页面布局线框图 (Wireframe)

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│ [页面置换算法可视化]                    [预设案例: 经典Belady异常 ▼] [🎲 随机生成] │
├──────────────────────────────────────────────────────────────────────────────────┤
│ 参数配置栏:                                                                       │
│  算法选择: (●) FIFO  ( ) LRU  ( ) OPT  ( ) CLOCK                                 │
│  页面参考串: [ 7, 0, 1, 2, 0, 3, 0, 4, 2, 3, 0, 3, 2, 1, 2, 0, 1, 7, 0, 1     ]   │
│  物理页框数: [ 3 ] (范围 2~7)       [ ⚡ 重新生成执行轨迹 ] [ 🔄 重置数据 ]        │
├─────────────────────────────────────────────────┬────────────────────────────────┤
│ 主可视化大屏 (页框二维网格矩阵)                  │ 实时统计与指标看板             │
│                                                 │                                │
│ 步骤: 6 / 20  | 当前访问: 页面 [ 3 ]             │ ┌──────────────┬─────────────┐ │
│ 状态: [ ❌ 发生缺页 (Page Fault) ]              │ │ 访问总数: 6  │ 缺页次数: 5 │ │
│                                                 │ ├──────────────┼─────────────┤ │
│  时序参考串:                                    │ │ 命中次数: 1  │ 缺页率:83.3%│ │
│  [ 7 ] [ 0 ] [ 1 ] [ 2 ] [ 0 ] ➔[ 3 ] [ 0 ] ... │ └──────────────┴─────────────┘ │
│   已   已   已   已   已   当前  待访            │ ┌────────────────────────────┐ │
│                                                 │ │ 缺页率动态进度环            │ │
│  物理页框状态:                                  │ │    ╭──────╮  83.3%         │ │
│  ┌──────────────┐                               │ │   │  83%   │ 缺页风险较高  │ │
│  │ 页框 0: [ 2 ]│ (驻留时间: 2 步)              │ │    ╰──────╯                │ │
│  ├──────────────┤                               │ └────────────────────────────┘ │
│  │ 页框 1: [ 3 ]│ ◄── [新载入! 替换了页面 0]    ├────────────────────────────────┤
│  ├──────────────┤                               │ 置换原理解释 (动态卡片)        │
│  │ 页框 2: [ 1 ]│ (驻留时间: 4 步)              │ FIFO 策略：                    │
│  └──────────────┘                               │ 页框1中的页面0最先进入内存，   │
│  (CLOCK 算法时此处展示环形表盘与指针 Arrow)     │ 驻留时间达 4 步，故触发淘汰。   │
├─────────────────────────────────────────────────┴────────────────────────────────┤
│ 控制台运行日志 (Console Execution Log)                                           │
│ [10:24:01] INFO  初始化完成: 页框数=3, 算法=FIFO                                 │
│ [10:24:02] MISS  访问页面 7: 内存空闲，分配页框 0                                │
│ [10:24:04] HIT   访问页面 0: 命中页框 1，无需置换                                │
│ [10:24:06] MISS  访问页面 3: 内存已满，根据 FIFO 淘汰页框 1 中的旧页面 0        │
└──────────────────────────────────────────────────────────────────────────────────┘
```

### 5.3 控件树与属性规范 (Component Hierarchy)

- `PageReplacementView` (Flex Col, W: 100%, H: 100%)
  - `HeaderSection` (Flex Row, H: 48px, Align: Center)
    - `TitleText` (Type: Heading, Size: 20px, Color: TextPrimary)
    - `PresetDropdown` (Type: Select, Options: ["经典Belady例题", "教材标准串", "高频局部性访问"])
    - `RandomButton` (Type: Button, Icon: Dices, Text: "随机生成参考串")
  - `ConfigCard` (Type: Panel, Padding: 16px, Bg: Surface, Radius: 12px)
    - `AlgorithmRadioGroup` (Type: RadioGroup, Layout: Horizontal, Options: [FIFO, LRU, OPT, CLOCK])
    - `ReferenceStringInput` (Type: TextInput, Default: "7,0,1,2,0,3,0,4,2,3,0,3,2,1,2,0,1,7,0,1")
    - `FrameCountSelector` (Type: NumberStepper, Min: 2, Max: 7, Default: 3)
    - `ExecuteButton` (Type: PrimaryButton, Text: "生成轨迹并播放", Bg: Sky500)
  - `VisualizerBody` (Grid 12 Cols, Gap: 16px, Flex: 1)
    - `LeftCanvas` (Grid Col: 8, Type: Card)
      - `AccessSequenceBanner` (Type: ScrollableTagList, HighlightCurrentIndex: 5)
      - `FramesDisplayArea` (Type: StackedSlots / ClockCircle, MinHeight: 280px)
        - `FrameSlot` (Array x FrameCount, Props: frameIndex, pageNumber, status: [HIT|MISS|EMPTY], isEvicted)
      - `ClockPointerWidget` (Condition: algorithm === 'CLOCK', SVG Needle Animation)
    - `RightMetricsPanel` (Grid Col: 4, Type: Card)
      - `StatsSummaryGrid` (Grid 2x2, Props: totalAccess, hits, misses, missRate)
      - `GaugeProgressRing` (Type: SVG Donut, Percent: missRate, Color: Danger/Success)
      - `PrincipleCard` (Type: InfoBox, DynamicText: StepDescription)
  - `LogConsolePanel` (Type: TerminalWindow, Height: 160px, Bg: TerminalBg, Font: JetBrains Mono)

### 5.4 浅色与深色模式下的可视化元素配色表

| 可视化组件 | 深色模式配色 (Dark) | 浅色模式配色 (Light) | 教学心理与视觉效果 |
| :--- | :--- | :--- | :--- |
| **参考串当前项** | 边框 `--color-accent-primary` (#38bdf8)，背景光晕 Sky-400 | 边框 `#0284c7` (Sky-600)，背景浅天蓝 (`rgba(2, 132, 199, 0.12)`) | 聚焦醒目，不刺眼 |
| **参考串已访项** | 不透明度 `0.6`，边框变弱暗灰 | 不透明度 `0.5`，背景 `#f1f5f9`，边框 `#cbd5e1` | 明确区分已逝时间与未来时间 |
| **命中 (HIT) 页框** | 边框 `#10b981`，渐变底色绿色光晕 | 边框 `#059669`，浅翡翠底色 (`#ecfdf5`) | 清新舒适的确认感 |
| **缺页 (MISS) 页框** | 边框 `#ef4444`，渐变底色红色光晕 | 边框 `#dc2626`，浅玫瑰底色 (`#fef2f2`) | 醒目的置换提示 |
| **缺页率环形进度条** | 轨道底色 `#374151`，数值高光天蓝 | 轨道底色 `#e2e8f0`，数值深墨蓝 (`#0f172a`) | 仪表盘质感统一 |
| **运行控制台终端** | 极夜底色 `#050811`，荧光绿/荧光红字符 | 雅致 Slate 浅色底 `#f8fafc`，高对比红绿字 | 专业代码可读性 |

---

## 6. 银行家算法资源分配与死锁避免页面设计（含线框图、控件树与深浅配色）

### 6.1 核心算法机制与交互要点
包含两组核心判定：
1. **安全性检查（Safety Algorithm）**：寻找安全序列 $\langle P_1, P_3, P_4, P_0, P_2 \rangle$。
2. **资源请求分配与试探（Resource-Request Algorithm）**：
   - 步骤一：$\text{Request}_i \le \text{Need}_i$
   - 步骤二：$\text{Request}_i \le \text{Available}$
   - 步骤三：试探性分配并调用安全性检查。若安全则批准，不安全则回滚并提示等待。

### 6.2 页面布局线框图 (Wireframe)

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│ [银行家算法 (Banker's Algorithm)]             [预设案例: 教材标准5进程3资源 ▼]   │
├──────────────────────────────────────────────────────────────────────────────────┤
│ 资源配置与矩阵输入区 (可折叠面板):                                                │
│  进程总数: [ 5 ]  资源种类: [ 3 ] (A, B, C)  初始Available: [ A:3, B:3, C:2 ]    │
│  ┌───────────────────────┬───────────────────────┬───────────────────────┐      │
│  │ Max 矩阵 (最大需求)   │ Allocation (已分配)   │ Need (需求 = Max-Alloc)│      │
│  │    A  B  C            │    A  B  C            │    A  B  C            │      │
│  │ P0 [7][5][3]          │ P0 [0][1][0]          │ P0 [7][4][3]          │      │
│  │ P1 [3][2][2]          │ P1 [2][0][0]          │ P1 [1][2][2]          │      │
│  │ P2 [9][0][2]          │ P2 [3][0][2]          │ P2 [6][0][0]          │      │
│  │ P3 [2][2][2]          │ P3 [2][1][1]          │ P3 [0][1][1]          │      │
│  │ P4 [4][3][3]          │ P4 [0][0][2]          │ P4 [4][3][1]          │      │
│  └───────────────────────┴───────────────────────┴───────────────────────┘      │
│  [ 📋 文本/JSON一键导入 ]  [ 📤 导出配置 ]  [ 🔍 运行安全性检查 ]                 │
├──────────────────────────────────────────────────────────────────────────────────┤
│ 安全性检查推导动态大屏 (Work & Finish 动态演进表):                                │
│                                                                                  │
│ 当前检查进程: P1  |  判定条件: Need[P1] (1,2,2) <= Work (3,3,2)  ➔ [ ✅ 满足 ]    │
│                                                                                  │
│ ┌─────┬──────────────┬──────────────┬──────────────┬──────────────┬────────────┐ │
│ │ 进程│ Work (可用)  │ Need (需求)  │ Allocation   │ Work+Alloc   │ Finish状态 │ │
│ ├─────┼──────────────┼──────────────┼──────────────┼──────────────┼────────────┤ │
│ │ P1  │ 3  3  2      │ 1  2  2      │ 2  0  0      │ 5  3  2      │ [✅ TRUE]  │ │
│ │ P3  │ 5  3  2      │ 0  1  1      │ 2  1  1      │ 7  4  3      │ [✅ TRUE]  │ │
│ │ P4  │ 7  4  3      │ 4  3  1      │ 0  0  2      │ 7  4  5      │ [等待检查] │ │
│ └─────┴──────────────┴──────────────┴──────────────┴──────────────┴────────────┘ │
│ 当前找到的安全序列: [ P1 ] ──> [ P3 ] ──> [ P4 ] ──> [ P0 ] ──> [ P2 ]            │
├─────────────────────────────────────────────────┬────────────────────────────────┤
│ 动态资源请求交互模态区 (Request 模拟测试)        │ 最终判定结果看板               │
│ 发起请求进程: [ P1 ▼ ]   请求量: A:[1] B:[0] C:[2] │ 状态: 安全 (SAFE) 允许立即分配 │
│ [ 🚀 提交分配申请并判定 ]                       │ 判定: 满足条件一二，试探分配安全 │
└─────────────────────────────────────────────────┴────────────────────────────────┘
```

### 6.3 浅色模式与深色模式下的矩阵表格配色

- **表头 (Table Header)**：
  - 深色：背景 `#111827`，文字 `#9ca3af`。
  - 浅色：背景 `#f1f5f9`，文字 `#475569`，下边框 `#cbd5e1`。
- **活动行 (Active Checking Process)**：
  - 深色：背景 `rgba(56, 189, 248, 0.12)`，字体高亮天蓝。
  - 浅色：背景 `#e0f2fe`（浅天蓝），边框高亮 `#0284c7`，文字 `#0369a1`。
- **已释放资源行 (Finish = True)**：
  - 深色：背景 `rgba(16, 185, 129, 0.15)`。
  - 浅色：背景 `#ecfdf5`（柔和淡绿），文字绿色加粗 `#065f46`。

---

## 7. 多线程同步互斥（生产者-消费者）页面设计（含线框图、控件树与深浅配色）

### 7.1 问题选型与理由
- **明确选定**：**经典有界缓冲区生产者-消费者模型（Bounded-Buffer Problem）**。
- **选型理由**：融合了互斥锁（`mutex=1`）、空位信号量（`empty=N`）与产品信号量（`full=0`）三大经典原语，格状环形队列视觉反馈最生动，便于量化观察阻塞与唤醒。

### 7.2 页面布局线框图 (Wireframe)

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│ [多线程同步互斥演示 —— 生产者/消费者模型]               [预设: 2生产 2消费 缓冲=5 ▼] │
├──────────────────────────────────────────────────────────────────────────────────┤
│ 控制栏: 缓冲区容量: [ 5 ]  生产速率: [ 1.5s/个 ]  消费速率: [ 2.0s/个 ]  [▶ 开始模拟] │
├─────────────────────────────────────────────────┬────────────────────────────────┤
│ 共享缓冲区 (Bounded Buffer) 实时状态             │ 同步原语与锁状态 (Primitives)  │
│                                                 │                                │
│ 容量: 5 | 当前产品数: 3 / 5 | 状态: 正常流转    │ 互斥锁 Mutex:                  │
│                                                 │  [ 🟢 自由空闲 (Value: 1) ]    │
│  [ 槽位 0 ]   [ 槽位 1 ]   [ 槽位 2 ]   [ 槽位 3 ]   [ 槽位 4 ]                  │
│ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐   空位信号量 Empty: │
│ │  ITEM   │ │  ITEM   │ │  ITEM   │ │  (空)   │ │  (空)   │    [ 2 / 5 剩余空槽 ]│
│ │  #101   │ │  #102   │ │  #103   │ │         │ │         │                      │
│ └─────────┘ └─────────┘ └─────────┘ └─────────┘ └─────────┘   产品信号量 Full:  │
│      ▲                                                        [ 3 / 5 已产存货 ]│
│   (已占)       (已占)       (已占)    (下一写入位)                               │
├─────────────────────────────────────────────────┴────────────────────────────────┤
│ 线程工作台与运行状态监控 (Thread Lifecycle & Callstack)                          │
│                                                                                  │
│ 生产者线程池 (Producers):                                                        │
│  P1 [ 🟢 RUNNING 正在生产 ]  进度: [██████████░░░░] 70%  执行代码: P(empty);      │
│  P2 [ 🟡 BLOCKED 阻塞等待 ]  原因: 信号量 empty=0 (缓冲区已满) 等待消费者唤醒    │
│                                                                                  │
│ 消费者线程池 (Consumers):                                                        │
│  C1 [ 🔵 SLEEP 休眠就绪 ]    进度: [░░░░░░░░░░░░░░] 0%   准备申请互斥锁          │
│  C2 [ 🟢 RUNNING 正在取出 ]  进度: [██████████████] 100% 执行代码: V(empty);      │
├──────────────────────────────────────────────────────────────────────────────────┤
│ 伪代码执行高亮联动面板 (Pseudo-code Context)                                      │
│                                                                                  │
│ 1: item = produce_item();             1: P(full);   // 检查是否有产品            │
│ 2: P(empty); // 等待空槽位            2: P(mutex);  // 抢占互斥锁                │
│ 3: P(mutex); // 抢占互斥锁            3: item = remove_item(); // 取出产品       │
│ 4: insert_item(item); // 写入缓冲区 ➔ 4: V(mutex);  // 释放互斥锁                │
│ 5: V(mutex); // 释放互斥锁            5: V(empty);  // 增加空槽位信号            │
│ 6: V(full);  // 唤醒消费者            6: consume_item(item);                     │
└──────────────────────────────────────────────────────────────────────────────────┘
```

### 7.3 浅色模式与深色模式下的线程与队列配色

- **缓冲区空槽位**：深色为深灰底 `#1e293b` 虚线框；浅色为纯白底 `#ffffff` 配 `#94a3b8` 虚线框。
- **缓冲区装满槽位**：深色为 `#38bdf8` 边框带发光底；浅色为 `#0284c7` 边框带浅天蓝 `#e0f2fe` 底色，产品编号加粗深蓝 `#0369a1`。
- **线程进度条**：深色轨道 `#111827`，渐变填充 `#0ea5e9` ➔ `#10b981`；浅色轨道 `#e2e8f0`，渐变填充 `#0284c7` ➔ `#059669`。

---

## 8. 多模型 AI 教学助理与对话交互系统设计

### 8.1 架构拓扑模型

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                 前端 UI (AI 对话页 & 引擎设置页) [支持深色/浅色动态切换]      │
│  [模型切换器] ─── [预设提示词] ─── [附带算法快照] ─── [Markdown/公式流式渲染] │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │ SSE 流式请求 (统一标准接口)
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                     后端统一大模型代理适配器 (FastAPI Proxy)                 │
│                 POST /api/v1/ai/chat/stream                                 │
└──────┬───────────────────────┬───────────────────────────────┬──────────────┘
       │                       │                               │
       ▼ (公有云厂商)          ▼ (中转网关 / 自定义)           ▼ (本地离线私有化)
┌──────────────┐       ┌──────────────────────┐        ┌──────────────────────┐
│ 11 大模型厂商 │       │ OneAPI / NewAPI /    │        │ Ollama / LM Studio / │
│ 官方原生或兼容│       │ 自定义 OpenAI 兼容   │        │ 本地内置小模型 (GGUF)│
│ (OpenAI/豆包/│       │ 逆向网关             │        │ (Qwen2.5/DeepSeek-R1)│
│ DeepSeek等)  │       └──────────────────────┘        └──────────────────────┘
└──────────────┘
```

### 8.2 对话界面交互要点
- **打字机闪烁光标**：流式推送末尾渲染 `typing-cursor`，支持 Markdown 语法树动态重绘。
- **停止生成与重试**：点击停止立即向后端发出 `abort` 信号，断开上游 SSE 连接。
- **算法快照附带**：用户勾选后，前端自动将当前页面置换或银行家的矩阵状态注入 Prompt 上下文。

---

## 9. 模型引擎设置页：多厂商模板、自定义中转与本地部署规范

### 9.1 主流模型厂商模板清单核实表 (12 大厂商)

| 序号 | 厂商 / 平台名称 | 官方真实 `base_url` | 官方标准模型标识 (`model`) | 鉴权请求头字段名 | 请求体是否 OpenAI 兼容 | SSE 响应体文本路径 |
| :---: | :--- | :--- | :--- | :--- | :---: | :--- |
| 1 | **OpenAI** | `https://api.openai.com/v1` | `gpt-4o`, `gpt-4o-mini` | `Authorization: Bearer <KEY>` | ✅ 是 | `choices[0].delta.content` |
| 2 | **Anthropic Claude** | `https://api.anthropic.com/v1` | `claude-3-5-sonnet-20241022` | `x-api-key: <KEY>`<br>`anthropic-version: 2023-06-01` | ❌ 否 (Messages 格式) | `delta.text` |
| 3 | **Google Gemini** | `https://generativelanguage.googleapis.com/v1beta/openai/` | `gemini-1.5-flash`, `gemini-2.0-flash` | `Authorization: Bearer <KEY>` | ✅ 是 | `choices[0].delta.content` |
| 4 | **DeepSeek** | `https://api.deepseek.com/v1` | `deepseek-chat`, `deepseek-reasoner` | `Authorization: Bearer <KEY>` | ✅ 是 | `choices[0].delta.content` |
| 5 | **阿里云百炼 (DashScope)** | `https://dashscope.aliyuncs.com/compatible-mode/v1` | `qwen-plus`, `qwen-turbo` | `Authorization: Bearer <KEY>` | ✅ 是 | `choices[0].delta.content` |
| 6 | **火山方舟 (豆包 Doubao)** | `https://ark.cn-beijing.volces.com/api/v3` | 控制台推理接入点 ID (`ep-...`) | `Authorization: Bearer <KEY>` | ✅ 是 | `choices[0].delta.content` |
| 7 | **硅基流动 (SiliconFlow)** | `https://api.siliconflow.cn/v1` | `deepseek-ai/DeepSeek-V3` | `Authorization: Bearer <KEY>` | ✅ 是 | `choices[0].delta.content` |
| 8 | **Groq** | `https://api.groq.com/openai/v1` | `llama-3.3-70b-versatile` | `Authorization: Bearer <KEY>` | ✅ 是 | `choices[0].delta.content` |
| 9 | **OpenRouter** | `https://openrouter.ai/api/v1` | `meta-llama/llama-3.3-70b-instruct` | `Authorization: Bearer <KEY>` | ✅ 是 | `choices[0].delta.content` |
| 10 | **Moonshot Kimi** | `https://api.moonshot.cn/v1` | `moonshot-v1-8k` | `Authorization: Bearer <KEY>` | ✅ 是 | `choices[0].delta.content` |
| 11 | **智谱 GLM** | `https://open.bigmodel.cn/api/paas/v4` | `glm-4-flash` | `Authorization: Bearer <KEY>` | ✅ 是 | `choices[0].delta.content` |
| 12 | **自定义 / 中转 API (通用)** | 用户自由输入 | 用户自由输入 | `Authorization: Bearer <KEY>` + 额外头 | ✅ 是 | `choices[0].delta.content` |

### 9.2 通用中转 / 自定义 API 接入控制台设计
支持用户配置：`base_url`、API Key、模型名、自定义 Header JSON。配备「测试连接」按钮，前端向后端发 ping 探测，返回往返延迟（ms）或清晰的错误码与失败诊断卡片（401 密钥失效、404 模型不存在、网络超时等）。

### 9.3 本地部署方案选型与一键探测
- **Ollama (首选)**：默认端口 `11434`，OpenAI 端点 `http://localhost:11434/v1`，探测接口 `GET http://localhost:11434/api/tags`。支持一键探测并自动解析本地拉取的所有模型列表填入下拉框。
- **LM Studio**（端口 1234）、**llama.cpp server**（端口 8080）、**vLLM**（端口 8000）均支持标准化一键接入。

---

## 10. 内置小模型离线下载与生命周期管理机制

### 10.1 内置离线小模型选型清单 (4 款真实小模型)

| 模型标识符 (`Model ID`) | 参数量 | 下载体积 (GGUF Q4) | 官方来源仓库 | 许可证 | 语言与能力特征 | CPU 推理速度预期 | 推荐加载后端 |
| :--- | :---: | :---: | :--- | :--- | :--- | :---: | :--- |
| **Qwen2.5-0.5B-Instruct** | 0.5B | **~390 MB** | HuggingFace / ModelScope / Ollama Library | Apache 2.0 | 中英双语、操作系统基础概念与语法遵循极快 | **35 ~ 60 tokens/s** | Ollama / llama.cpp |
| **Qwen2.5-1.5B-Instruct** | 1.5B | **~980 MB** | HuggingFace / ModelScope / Ollama Library | Apache 2.0 | 中英双语、逻辑推理扎实，具备 OS 核心代码分析能力 | **18 ~ 30 tokens/s** | Ollama / llama.cpp |
| **DeepSeek-R1-Distill-Qwen-1.5B** | 1.5B | **~1.1 GB** | HuggingFace / Ollama Library | MIT | 具备思考链 (CoT) 推导，能分步解析页面置换与死锁 | **14 ~ 22 tokens/s** | Ollama |
| **Llama-3.2-1B-Instruct** | 1.2B | **~800 MB** | HuggingFace / Ollama Library | Llama 3.2 Community | 纯英文/轻量指令微调，适合国际化或精简问答 | **25 ~ 40 tokens/s** | Ollama / llama.cpp |

### 10.2 下载架构与状态机生命周期设计
- **谁来下载？**：由自研 FastAPI 后端服务通过流式管道下载到服务器磁盘目录（`~/.ollama/models` 或 `backend/models_cache/`），浏览器前端通过轮询或 SSE 接收实时进度。
- **五态模型**：
  1. `NOT_DOWNLOADED`（未下载）：提供体积预估与一键下载按钮。
  2. `DOWNLOADING`（下载中）：条形进度条、下载速率、已下/总量、暂停与取消，支持断点续传。
  3. `READY`（已就绪）：MD5 校验通过，提供启用与删除按钮。
  4. `LOADING`（装载中）：模型正装载入内存 (mmap)。
  5. `ERROR`（失败态）：显示红色警告与具体原因，提供重试。

### 10.3 安全与配置持久化策略
- API Key 零明文代码入库，前端密码框带掩码与眼睛切换图标。
- 配置持久化于后端 SQLite 表 `model_providers`，重启服务后所有已配置厂商秘钥与已下载模型索引完整保留。

---

## 11. 用户登录与鉴权体系设计

### 11.1 架构决策与选型
- **明确结论**：采用轻量级全栈真实账号体系（FastAPI + SQLite + JWT），前端采用 `localStorage` 持久化 Token，同时提供一键免登录的“游客模式（Guest Mode）”。
- **决策理由**：真实账号保证矩阵案例与 AI 提问历史在多终端间安全漫游同步；游客模式确保课堂演示与初次体验门槛为零。

### 11.2 鉴权流程时序图

```
[前端浏览器]                                      [后端 FastAPI 鉴权中间件]
     │                                                      │
     ├────── 1. POST /api/v1/auth/login (账号密码) ────────>│ (验证密码 Hash)
     │<───── 2. 返回 { access_token, user_info } ──────────┤
     │                                                      │
     │  (存储 token 到 localStorage)                         │
     │                                                      │
     ├────── 3. 携带 Authorization: Bearer <token> ────────>│ (验证 JWT 签名)
     │<───── 4. 200 OK / 401 Unauthorized ──────────────────┤
```

### 11.3 登录/注册界面线框图

```
┌──────────────────────────────────────────────────────────┐
│                   OS Visualizer 操作系统教学              │
│                理解核心原理，掌控计算机内核底层             │
├──────────────────────────────────────────────────────────┤
│        [ 登录 (Sign In) ]     [ 注册 (Register) ]        │
│  用户名 / 学号: [ student_os                          ]  │
│  登录密码:      [ ••••••••••••                     👁 ]  │
│  [!] 用户名长度不少于 3 个字符，密码不少于 6 位          │
│  [ 🚀 立即登录 ]                                         │
│  ────────────── 或者是课堂演示 / 临时体验？ ────────────  │
│  [ ⚡ 以游客身份快速体验 (无需账号) ]                     │
└──────────────────────────────────────────────────────────┘
```

---

## 12. Web Audio 程序化音效反馈系统

### 12.1 为什么选择 Web Audio API 程序化合成？
- **零外部网络依赖与 0 字节体积**：完全不产生静态资源 HTTP 请求，绝不出现 404 音频丢失。
- **零触发延迟**：直接在底层音频线程合成正弦波/三角波，延迟 $<5\text{ms}$，在高倍速算法自动播放时保持精准同步。

### 12.2 音效事件映射表与声音特征

| 音效标识 | 触发业务事件 | 合成波形 (`type`) | 频率序列 (`Hz`) | 衰减时长 (`Duration`) | 听觉心理感受 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `TONE_HIT` | 页面置换命中 | 正弦波 (`sine`) | 587.33 (D5) ➔ 880 (A5) | 120ms，快速渐弱 | 清脆、明快的“叮咚”确认感 |
| `TONE_MISS` | 页面置换缺页 / 淘汰 | 三角波 (`triangle`) | 220 (A3) ➔ 110 (A2) | 200ms，带低通滤波 | 沉闷短促的提示感，不刺耳 |
| `TONE_STEP` | 单步步进推进 | 白噪声 / 高频正弦 | 1200 (短脉冲) | 30ms，微弱咔哒声 | 类似机械按键的触觉反馈 |
| `TONE_SAFE` | 银行家安全检查通过 | 正弦波双音和弦 | 523.25 (C5) + 659.25 (E5) | 350ms，舒缓展开 | 成功、安全解脱的和谐音 |
| `TONE_DEADLOCK` | 银行家死锁 / 申请被拒 | 锯齿波 (`sawtooth`) | 180 (F3) ➔ 150 (D3) 震颤 | 400ms，蜂鸣颤音 | 警示、注意死锁风险 |
| `TONE_SWITCH` | 线程阻塞 / 唤醒 | 正弦滑音 | 400 ➔ 600 (Wake) / 600 ➔ 400 (Block) | 80ms 快速滑音 | 物理位置或状态流转感 |

---

## 13. 落地映射与工程实现契约 (Implementation Contract)

### 13.1 前后端完整工程目录结构树

```
os-visualizer/
├── frontend/                       # 前端工程 (React 19 + TypeScript + Vite)
│   ├── public/
│   │   └── favicon.svg
│   ├── src/
│   │   ├── components/             # 公共可复用 UI 组件
│   │   │   ├── shell/              # 页面壳布局 (AppShell, Sidebar, TopHeader, PlaybackDock)
│   │   │   ├── common/             # 通用小组件 (Button, Modal, Badge, ThemeToggle)
│   │   │   ├── visualizer/         # 算法可视化专用组件 (MatrixTable, FrameSlots, ThreadBar, StepLogView)
│   │   │   └── engine/             # 模型引擎组件 (ProviderCard, ModelDownloader, PingTester)
│   │   ├── views/                  # 各大路由视图页面
│   │   │   ├── LoginView.tsx       # 用户登录/注册/游客页
│   │   │   ├── PageRepView.tsx     # 页面置换算法主页
│   │   │   ├── BankerView.tsx      # 银行家算法主页
│   │   │   ├── ThreadsView.tsx     # 多线程并发主页
│   │   │   ├── AiChatView.tsx      # 豆包 AI 对话助教主页
│   │   │   ├── EngineSettingsView.tsx # 模型引擎与本地部署配置主页
│   │   │   └── SettingsView.tsx    # 系统通用偏好设置主页
│   │   ├── hooks/                  # usePlayback, useAudioSynth, useAiStream, useAuth, useTheme
│   │   ├── services/               # client.ts, algorithmApi.ts, authApi.ts, engineApi.ts
│   │   ├── types/                  # algorithm.ts, ai_engine.ts, auth.ts
│   │   ├── styles/tokens.css       # 深浅双主题 CSS 变量与设计令牌
│   │   ├── App.tsx                 # 根路由表
│   │   └── main.tsx                # 入口挂载
│   ├── package.json
│   ├── tsconfig.json
│   └── vite.config.ts
│
└── backend/                        # 后端工程 (FastAPI + Pydantic v2 + SQLite)
    ├── app/
    │   ├── api/v1/
    │   │   ├── auth.py             # 登录注册端点
    │   │   ├── algorithms.py       # 页面置换/银行家/多线程计算
    │   │   ├── ai_proxy.py         # 多厂商大模型 SSE 代理转发
    │   │   └── engine_manager.py   # 模型探测、小模型下载管理、Ping 接口
    │   ├── core/config.py          # 环境变量与配置
    │   ├── engine/                 # 操作系统离线纯算法 (Python)
    │   │   ├── page_replacement.py # FIFO, LRU, OPT, CLOCK 轨迹生成器
    │   │   ├── banker.py           # 银行家安全性与 Request 判定器
    │   │   └── threads_simulator.py# 生产者消费者离散事件推进器
    │   ├── local_models/           # 本地模型下载管理器 (Ollama 客户端 / 管道流)
    │   ├── models/                 # SQLite ORM 模型 (user, scenario, provider_config)
    │   └── schemas/                # Pydantic 校验与传输数据结构
    ├── requirements.txt
    └── .env.example
```

---

### 13.2 全部 HTTP 接口清单契约 (API Specification)

所有接口统一前缀：`/api/v1`。

#### 1. 登录注册与用户体系接口
- **POST `/api/v1/auth/login`**
  - 请求体：`{ "username": "student1", "password": "password123" }`
  - 响应体：`{ "code": 200, "data": { "accessToken": "...", "tokenType": "bearer", "user": { "id": 1, "username": "student1" } } }`
  - 错误码：400（参数缺失）、401（用户名或密码错误）。
- **POST `/api/v1/auth/register`**
  - 请求体：`{ "username": "string", "password": "string" }`
  - 响应体：201 Created。

#### 2. 页面置换算法计算接口
- **POST `/api/v1/algorithms/page-replacement/simulate`**
  - 请求体：`{ "algorithm": "LRU", "referenceString": [7,0,1,2,0,3], "frameCount": 3 }`
  - 响应体：返回完整包含 `totalSteps`、`metrics` 及 `steps` 数组的 `ExecutionTrace`。

#### 3. 银行家算法计算与判定接口
- **POST `/api/v1/algorithms/banker/check-safety`**
  - 请求体：`{ "available": [3,3,2], "maxMatrix": [...], "allocationMatrix": [...] }`
  - 响应体：`{ "code": 200, "data": { "isSafe": true, "safeSequence": ["P1","P3","P4","P0","P2"], "steps": [...] } }`
- **POST `/api/v1/algorithms/banker/request-resource`**
  - 请求体：`{ "processIndex": 1, "requestVector": [1,0,2], "currentState": {...} }`
  - 响应体：`{ "code": 200, "data": { "granted": true, "reason": "...", "trace": {...} } }`

#### 4. 多线程并发模拟接口
- **POST `/api/v1/algorithms/threads/simulate`**
  - 请求体：`{ "bufferCapacity": 5, "producerCount": 2, "consumerCount": 2, "totalOperations": 20 }`
  - 响应体：返回离散并发事件序列快照。

#### 5. 统一大模型 SSE 流式问答接口
- **POST `/api/v1/ai/chat/stream`**
  - 请求体：`{ "messages": [...], "contextSnapshot": {...} }`
  - 响应格式：`text/event-stream`，返回逐字 token 增量，以 `data: [DONE]` 终止。

#### 6. 模型引擎连通性与管理接口
- **POST `/api/v1/ai/engine/ping`**：测试任意厂商或自定义中转 `base_url` 的连通性与延迟。
- **GET `/api/v1/ai/engine/local/detect`**：探测本机 Ollama / LM Studio 是否运行及已装载模型列表。
- **POST `/api/v1/ai/engine/models/download`**：触发特定内置小模型的下载任务。
- **GET `/api/v1/ai/engine/models/status`**：获取全部内置小模型的实时五态状态与下载进度。

---

### 13.3 核心数据模型与共享类型定义 (TypeScript 契约)

```typescript
export type ThemeMode = 'dark' | 'light' | 'system';

export interface PageRepStep {
  stepIndex: number;
  page: number;
  status: 'HIT' | 'MISS';
  evictedPage: number | null;
  frames: (number | null)[];
  description: string;
  eventTone: 'HIT' | 'MISS' | 'NONE';
}

export interface BankerSafetyStep {
  stepIndex: number;
  process: string;
  workBefore: number[];
  need: number[];
  allocation: number[];
  workAfter: number[];
  finish: boolean[];
  description: string;
}

export interface ThreadStep {
  stepIndex: number;
  activeThreadId: string;
  threadType: 'PRODUCER' | 'CONSUMER';
  action: string;
  bufferState: (number | null)[];
  semaphores: { mutex: number; empty: number; full: number };
  description: string;
}
```

---

## 14. 端到端目标执行链 (End-to-End Execution Flow)

### 场景：用户使用本地 Ollama 驱动 AI 助教分析当前算法死锁成因
1. 用户在【模型引擎设置】点击“探测本地 Ollama”，系统探测到端口 `11434` 在线并填装 `qwen2.5:1.5b`。
2. 用户在【银行家算法】页面点击“向助教提问死锁成因”，前端将当前银行家算法的 Need 矩阵与 Available 向量快照注入 Prompt 上下文。
3. 前端发起 SSE 请求 `POST /api/v1/ai/chat/stream`，后端向 `http://localhost:11434/v1/chat/completions` 发起流式请求并泵送回前端。
4. 前端打字机动画实时解析 Markdown 并高亮输出，全程无需公网流量，完全离线响应。

---

## 15. 项目分期实施计划与风险评估

### 15.1 分期规划 (Milestones)

| 阶段 | 目标与交付功能 | 包含页面与模块 | 交付标准 |
| :--- | :--- | :--- | :--- |
| **Phase 1 (MVP 核心基石)** | 前端工程骨架 + **双主题（深色/浅色动态切换）** + 步进/回退播放引擎 + 页面置换算法可视化 | `P-LOGIN` (游客模式)、`P-PAGE-REP` (FIFO/LRU)、`AppShell`、`PlaybackDock`、`Web Audio` 合成器 | 能完整运行页面置换的自定义输入、单步前进后退、自动播放、音效反馈、缺页率统计 |
| **Phase 2 (进阶算法与并发)** | 银行家算法全套 + 生产者消费者多线程模拟 + 页面置换补充 (OPT/CLOCK) | `P-BANKER` (矩阵编辑、安全性推导、Request 判定)、`P-THREADS` (环形缓冲、信号量、线程状态监控) | 4 矩阵可交互编辑与判定；多线程能够直观展现互斥锁争抢与信号量阻塞 |
| **Phase 3 (多模型 AI 引擎)** | 多模型 AI 助教 + 12 厂商模板 + 自定义中转测试 + 账号鉴权持久化 | `P-AI-CHAT` (流式对话、上下文挂载)、`P-ENGINE-SETTINGS` (12 厂商模板、Ping 探测)、SQLite 鉴权 | 实时流式对话极速响应；中转连接测试正常；登录后支持保存矩阵案例 |
| **Phase 4 (本地部署与离线小模型)** | 本地部署对接 (Ollama) + 内置 4 款小模型下载与五态管理 + 全站综合优化 | `P-ENGINE-SETTINGS` (本地探测、断点续传下载、五态展示)、键盘快捷键支持 | 本地模型一键接通，离线小模型流畅下载与加载，全站 60fps 稳定运行 |

### 15.2 关键风险点与防范规避策略
1. **风险一：AI 流式响应超时与网络断连**
   - 前端实现 8 秒超时看门狗定时器与一键 `AbortController` 打断，提供友好重试机制。
2. **风险二：高倍速（8x）自动播放下的爆音（Click/Pop）与掉帧**
   - Web Audio 合成器中对振荡器 GainNode 施加 5ms 指数缓动渐变，消除突变方波爆音；界面使用 CSS 硬件加速。
3. **风险三：矩阵输入过大导致死循环或算力耗尽**
   - 前端强制限定输入边界：进程数最大 10，资源种类最大 6，数值在 0~99 之间，计算耗时严格 $<2\text{ms}$。
