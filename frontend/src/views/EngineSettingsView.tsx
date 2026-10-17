/**
 * 模型引擎设置页（设计文档 §9 / §10 / §13.2）。
 * 四个标签页：
 *  1. 主流厂商模板（12 家）+ 配置表单 + Ping 探活 + 已保存配置管理
 *  2. 自定义中转 API（OpenAI 兼容网关）
 *  3. 本地部署接入（Ollama / LM Studio / llama.cpp / vLLM 一键探测与接入）
 *  4. 内置离线小模型下载（五态生命周期：下载 / 暂停 / 取消 / 重试 / 删除 / 装载）
 * 所有密钥与本地路径均由后端保管，前端仅显示掩码。
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Activity,
  Cable,
  CheckCircle2,
  Cloud,
  DownloadCloud,
  HardDrive,
  Loader2,
  Pause,
  Play,
  RefreshCw,
  Search,
  Server,
  Trash2,
  XCircle,
  Zap,
} from 'lucide-react';
import {
  activateProviderConfig,
  cancelModel,
  connectLocalRuntime,
  deleteModel,
  deleteProviderConfig,
  detectLocalRuntimes,
  downloadModel,
  fetchEngineCatalog,
  fetchModelCatalog,
  fetchModelStatus,
  listProviderConfigs,
  loadModel,
  pauseModel,
  pingEngine,
  retryModel,
  saveProviderConfig,
  unloadModel,
} from '../services/engineApi';
import type { ModelCatalogPayload } from '../services/engineApi';
import { errorMessage } from '../services/client';
import { Badge } from '../components/common/Badge';
import { PasswordField } from '../components/common/PasswordField';
import type {
  EngineCatalog,
  LocalDetectResult,
  ModelDiskUsage,
  ModelStatus,
  PingResult,
  ProviderTemplate,
  SavedProviderConfig,
} from '../types/ai_engine';

type TabKey = 'providers' | 'custom' | 'local' | 'models';

const TABS: { key: TabKey; label: string; icon: typeof Cloud }[] = [
  { key: 'providers', label: '主流厂商模板 (12 家)', icon: Cloud },
  { key: 'custom', label: '自定义中转 API', icon: Cable },
  { key: 'local', label: '本地部署接入 (Ollama 等)', icon: Server },
  { key: 'models', label: '内置离线小模型 (4 款)', icon: DownloadCloud },
];

const STATE_LABEL: Record<string, string> = {
  NOT_DOWNLOADED: '未下载',
  DOWNLOADING: '下载中',
  READY: '已就绪',
  LOADING: '装载中',
  ERROR: '失败',
};

const STATE_TONE: Record<string, 'muted' | 'accent' | 'success' | 'warning' | 'danger'> = {
  NOT_DOWNLOADED: 'muted',
  DOWNLOADING: 'accent',
  READY: 'success',
  LOADING: 'warning',
  ERROR: 'danger',
};

function formatBytes(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes <= 0) return '0 B';
  if (bytes >= 1024 ** 3) return `${(bytes / 1024 ** 3).toFixed(2)} GB`;
  if (bytes >= 1024 ** 2) return `${(bytes / 1024 ** 2).toFixed(1)} MB`;
  if (bytes >= 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${bytes} B`;
}

function parseHeaders(text: string): { headers?: Record<string, string>; error?: string } {
  const trimmed = text.trim();
  if (!trimmed) return { headers: {} };
  try {
    const parsed: unknown = JSON.parse(trimmed);
    if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) {
      return { error: '自定义请求头必须是 JSON 对象，例如 {"X-Foo": "bar"}' };
    }
    const headers: Record<string, string> = {};
    for (const [key, value] of Object.entries(parsed as Record<string, unknown>)) {
      headers[key] = String(value);
    }
    return { headers };
  } catch {
    return { error: '自定义请求头不是合法 JSON，请检查引号与逗号' };
  }
}

/* ------------------------------ 厂商配置表单 ------------------------------ */

