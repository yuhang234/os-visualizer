# os-visualizer 文档与在线展厅

本目录同时是 GitHub Pages 的发布源（`main` 分支 `docs/` 目录）。

| 路径 | 内容 |
| :--- | :--- |
| [`index.html`](index.html) | 入口落地页，自动跳转到交互展厅 |
| [`showcase/`](showcase/) | **交互展厅**：纯静态、零依赖，用浏览器内模拟完整展示产品功能（页面置换、银行家算法、多线程并发、AI 助教、模型引擎设置、登录、双主题、音效、日志） |
| [`design-spec.md`](design-spec.md) | 设计契约：双主题令牌一一对应表、三个算法页线框图与控件树、12 家厂商模板核实表、鉴权时序图、工程目录树与全部 HTTP 接口契约 |
| [`mockup.html`](mockup.html) | 设计阶段的交互原型（单文件、可切换主题） |

在线地址：<https://yuhang234.github.io/os-visualizer/>

> 展厅中的全部功能均由浏览器本地脚本模拟，不连接后端，用于对外展示；真实产品请按仓库根目录 [`README.md`](../README.md) 的说明本地启动。
