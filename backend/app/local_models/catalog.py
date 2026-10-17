"""内置离线小模型清单（4 款）。

设计文档第 10.1 节给出模型标识符、参数量、体积量级、来源与许可证。
下载 URL 与 SHA-256 校验值由本任务逐一实测核实（见交付报告"证据"章节）：

  Qwen2.5-0.5B-Instruct      HF Qwen/Qwen2.5-0.5B-Instruct-GGUF    491,400,032 B
  Qwen2.5-1.5B-Instruct      HF Qwen/Qwen2.5-1.5B-Instruct-GGUF  1,117,320,736 B
  DeepSeek-R1-Distill-Qwen-1.5B  HF unsloth/DeepSeek-R1-Distill-Qwen-1.5B-GGUF  1,117,321,312 B
  Llama-3.2-1B-Instruct      HF bartowski/Llama-3.2-1B-Instruct-GGUF  807,694,464 B

文档给出的"下载体积"是近似量级（~390 MB / ~980 MB / ~1.1 GB / ~800 MB），与实际 Q4_K_M
文件字节数存在差异；进度与磁盘占用以实测字节数为准，同时保留 docSizeLabel 供对照。
"""

from __future__ import annotations

from typing import Any

BUILTIN_MODELS: list[dict[str, Any]] = [
    {
        "id": "qwen2.5-0.5b-instruct",
        "name": "Qwen2.5-0.5B-Instruct",
        "parameters": "0.5B",
        "docSizeLabel": "~390 MB",
        "bytesTotal": 491_400_032,
        "sha256": "74a4da8c9fdbcd15bd1f6d01d621410d31c6fc00986f5eb687824e7b93d7a9db",
        "fileName": "qwen2.5-0.5b-instruct-q4_k_m.gguf",
        "downloadUrl": "https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct-GGUF/resolve/main/qwen2.5-0.5b-instruct-q4_k_m.gguf",
        "sourceRepo": "HuggingFace / ModelScope / Ollama Library",
        "sourceUrl": "https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct-GGUF",
        "license": "Apache 2.0",
        "languages": "中英双语",
        "ability": "操作系统基础概念与语法遵循极快",
        "expectedSpeed": "35 ~ 60 tokens/s",
        "backends": ["Ollama", "llama.cpp"],
        "quantization": "Q4_K_M (GGUF)",
    },
    {
        "id": "qwen2.5-1.5b-instruct",
        "name": "Qwen2.5-1.5B-Instruct",
        "parameters": "1.5B",
        "docSizeLabel": "~980 MB",
        "bytesTotal": 1_117_320_736,
        "sha256": "6a1a2eb6d15622bf3c96857206351ba97e1af16c30d7a74ee38970e434e9407e",
        "fileName": "qwen2.5-1.5b-instruct-q4_k_m.gguf",
        "downloadUrl": "https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF/resolve/main/qwen2.5-1.5b-instruct-q4_k_m.gguf",
        "sourceRepo": "HuggingFace / ModelScope / Ollama Library",
        "sourceUrl": "https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF",
        "license": "Apache 2.0",
        "languages": "中英双语",
        "ability": "逻辑推理扎实，具备 OS 核心代码分析能力",
        "expectedSpeed": "18 ~ 30 tokens/s",
        "backends": ["Ollama", "llama.cpp"],
        "quantization": "Q4_K_M (GGUF)",
    },
    {
        "id": "deepseek-r1-distill-qwen-1.5b",
        "name": "DeepSeek-R1-Distill-Qwen-1.5B",
        "parameters": "1.5B",
        "docSizeLabel": "~1.1 GB",
        "bytesTotal": 1_117_321_312,
        "sha256": "f3bdf9cf31dee4b57ae4e455a1cb0d01b5c2c1b50d72d3112141c195506c2840",
        "fileName": "DeepSeek-R1-Distill-Qwen-1.5B-Q4_K_M.gguf",
        "downloadUrl": "https://huggingface.co/unsloth/DeepSeek-R1-Distill-Qwen-1.5B-GGUF/resolve/main/DeepSeek-R1-Distill-Qwen-1.5B-Q4_K_M.gguf",
        "sourceRepo": "HuggingFace / Ollama Library",
        "sourceUrl": "https://huggingface.co/unsloth/DeepSeek-R1-Distill-Qwen-1.5B-GGUF",
        "license": "MIT",
        "languages": "中英双语",
        "ability": "具备思考链 (CoT) 推导，能分步解析页面置换与死锁",
        "expectedSpeed": "14 ~ 22 tokens/s",
        "backends": ["Ollama"],
        "quantization": "Q4_K_M (GGUF)",
    },
    {
        "id": "llama-3.2-1b-instruct",
        "name": "Llama-3.2-1B-Instruct",
        "parameters": "1.2B",
        "docSizeLabel": "~800 MB",
        "bytesTotal": 807_694_464,
        "sha256": "6f85a640a97cf2bf5b8e764087b1e83da0fdb51d7c9fab7d0fece9385611df83",
        "fileName": "Llama-3.2-1B-Instruct-Q4_K_M.gguf",
        "downloadUrl": "https://huggingface.co/bartowski/Llama-3.2-1B-Instruct-GGUF/resolve/main/Llama-3.2-1B-Instruct-Q4_K_M.gguf",
        "sourceRepo": "HuggingFace / Ollama Library",
        "sourceUrl": "https://huggingface.co/bartowski/Llama-3.2-1B-Instruct-GGUF",
        "license": "Llama 3.2 Community",
        "languages": "英文为主",
        "ability": "轻量指令微调，适合国际化或精简问答",
        "expectedSpeed": "25 ~ 40 tokens/s",
        "backends": ["Ollama", "llama.cpp"],
        "quantization": "Q4_K_M (GGUF)",
    },
]

MODEL_BY_ID: dict[str, dict[str, Any]] = {item["id"]: item for item in BUILTIN_MODELS}

# 五态生命周期（设计文档 10.2）
STATE_NOT_DOWNLOADED = "NOT_DOWNLOADED"
STATE_DOWNLOADING = "DOWNLOADING"
STATE_READY = "READY"
STATE_LOADING = "LOADING"
STATE_ERROR = "ERROR"
ALL_STATES = (STATE_NOT_DOWNLOADED, STATE_DOWNLOADING, STATE_READY, STATE_LOADING, STATE_ERROR)


def get_model(model_id: str) -> dict[str, Any] | None:
    return MODEL_BY_ID.get(model_id)


def list_models() -> list[dict[str, Any]]:
    return [dict(item) for item in BUILTIN_MODELS]


def total_download_bytes() -> int:
    return sum(item["bytesTotal"] for item in BUILTIN_MODELS)


def human_size(num_bytes: int) -> str:
    units = ["B", "KB", "MB", "GB", "TB"]
    value = float(num_bytes)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024
    return f"{num_bytes} B"