function ProviderEditor({
  template,
  saved,
  onSaved,
  variant,
}: {
  template: ProviderTemplate | null;
  saved: SavedProviderConfig | null;
  onSaved: () => void;
  variant: 'template' | 'custom';
}) {
  const providerKey = template?.key ?? 'custom';
  const [baseUrl, setBaseUrl] = useState(saved?.baseUrl ?? template?.baseUrl ?? '');
  const [model, setModel] = useState(saved?.model ?? template?.defaultModel ?? '');
  const [apiKey, setApiKey] = useState('');
  const [headersText, setHeadersText] = useState(saved ? JSON.stringify(saved.extraHeaders ?? {}) : '');
  const [displayName, setDisplayName] = useState(saved?.displayName ?? template?.name ?? '');
  const [pinging, setPinging] = useState(false);
  const [ping, setPing] = useState<PingResult | null>(null);
  const [pingError, setPingError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  // 切换厂商卡片 / 已保存配置时同步表单
  useEffect(() => {
    setBaseUrl(saved?.baseUrl ?? template?.baseUrl ?? '');
    setModel(saved?.model ?? template?.defaultModel ?? '');
    setDisplayName(saved?.displayName ?? template?.name ?? '');
    setHeadersText(saved ? JSON.stringify(saved.extraHeaders ?? {}) : '');
    setApiKey('');
    setPing(null);
    setPingError(null);
    setMessage(null);
    setError(null);
  }, [providerKey, saved, template]);

  const handlePing = async () => {
    const parsed = parseHeaders(headersText);
    if (parsed.error) {
      setPingError(parsed.error);
      return;
    }
    setPinging(true);
    setPing(null);
    setPingError(null);
    try {
      const result = await pingEngine({
        providerKey,
        baseUrl: baseUrl.trim(),
        model: model.trim(),
        apiKey: apiKey.trim() || undefined,
        extraHeaders: parsed.headers,
      });
      setPing(result);
    } catch (thrown) {
      setPingError(errorMessage(thrown));
    } finally {
      setPinging(false);
    }
  };

  const handleSave = async (activate: boolean) => {
    const parsed = parseHeaders(headersText);
    if (parsed.error) {
      setError(parsed.error);
      return;
    }
    if (!baseUrl.trim()) {
      setError('Base URL 不能为空');
      return;
    }
    if (!model.trim()) {
      setError('模型名称不能为空');
      return;
    }
    setSaving(true);
    setError(null);
    setMessage(null);
    try {
      const result = await saveProviderConfig({
        providerKey,
        displayName: displayName.trim() || template?.name,
        baseUrl: baseUrl.trim(),
        model: model.trim(),
        apiKey: apiKey.trim() ? apiKey.trim() : undefined,
        extraHeaders: parsed.headers ?? {},
        isLocal: false,
      });
      if (activate) {
        await activateProviderConfig(result.id);
      }
      setApiKey('');
      setMessage(activate ? '配置已保存并设为当前对话引擎' : '配置已保存（密钥仅存于后端）');
      onSaved();
    } catch (thrown) {
      setError(errorMessage(thrown));
    } finally {
      setSaving(false);
    }
  };

  const handleClearKey = async () => {
    const parsed = parseHeaders(headersText);
    if (parsed.error) {
      setError(parsed.error);
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await saveProviderConfig({
        providerKey,
        displayName: displayName.trim() || template?.name,
        baseUrl: baseUrl.trim(),
        model: model.trim(),
        apiKey: '',
        extraHeaders: parsed.headers ?? {},
        isLocal: false,
      });
      setMessage('已清除该厂商保存的密钥');
      onSaved();
    } catch (thrown) {
      setError(errorMessage(thrown));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="flex-col">
      <div className="flex-between">
        <strong style={{ color: 'var(--color-accent-primary)' }}>
          当前配置：{displayName || template?.name || '自定义中转'}
        </strong>
        <div className="row-inline">
          {saved ? <Badge tone="success">已保存配置 #{saved.id}</Badge> : <Badge tone="muted">未保存</Badge>}
          {saved?.isActive ? <Badge tone="accent">当前默认引擎</Badge> : null}
        </div>
      </div>

      {template ? (
        <div className="help-text">
          {variant === 'custom'
            ? '接入任意 OpenAI 兼容网关（OneAPI / NewAPI / 个人反代）：填写 Base URL 与令牌即可。'
            : `${template.openAiCompatible ? 'OpenAI 兼容协议' : `私有协议：${template.nativeProtocol ?? 'Messages'}`} · 鉴权头 ${template.authHeader} · 文档 ${template.docsUrl}`}
        </div>
      ) : null}

      <div className="grid-2">
        <label className="field">
          <span className="field-label">服务基地址 (Base URL)</span>
          <input className="input-field input-mono" value={baseUrl} onChange={(event) => setBaseUrl(event.target.value)} />
        </label>
        <label className="field">
          <span className="field-label">模型名称 / Endpoint ID (model)</span>
          <input
            className="input-field input-mono"
            value={model}
            placeholder={template?.models.length ? `如 ${template.models.slice(0, 2).join(' / ')}` : '如 gpt-4o-mini'}
            onChange={(event) => setModel(event.target.value)}
          />
        </label>
      </div>

      <PasswordField
        label="API Key（后端加密存储，前端只显示掩码）"
        value={apiKey}
        onChange={setApiKey}
        placeholder={saved?.hasApiKey ? `已保存：${saved.apiKeyMasked}（留空表示保留）` : 'sk-...'}
        autoComplete="off"
      />
      <div className="help-text">
        {saved?.hasApiKey
          ? `当前已存密钥：${saved.apiKeyMasked}。留空保存 = 保留原密钥；点击「清除已存密钥」立即删除。`
          : '密钥经后端 AES 加密后存入 SQLite，任何接口都不会回传明文。'}
      </div>

      <details>
        <summary className="help-text" style={{ cursor: 'pointer' }}>
          高级：自定义请求头 JSON（可选，最多 20 项）
        </summary>
        <textarea
          className="input-field input-mono mt-8"
          rows={3}
          value={headersText}
          placeholder='{"X-Custom-Header": "value"}'
          onChange={(event) => setHeadersText(event.target.value)}
        />
      </details>

      {ping ? (
        <div className={`ping-result ${ping.ok ? 'ok' : 'fail'}`}>
          {ping.ok ? (
            <>
              ✅ 连通成功 · 延迟 {ping.latencyMs ?? '—'} ms · HTTP {ping.httpStatus ?? 200}
              {ping.probePath ? ` · 探测端点 ${ping.probePath}` : ''}
              {ping.modelExists === false ? ' · 注意：模型列表中未找到该模型标识' : ''}
              {ping.models && ping.models.length > 0 ? <div className="mono-xs mt-8">可用模型：{ping.models.slice(0, 6).join('、')}</div> : null}
            </>
          ) : (
            <>
              ❌ 连接失败{ping.errorCode ? ` [${ping.errorCode}]` : ''}：{ping.error ?? '未知错误'}
              {ping.httpStatus ? ` · HTTP ${ping.httpStatus}` : ''}
            </>
          )}
        </div>
      ) : null}
      {pingError ? <div className="alert alert-error">{pingError}</div> : null}
      {message ? <div className="alert alert-success">{message}</div> : null}
      {error ? <div className="alert alert-error">{error}</div> : null}

      <div className="row-inline" style={{ justifyContent: 'flex-end' }}>
        <button className="btn btn-secondary btn-sm" onClick={() => void handlePing()} disabled={pinging} type="button">
          {pinging ? <span className="spinner" /> : <Zap size={15} />}
          {pinging ? '探测中…' : variant === 'custom' ? '⚡ 测试中转可用性' : '⚡ 测试连接状态'}
        </button>
        {saved?.hasApiKey ? (
          <button className="btn btn-secondary btn-sm btn-danger" onClick={() => void handleClearKey()} disabled={saving} type="button">
            清除已存密钥
          </button>
        ) : null}
        <button className="btn btn-secondary btn-sm" onClick={() => void handleSave(false)} disabled={saving} type="button">
          保存配置
        </button>
        <button className="btn btn-primary btn-sm" onClick={() => void handleSave(true)} disabled={saving} type="button">
          {saving ? <span className="spinner" /> : null}
          保存并设为默认助教
        </button>
      </div>
    </div>
  );
}

/* ------------------------------ 主视图 ------------------------------ */

export function EngineSettingsView() {
  const [tab, setTab] = useState<TabKey>('providers');
  const [catalog, setCatalog] = useState<EngineCatalog | null>(null);
  const [saved, setSaved] = useState<SavedProviderConfig[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [selectedKey, setSelectedKey] = useState('openai');
  const [banner, setBanner] = useState<string | null>(null);

  const [detect, setDetect] = useState<LocalDetectResult | null>(null);
  const [detecting, setDetecting] = useState(false);
  const [detectError, setDetectError] = useState<string | null>(null);
  const [localHost, setLocalHost] = useState('localhost');
  const [localModel, setLocalModel] = useState<Record<string, string>>({});
  const [connectingKey, setConnectingKey] = useState<string | null>(null);
  const [localResult, setLocalResult] = useState<Record<string, string>>({});

  const [modelCatalog, setModelCatalog] = useState<ModelCatalogPayload | null>(null);
  const [modelStatus, setModelStatus] = useState<ModelStatus[]>([]);
  const [modelDisk, setModelDisk] = useState<ModelDiskUsage | null>(null);
  const [modelBusy, setModelBusy] = useState<string | null>(null);
  const [modelMessage, setModelMessage] = useState<string | null>(null);
  const [modelError, setModelError] = useState<string | null>(null);
  const pollRef = useRef<number | null>(null);

  const refreshSaved = useCallback(async () => {
    try {
      setSaved(await listProviderConfigs());
    } catch (thrown) {
      setLoadError(errorMessage(thrown));
    }
  }, []);

  useEffect(() => {
    let disposed = false;
    Promise.all([fetchEngineCatalog(), listProviderConfigs()])
      .then(([catalogResult, providers]) => {
        if (disposed) return;
        setCatalog(catalogResult);
        setSaved(providers);
        setLoadError(null);
      })
      .catch((thrown) => {
        if (!disposed) setLoadError(errorMessage(thrown));
      });
    return () => {
      disposed = true;
    };
  }, []);

  /* ---------- 内置小模型：目录 + 状态轮询 ---------- */
  const refreshModelStatus = useCallback(async () => {
    try {
      const result = await fetchModelStatus();
      setModelStatus(result.models);
      setModelDisk(result.disk);
    } catch (thrown) {
      setModelError(errorMessage(thrown));
    }
  }, []);

  useEffect(() => {
    if (tab !== 'models') return undefined;
    let disposed = false;
    const bootstrap = async () => {
      try {
        const catalogResult = await fetchModelCatalog();
        if (!disposed) setModelCatalog(catalogResult);
        await refreshModelStatus();
      } catch (thrown) {
        if (!disposed) setModelError(errorMessage(thrown));
      }
    };
    void bootstrap();
    return () => {
      disposed = true;
    };
  }, [tab, refreshModelStatus]);

  const hasActiveModel = modelStatus.some((model) => model.state === 'DOWNLOADING' || model.state === 'LOADING' || model.state === 'ERROR');
  useEffect(() => {
    if (tab !== 'models' || !hasActiveModel) return undefined;
    pollRef.current = window.setInterval(() => {
      void refreshModelStatus();
    }, 1500);
    return () => {
      if (pollRef.current != null) window.clearInterval(pollRef.current);
      pollRef.current = null;
    };
  }, [tab, hasActiveModel, refreshModelStatus]);

  const runModelAction = useCallback(
    async (modelId: string, action: () => Promise<unknown>, successMessage: string) => {
      setModelBusy(modelId);
      setModelError(null);
      setModelMessage(null);
      try {
        await action();
        await refreshModelStatus();
        setModelMessage(successMessage);
      } catch (thrown) {
        setModelError(errorMessage(thrown));
      } finally {
        setModelBusy(null);
      }
    },
    [refreshModelStatus],
  );

  const handleDetect = async () => {
    setDetecting(true);
    setDetectError(null);
    try {
      const result = await detectLocalRuntimes();
      setDetect(result);
      const firstOnline = result.runtimes.find((runtime) => runtime.online && runtime.models.length > 0);
      if (firstOnline) {
        setLocalModel((current) => ({ ...current, [firstOnline.key]: current[firstOnline.key] || firstOnline.models[0] }));
      }
    } catch (thrown) {
      setDetectError(errorMessage(thrown));
    } finally {
      setDetecting(false);
    }
  };

  const handleConnect = async (runtimeKey: string) => {
    setConnectingKey(runtimeKey);
    setLocalResult((current) => ({ ...current, [runtimeKey]: '' }));
    try {
      const result = await connectLocalRuntime({
        runtimeKey,
        host: localHost.trim() || 'localhost',
        model: localModel[runtimeKey] ?? '',
        save: true,
      });
      if (result.connected && result.saved) {
        setLocalResult((current) => ({
          ...current,
          [runtimeKey]: `已接入并设为当前对话引擎：${result.model ?? ''}`,
        }));
        setBanner(`已接入本地 ${runtimeKey} · 模型 ${result.model ?? ''}`);
        await refreshSaved();
      } else if (result.connected) {
        setLocalResult((current) => ({ ...current, [runtimeKey]: `服务在线，模型 ${result.model ?? ''} 可用（未保存配置）` }));
      } else {
        setLocalResult((current) => ({
          ...current,
          [runtimeKey]: `未能接入：${result.probe.error ?? '服务未在线，请先启动本地推理服务'}`,
        }));
      }
    } catch (thrown) {
      setLocalResult((current) => ({ ...current, [runtimeKey]: errorMessage(thrown) }));
    } finally {
      setConnectingKey(null);
    }
  };

  const templates = catalog?.providers ?? [];
  const selectedTemplate = useMemo(
    () => templates.find((item) => item.key === selectedKey) ?? null,
    [selectedKey, templates],
  );
  const selectedSaved = useMemo(() => saved.find((item) => item.providerKey === selectedKey) ?? null, [saved, selectedKey]);
  const customTemplate = useMemo(() => templates.find((item) => item.key === 'custom') ?? null, [templates]);
  const customSaved = useMemo(() => saved.find((item) => item.providerKey === 'custom') ?? null, [saved]);
  const runtimeList = detect?.runtimes ?? [];
  const runtimesMeta = catalog?.localRuntimes ?? [];

  interface RuntimeCardData {
    key: string;
    name: string;
    online: boolean;
    port?: number;
    baseUrl?: string;
    latencyMs?: number;
    models: string[];
    error?: string | null;
  }
  const runtimeCards = useMemo<RuntimeCardData[]>(() => {
    if (runtimeList.length > 0) {
      return runtimeList.map((runtime) => ({
        key: runtime.key,
        name: runtime.name ?? runtime.key,
        online: runtime.online,
        port: runtime.port,
        baseUrl: runtime.baseUrl,
        latencyMs: runtime.latencyMs,
        models: runtime.models ?? [],
        error: runtime.error,
      }));
    }
    return runtimesMeta.map((meta) => ({ key: meta.key, name: meta.name, online: false, models: [] }));
  }, [runtimeList, runtimesMeta]);

  return (
    <div>
      <div className="page-head">
        <span className="page-title">AI 引擎与本地模型管理中心</span>
        <div className="page-actions">
          <Badge tone="info">统一接口：REST / SSE</Badge>
          <Badge tone="muted">密钥后端加密存储</Badge>
        </div>
      </div>

      {banner ? (
        <div className="alert alert-success mb-12" onClick={() => setBanner(null)} role="presentation">
          {banner}
        </div>
      ) : null}
      {loadError ? <div className="alert alert-error mb-12">引擎目录加载失败：{loadError}</div> : null}

      <div className="card mb-12">
        <div className="tabs">
          {TABS.map((item) => {
            const Icon = item.icon;
            return (
              <button
                key={item.key}
                className={`tabs-item${tab === item.key ? ' active' : ''}`}
                onClick={() => setTab(item.key)}
                type="button"
              >
                <Icon size={15} /> {item.label}
              </button>
            );
          })}
        </div>
      </div>

      {tab === 'providers' ? (
        <div className="card">
          <div className="card-title">主流厂商模板（12 家，含官方与 OpenAI 兼容端点）</div>
          <div className="provider-grid mb-16">
            {templates.map((item) => {
              const hasSaved = saved.some((config) => config.providerKey === item.key);
              return (
                <div
                  key={item.key}
                  className={`provider-card${selectedKey === item.key ? ' selected' : ''}${hasSaved ? ' saved' : ''}`}
                  onClick={() => setSelectedKey(item.key)}
                  role="button"
                  tabIndex={0}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter') setSelectedKey(item.key);
                  }}
                >
                  <div className="pc-name">
                    {item.name}
                    {hasSaved ? <CheckCircle2 size={13} style={{ color: 'var(--color-success)' }} /> : null}
                  </div>
                  <div className="pc-url">{item.baseUrl}</div>
                  <div className="help-text mt-8">
                    {item.openAiCompatible ? 'OpenAI 兼容' : (item.nativeProtocol ?? '私有协议')} · {item.defaultModel}
                  </div>
                </div>
              );
            })}
          </div>
          <div className="config-card">
            <ProviderEditor
              template={selectedTemplate}
              saved={selectedSaved}
              onSaved={() => void refreshSaved()}
              variant={selectedKey === 'custom' ? 'custom' : 'template'}
            />
          </div>
        </div>
      ) : null}

      {tab === 'custom' ? (
        <div className="card">
          <div className="card-title">自定义 OpenAI 兼容中转网关（OneAPI / NewAPI / 个人反代）</div>
          <div className="config-card">
            <ProviderEditor template={customTemplate} saved={customSaved} onSaved={() => void refreshSaved()} variant="custom" />
          </div>
        </div>
      ) : null}

      {tab === 'local' ? (
        <div className="card">
          <div className="flex-between mb-12">
            <div>
              <div className="card-title mb-0">本地推理后端服务探测 (Local Inference Engine)</div>
              <div className="help-text">适用于学校机房、无网离线或纯内网环境；探测接口与端口来自各方案官方默认值。</div>
            </div>
            <div className="row-inline">
              <input
                className="input-field input-inline"
                style={{ width: 120 }}
                value={localHost}
                onChange={(event) => setLocalHost(event.target.value)}
                title="本地主机名（默认 localhost）"
              />
              <button className="btn btn-primary btn-sm" onClick={() => void handleDetect()} disabled={detecting} type="button">
                {detecting ? <span className="spinner" /> : <Search size={15} />}
                {detecting ? '探测中…' : '🔍 一键探测本地推理服务'}
              </button>
            </div>
          </div>

          {detectError ? <div className="alert alert-error mb-12">{detectError}</div> : null}

          <div className="runtime-grid">
            {runtimeCards.map((runtime) => {
              const meta = runtimesMeta.find((item) => item.key === runtime.key);
              const models = runtime.models;
              return (
                <div key={runtime.key} className={`runtime-card${runtime.online ? ' online' : ''}`}>
                  <div className="flex-between">
                    <strong>{runtime.name}</strong>
                    {runtime.online ? (
                      <Badge tone="success">🟢 运行中 (Port: {runtime.port ?? meta?.defaultPort})</Badge>
                    ) : (
                      <Badge tone="muted">未运行 (Port: {meta?.defaultPort ?? '—'})</Badge>
                    )}
                  </div>
                  <div className="help-text mt-8">
                    接口端点：<code>{runtime.baseUrl ?? meta?.baseUrl ?? '—'}</code>
                    <br />
                    {runtime.online ? (
                      <>
                        延迟 {runtime.latencyMs ?? '—'} ms · 已探测到模型：
                        {models.length > 0 ? <strong style={{ color: 'var(--color-accent-primary)' }}> {models.join('、')}</strong> : ' 无（请先 ollama pull）'}
                      </>
                    ) : (
                      <>
                        {runtime.error ? `探测失败：${runtime.error}` : '启动方式：'} {meta?.installHint ?? ''}
                      </>
                    )}
                  </div>
                  {runtime.online ? (
                    models.length > 0 ? (
                      <>
                        <div className="model-actions mt-12">
                          <select
                            className="input-field input-inline"
                            style={{ maxWidth: 220 }}
                            value={localModel[runtime.key] ?? models[0]}
                            onChange={(event) => setLocalModel((current) => ({ ...current, [runtime.key]: event.target.value }))}
                          >
                            {models.map((name: string) => (
                              <option key={name} value={name}>
                                {name}
                              </option>
                            ))}
                          </select>
                          <button
                            className="btn btn-primary btn-sm"
                            onClick={() => void handleConnect(runtime.key)}
                            disabled={connectingKey === runtime.key}
                            type="button"
                          >
                            {connectingKey === runtime.key ? <span className="spinner" /> : <Cable size={15} />}
                            一键接入并设为对话引擎
                          </button>
                        </div>
                        <div className="help-text mt-8">
                          命令行快捷拉取新模型：<code>ollama pull qwen2.5:1.5b</code>
                        </div>
                      </>
                    ) : (
                      <div className="alert alert-warning mt-12" style={{ fontSize: 'var(--font-size-xs)' }}>
                        服务在线但没有可用模型，请先执行 <code>ollama pull qwen2.5:1.5b</code> 等命令。
                      </div>
                    )
                  ) : null}
                  {localResult[runtime.key] ? <div className="help-text mt-8">{localResult[runtime.key]}</div> : null}
                </div>
              );
            })}
          </div>

          {detect ? (
            <div className="alert alert-info mt-16" style={{ fontSize: 'var(--font-size-xs)' }}>
              <strong>装载后端诊断：</strong> Ollama（{detect.loadingBackends.ollama.online ? '在线' : '离线'} · 模型 {detect.loadingBackends.ollama.models.length} 个）；
              llama.cpp（{detect.loadingBackends.llamacpp.binaryAvailable ? `可用：${detect.loadingBackends.llamacpp.binaryPath}` : detect.loadingBackends.llamacpp.hint}）
            </div>
          ) : null}
        </div>
      ) : null}

      {tab === 'models' ? (
        <div className="card">
          <div className="flex-between mb-12">
            <div>
              <div className="card-title mb-0">内置离线小模型下载与生命周期管理（4 款真实小模型）</div>
              <div className="help-text">
                下载由后端流式管道完成并做 SHA-256 校验，支持断点续传；下载目录 {modelCatalog?.modelsDirLabel ?? 'backend/models_cache'}/（服务器绝对路径不进入浏览器）
              </div>
            </div>
            <div className="row-inline">
              <Badge tone="info">纯 CPU 可跑 · 免显卡</Badge>
              <button className="btn btn-secondary btn-sm" onClick={() => void refreshModelStatus()} type="button">
                <RefreshCw size={15} /> 刷新状态
              </button>
            </div>
          </div>

          {modelError ? <div className="alert alert-error mb-12">{modelError}</div> : null}
          {modelMessage ? (
            <div className="alert alert-success mb-12" onClick={() => setModelMessage(null)} role="presentation">
              {modelMessage}
            </div>
          ) : null}

          <div className="disk-usage mb-12">
            <span>
              <HardDrive size={13} /> 已下载磁盘占用：{formatBytes(modelDisk?.totalBytes ?? 0)} / 全部 4 款共 {formatBytes(modelCatalog?.totalBytes ?? 0)}
            </span>
            <span>目录：{modelDisk?.directoryLabel ?? '—'}/</span>
          </div>

          <div className="flex-col">
            {modelStatus.map((model) => {
              const busy = modelBusy === model.id;
              return (
                <div key={model.id} className={`model-card${model.loadedRuntime ? ' loaded' : ''}`}>
                  <div className="model-head">
                    <div style={{ flex: 1 }}>
                      <div className="row-inline">
                        <span className="model-name">{model.name}</span>
                        <span className={`state-chip state-${model.state}`}>
                          {STATE_LABEL[model.state] ?? model.state}
                          {model.state === 'DOWNLOADING' ? ` ${model.percent.toFixed(1)}%` : ''}
                          {model.paused ? '（已暂停）' : ''}
                        </span>
                        {model.loadedRuntime ? <Badge tone="success">已装载：{model.loadedRuntime}</Badge> : null}
                      </div>
                      <div className="model-spec mt-8">
                        参数量: {model.parameters} · 体积: {model.docSizeLabel} · 许可证: {model.license} · CPU 速度: {model.expectedSpeed}
                        <br />
                        能力: {model.ability} · 推荐后端: {model.backends.join(' / ')} · 量化: {model.quantization}
                        <br />
                        来源: {model.sourceRepo}（{model.sourceUrl}）
                      </div>
                    </div>
                    <Badge tone={STATE_TONE[model.state] ?? 'muted'}>{model.state}</Badge>
                  </div>

                  {model.state === 'DOWNLOADING' ? (
                    <>
                      <div className="model-progress">
                        <div className="model-progress-fill" style={{ width: `${Math.min(100, Math.max(0, model.percent))}%` }} />
                      </div>
                      <div className="disk-usage">
                        <span>
                          已下载 {formatBytes(model.bytesDone)} / {formatBytes(model.bytesTotal)}
                        </span>
                        <span>速率 {formatBytes(model.speedBps)}/s</span>
                        <span>{model.etaSeconds != null ? `剩余约 ${Math.max(1, Math.round(model.etaSeconds))} s` : '估算中…'}</span>
                        <span>断点续传：已保留分片文件</span>
                      </div>
                    </>
                  ) : null}

                  {model.state === 'ERROR' && model.error ? (
                    <div className="alert alert-error" style={{ fontSize: 'var(--font-size-xs)' }}>
                      [{model.errorCode || 'DOWNLOAD_FAILED'}] {model.error}
                    </div>
                  ) : null}

                  <div className="model-actions">
                    {model.state === 'NOT_DOWNLOADED' ? (
                      <button
                        className="btn btn-primary btn-sm"
                        disabled={busy}
                        onClick={() => void runModelAction(model.id, () => downloadModel(model.id), `已开始下载 ${model.name}`)}
                        type="button"
                      >
                        {busy ? <span className="spinner" /> : <DownloadCloud size={15} />} 一键下载到本地
                      </button>
                    ) : null}

                    {model.state === 'DOWNLOADING' && !model.paused ? (
                      <button
                        className="btn btn-secondary btn-sm"
                        disabled={busy}
                        onClick={() => void runModelAction(model.id, () => pauseModel(model.id), '已暂停，断点已保留')}
                        type="button"
                      >
                        {busy ? <span className="spinner" /> : <Pause size={15} />} 暂停
                      </button>
                    ) : null}

                    {model.state === 'DOWNLOADING' && model.paused ? (
                      <button
                        className="btn btn-primary btn-sm"
                        disabled={busy}
                        onClick={() => void runModelAction(model.id, () => retryModel(model.id), '已继续下载（断点续传）')}
                        type="button"
                      >
                        {busy ? <span className="spinner" /> : <Play size={15} />} 继续下载
                      </button>
                    ) : null}

                    {model.state === 'DOWNLOADING' ? (
                      <>
                        <button
                          className="btn btn-secondary btn-sm"
                          disabled={busy}
                          onClick={() => void runModelAction(model.id, () => retryModel(model.id), '已重新开始下载（断点续传）')}
                          type="button"
                        >
                          <RefreshCw size={15} /> 重试
                        </button>
                        <button
                          className="btn btn-secondary btn-sm btn-danger"
                          disabled={busy}
                          onClick={() => void runModelAction(model.id, () => cancelModel(model.id), '已取消下载并清除断点文件')}
                          type="button"
                        >
                          <XCircle size={15} /> 取消
                        </button>
                      </>
                    ) : null}

                    {model.state === 'READY' && !model.loadedRuntime ? (
                      <>
                        <button
                          className="btn btn-primary btn-sm"
                          disabled={busy}
                          onClick={() =>
                            void runModelAction(
                              model.id,
                              async () => {
                                const result = await loadModel(model.id);
                                const runtimeKey = result.loadedRuntime || 'ollama';
                                await connectLocalRuntime({
                                  runtimeKey,
                                  model: result.runtimeModel,
                                  save: true,
                                });
                              },
                              '已装载并设为当前对话引擎',
                            )
                          }
                          type="button"
                        >
                          {busy ? <span className="spinner" /> : <Play size={15} />} 装载并启用为对话引擎
                        </button>
                        <button
                          className="btn btn-secondary btn-sm btn-danger"
                          disabled={busy}
                          onClick={() => void runModelAction(model.id, () => deleteModel(model.id), '已删除本地模型文件')}
                          type="button"
                        >
                          <Trash2 size={15} /> 删除
                        </button>
                      </>
                    ) : null}

                    {model.state === 'READY' && model.loadedRuntime ? (
                      <>
                        <button
                          className="btn btn-secondary btn-sm"
                          disabled={busy}
                          onClick={() => void runModelAction(model.id, () => unloadModel(model.id), '已卸载，释放内存')}
                          type="button"
                        >
                          {busy ? <span className="spinner" /> : <Activity size={15} />} 卸载
                        </button>
                        <button
                          className="btn btn-secondary btn-sm btn-danger"
                          disabled={busy}
                          onClick={() =>
                            void runModelAction(
                              model.id,
                              async () => {
                                await unloadModel(model.id);
                                await deleteModel(model.id);
                              },
                              '已卸载并删除本地模型文件',
                            )
                          }
                          type="button"
                        >
                          <Trash2 size={15} /> 删除
                        </button>
                        <span className="help-text">运行模型标识：{model.runtimeModel}</span>
                      </>
                    ) : null}

                    {model.state === 'LOADING' ? (
                      <span className="help-text">
                        <Loader2 size={13} /> 正在装载入内存（mmap），请稍候……
                      </span>
                    ) : null}

                    {model.state === 'ERROR' ? (
                      <>
                        {model.downloaded || model.fileOnDisk ? (
                          <button
                            className="btn btn-primary btn-sm"
                            disabled={busy}
                            onClick={() =>
                              void runModelAction(
                                model.id,
                                async () => {
                                  const result = await loadModel(model.id);
                                  await connectLocalRuntime({
                                    runtimeKey: result.loadedRuntime || 'ollama',
                                    model: result.runtimeModel,
                                    save: true,
                                  });
                                },
                                '已装载并设为当前对话引擎',
                              )
                            }
                            type="button"
                          >
                            {busy ? <span className="spinner" /> : <Play size={15} />} 重新装载并启用
                          </button>
                        ) : (
                          <button
                            className="btn btn-primary btn-sm"
                            disabled={busy}
                            onClick={() => void runModelAction(model.id, () => retryModel(model.id), '已重试（断点续传）')}
                            type="button"
                          >
                            {busy ? <span className="spinner" /> : <RefreshCw size={15} />} 重试下载
                          </button>
                        )}
                        <button
                          className="btn btn-secondary btn-sm btn-danger"
                          disabled={busy}
                          onClick={() => void runModelAction(model.id, () => deleteModel(model.id), '已删除本地模型文件')}
                          type="button"
                        >
                          <Trash2 size={15} /> 删除本地文件
                        </button>
                      </>
                    ) : null}

                    <button
                      className="btn btn-ghost btn-sm"
                      disabled={busy}
                      onClick={() => void refreshModelStatus()}
                      type="button"
                    >
                      查询状态
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      ) : null}

      {tab === 'providers' && saved.length > 0 ? (
        <div className="card mt-12">
          <div className="card-title">已保存的配置（{saved.length}）</div>
          <div className="saved-config-list">
            {saved.map((config) => (
              <div key={config.id} className={`saved-config${config.isActive ? ' active' : ''}`}>
                <div className="sc-main">
                  <div className="sc-name">
                    {config.displayName || config.providerName}{' '}
                    {config.isActive ? <Badge tone="accent">当前默认</Badge> : null}
                    {config.isLocal ? <Badge tone="info">本地部署</Badge> : null}
                  </div>
                  <div className="sc-meta">
                    {config.providerKey} · {config.baseUrl} · {config.model} · 密钥 {config.hasApiKey ? config.apiKeyMasked : '未配置'}
                  </div>
                </div>
                <div className="model-actions">
                  {!config.isActive ? (
                    <button
                      className="btn btn-secondary btn-sm"
                      onClick={async () => {
                        try {
                          await activateProviderConfig(config.id);
                          setBanner(`已切换为当前对话引擎：${config.displayName || config.providerName}`);
                          await refreshSaved();
                        } catch (thrown) {
                          setLoadError(errorMessage(thrown));
                        }
                      }}
                      type="button"
                    >
                      设为默认助教
                    </button>
                  ) : null}
                  <button
                    className="btn btn-secondary btn-sm btn-danger"
                    onClick={async () => {
                      try {
                        await deleteProviderConfig(config.id);
                        await refreshSaved();
                      } catch (thrown) {
                        setLoadError(errorMessage(thrown));
                      }
                    }}
                    type="button"
                  >
                    <Trash2 size={14} /> 删除
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      ) : null}
    </div>
  );
}
