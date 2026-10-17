# os-visualizer 纯前端静态展厅 (Showcase)

欢迎体验 **os-visualizer 操作系统核心原理可视化教学平台** 产品展厅！

本展厅是一个**纯静态、零后端依赖、零外部网络请求**的单文件产品展厅页，专为教学演示、课件展示以及在无网络环境或静态托管环境（如 GitHub Pages）下让用户快速上手与探索平台核心功能而设计。

---

## 🌟 展厅与真实产品的关系

| 维度 | 本静态展厅 (`docs/showcase/index.html`) | 真实完整产品 (`backend/` + `frontend/`) |
| :--- | :--- | :--- |
| **运行依赖** | **零依赖**：单文件 HTML，双击直接运行 | Node.js + Python FastAPI + SQLite |
| **算法计算** | 浏览器端本地重算与状态机模拟（O(1) 快照） | 后端高性能 NumPy/C++ 算法内核，支持超大矩阵 |
| **AI 助教问答** | 预置分片文本与 SSE 打字机流式模拟 | 真实对接公有云厂商 API (DeepSeek/OpenAI/豆包) 或本地 Ollama |
| **数据持久化** | 浏览器 `localStorage` 临时保存主题与偏好 | SQLite 完整支持账号体系、案例云端漫游与历史记录 |
| **网络请求** | **绝对零网络请求**（无 CDN、无外链字体/图标） | RESTful API + SSE 长连接 |

> [!NOTE]
> 真实完整产品开源仓库地址：[https://github.com/yuhang234/os-visualizer](https://github.com/yuhang234/os-visualizer)  
> 最新正式版发行说明：[Release v1.0.0](https://github.com/yuhang234/os-visualizer/releases/tag/v1.0.0)

---

## 🎮 展厅内包含的核心交互模拟

1. **页面置换算法实验室 (Page Replacement)**：
   - 内置教材经典参考串与四种核心算法（**FIFO / LRU / OPT / CLOCK**）在浏览器内的本地实时重算。
   - 支持完整的播放控制：播放 / 暂停 / 单步前进 / **O(1) 状态快照回退** / 首尾跳转 / 4 档倍速播放。
   - 页框插槽实时高亮命中 (Hit)、缺页 (Miss) 与淘汰，CLOCK 算法支持指针巡检与使用位 (Use Bit) 动画。
   - 动态更新累计访问、缺页次数、命中次数与 SVG 缺页率环形进度。

2. **银行家算法与死锁检测 (Banker's Algorithm)**：
   - 预置经典 5 进程 3 资源矩阵（Max / Allocation / Need / Available）。
   - 点击「安全性检查」以动画步进方式演示 Work 向量与 Finish 状态推导，按顺序点亮安全序列 $\langle P_1 \to P_3 \to P_4 \to P_0 \to P_2 \rangle$。
   - 资源申请沙箱：演示 $P_1$ 申请安全批准、以及 $P_4$ 申请触发死锁风险拒绝并**原子回滚**。

3. **多线程并发互斥（生产者-消费者模型）**：
   - 5 槽位有界缓冲区环形队列动画。
   - 实时联动互斥锁（`mutex`）、空位信号量（`empty`）与产品信号量（`full`）状态条。
   - 支持单步生产、单步消费、自动循环，以及缓冲区满/空时触发线程阻塞挂起的模拟与伪代码行高亮。

4. **多模型 AI 助教交互系统**：
   - 模拟 SSE 流式打字机逐字输出（带呼吸闪烁光标 `▋`），支持中途停止生成。
   - 支持切换「内置离线规则」、「DeepSeek-Reasoner 思考链」、「Ollama 本地私有化」三种引擎风格。
   - 内置常见考点问答解析，演示 Markdown 语法树与操作系统数学公式排版渲染。

5. **模型引擎配置中心**：
   - 12 家云端主流模型厂商模板（OpenAI、Claude、Gemini、DeepSeek、阿里云、豆包、硅基流动等），点击载入配置并可进行掩码 API Key 查看与连通性 Ping 模拟。
   - 4 大本地运行时（Ollama、LM Studio、llama.cpp、vLLM）在线探测状态与重新探测动画。
   - 4 款离线内置小模型（Qwen2.5-0.5B/1.5B、DeepSeek-R1-1.5B 等）五态生命周期，支持模拟下载进度条推进至 100% 变更为已就绪。

6. **用户鉴权与游客模式**：
   - 登录/注册表单前端校验，模拟认证成功后全局顶栏身份联动切换为正式学员。
   - 提供免密一键体验的“游客模式”。

7. **深色 / 浅色双主题切换**：
   - 严格对齐 `docs/design-spec.md` 第 3 节设计令牌体系，支持「跟随系统 / 深色 / 浅色」三态无缝切换并持久化至本地。

8. **Web Audio 程序化音效**：
   - 纯 HTML5 Web Audio API 振荡器程序化合成正弦波、三角波与锯齿波，提供命中、缺页、死锁警报与单步音效，支持音量调节与全局静音。

9. **全局运行审计日志控制台**：
   - 实时记录并审计展厅内的所有操作事件，支持时间戳、级别色彩高亮与模块过滤。

---

## 🚀 如何在本地打开

由于本页面是**纯单文件 HTML** 且**不包含任何跨域资源或外部请求**，你可以选择任意方式运行：

### 方法一：直接双击打开（最简单）
使用文件管理器找到 `docs/showcase/index.html`，直接双击或拖拽入 Chrome / Edge / Firefox / Safari 浏览器窗口即可使用（URL 形如 `file:///.../docs/showcase/index.html`）。

### 方法二：本地简易 HTTP 服务器（可选）
如果你希望通过 HTTP 协议访问：
```bash
# 在仓库根目录下执行
python3 -m http.server 8000
```
打开浏览器访问：`http://localhost:8000/docs/showcase/index.html`

---

## 🌐 如何部署到 GitHub Pages

`docs/showcase/` 目录完美契合 GitHub Pages 的原生支持：

1. 将仓库代码推送到 GitHub。
2. 进入 GitHub 仓库页面，点击 **Settings** ➔ **Pages**。
3. 在 **Build and deployment** ➔ **Source** 中选择 **Deploy from a branch**。
4. 在 **Branch** 下拉框中选择主分支（如 `main`），文件夹选择 `/docs` 目录，点击 **Save**。
5. 部署完成后，通过生成的 GitHub Pages 链接即可访问：  
   `https://<username>.github.io/<repo>/showcase/index.html`
