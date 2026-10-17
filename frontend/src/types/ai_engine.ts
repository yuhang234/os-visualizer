/**
 * 模型引擎 / 厂商模板 / 本地部署 / 内置小模型类型（设计文档 §8 / §9 / §10）。
 * 字段与后端 `app/api/v1/ai_proxy.py`、`app/api/v1/engine_manager.py` 返回结构一致。
 */

export interface ProviderTemplate {
  key: string;
  name: string;
  baseUrl: string;
  defaultModel: string;
  models: string[];
  modelHint?: string;
  authHeader: string;
  authScheme: string;
  extraHeaders: Record<string, string>;
  openAiCompatible: boolean;
  sseTextPath: string;
  nativeProtocol?: string;
  category: 'cloud' | 'relay' | 'builtin';
  docsUrl: string;
  requiresApiKey?: boolean;
}

export interface SavedProviderConfig {
  id: number;
  providerKey: string;
  displayName: string;
  baseUrl: string;
  model: string;
  apiKeyMasked: string;
  hasApiKey: boolean;
  extraHeaders: Record<string, string>;
  isLocal: boolean;
  isActive: boolean;
  openAiCompatible: boolean;
  providerName: string;
  updatedAt: string;
}

export interface LocalRuntime {
  key: string;
  name: string;
  defaultPort: number;
  baseUrl: string;
  nativeBase: string;
  probePath: string;
  modelsPath: string;
  modelNameField: string;
  preferred: boolean;
  installHint: string;
}

export interface LocalProbe {
  key: string;
  name?: string;
  online: boolean;
  url?: string;
  baseUrl?: string;
  port?: number;
  latencyMs?: number;
  models: string[];
  errorCode?: string | null;
  error?: string | null;
}

export interface EngineCatalog {
  providers: ProviderTemplate[];
  localRuntimes: LocalRuntime[];
  mock: ProviderTemplate;
  saved: SavedProviderConfig[];
  guest: { dailyChatLimit: number; isGuest: boolean };
  serverDefaults: { provider: string; model: string; hasServerKey: boolean };
}

export type ModelState = 'NOT_DOWNLOADED' | 'DOWNLOADING' | 'READY' | 'LOADING' | 'ERROR';

export interface BuiltinModelMeta {
  id: string;
  name: string;
  parameters: string;
  docSizeLabel: string;
  bytesTotal: number;
  sha256: string;
  fileName: string;
  downloadUrl: string;
  sourceRepo: string;
  sourceUrl: string;
  license: string;
  languages: string;
  ability: string;
  expectedSpeed: string;
  backends: string[];
  quantization: string;
}

export interface ModelStatus {
  id: string;
  name: string;
  state: ModelState;
  paused: boolean;
  bytesDone: number;
  bytesTotal: number;
  percent: number;
  speedBps: number;
  etaSeconds: number | null;
  error: string;
  errorCode: string;
  downloaded: boolean;
  /** 载荷文件已通过 SHA-256 校验落在 models_cache（装载失败时仍为 true）。 */
  fileOnDisk: boolean;
  bytesOnDisk: number;
  loadedRuntime: string;
  runtimeModel: string;
  fileName: string;
  docSizeLabel: string;
  parameters: string;
  license: string;
  languages: string;
  ability: string;
  expectedSpeed: string;
  backends: string[];
  quantization: string;
  sourceRepo: string;
  sourceUrl: string;
  sha256: string;
}

export interface ModelDiskUsage {
  files: { id: string; name: string; fileName: string; bytes: number }[];
  totalBytes: number;
  directoryLabel: string;
}

export interface PingResult {
  ok: boolean;
  latencyMs?: number;
  httpStatus?: number;
  probePath?: string;
  models?: string[];
  modelExists?: boolean | null;
  errorCode?: string | null;
  error?: string | null;
}

export interface LocalDetectResult {
  runtimes: LocalProbe[];
  loadingBackends: {
    ollama: { online: boolean; error?: string | null; models: string[] };
    llamacpp: { binaryAvailable: boolean; binaryPath: string; hint: string };
  };
}

export interface LocalConnectResult {
  connected: boolean;
  probe: LocalProbe;
  model?: string;
  saved?: boolean;
  configId?: number;
}

export interface ProviderConfigPayload {
  providerKey: string;
  displayName?: string;
  baseUrl: string;
  model: string;
  apiKey?: string | null;
  extraHeaders: Record<string, string>;
  isLocal: boolean;
}

export interface PingPayload {
  providerKey?: string;
  baseUrl?: string;
  model?: string;
  apiKey?: string;
  extraHeaders?: Record<string, string>;
  providerId?: number;
}

/* ------------------------------ AI 对话 ------------------------------ */

export interface ChatContextSnapshot {
  pageReplacement?: Record<string, unknown>;
  banker?: Record<string, unknown>;
  threads?: Record<string, unknown>;
}

export interface ChatStreamPayload {
  messages: { role: 'system' | 'user' | 'assistant'; content: string }[];
  contextSnapshot?: ChatContextSnapshot;
  providerId?: number;
  providerKey?: string;
  model?: string;
  conversationId?: string;
}

/** SSE 帧（后端 `_sse` 产出，见 ai_proxy.py 模块注释） */
export type SseFrame =
  | {
      type: 'meta';
      provider: string;
      providerName?: string;
      model: string;
      source: string;
      conversationId?: string | null;
    }
  | { type: 'delta'; content: string }
  | { type: 'error'; code: string; message: string }
  | { type: 'done' };
