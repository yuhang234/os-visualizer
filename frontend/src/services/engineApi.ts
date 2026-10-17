/** 模型引擎接口：目录、配置 CRUD、Ping、本地探测、内置小模型下载（设计文档 §9 / §10 / §13.2）。 */

import { getJson, postJson, putJson, requestData } from './client';
import type {
  BuiltinModelMeta,
  EngineCatalog,
  LocalConnectResult,
  LocalDetectResult,
  ModelDiskUsage,
  ModelStatus,
  PingPayload,
  PingResult,
  ProviderConfigPayload,
  SavedProviderConfig,
} from '../types/ai_engine';

export function fetchEngineCatalog(): Promise<EngineCatalog> {
  return requestData<EngineCatalog>('/ai/engine/catalog', getJson());
}

export function listProviderConfigs(): Promise<SavedProviderConfig[]> {
  return requestData<SavedProviderConfig[]>('/ai/engine/providers', getJson());
}

export function saveProviderConfig(payload: ProviderConfigPayload): Promise<SavedProviderConfig> {
  return requestData<SavedProviderConfig>('/ai/engine/providers', putJson(payload));
}

export function activateProviderConfig(id: number): Promise<SavedProviderConfig> {
  return requestData<SavedProviderConfig>(`/ai/engine/providers/${id}/activate`, postJson({}));
}

export function deleteProviderConfig(id: number): Promise<{ deleted: boolean }> {
  return requestData<{ deleted: boolean }>(`/ai/engine/providers/${id}`, { method: 'DELETE' });
}

export function pingEngine(payload: PingPayload): Promise<PingResult> {
  return requestData<PingResult>('/ai/engine/ping', postJson(payload));
}

export function detectLocalRuntimes(): Promise<LocalDetectResult> {
  return requestData<LocalDetectResult>('/ai/engine/local/detect', getJson());
}

export function connectLocalRuntime(payload: {
  runtimeKey: string;
  host?: string;
  port?: number | null;
  model?: string;
  save?: boolean;
}): Promise<LocalConnectResult> {
  return requestData<LocalConnectResult>('/ai/engine/local/connect', postJson(payload));
}

/* ------------------------------ 内置小模型 ------------------------------ */

export interface ModelCatalogPayload {
  models: BuiltinModelMeta[];
  totalBytes: number;
  states: string[];
  modelsDirLabel: string;
}

export function fetchModelCatalog(): Promise<ModelCatalogPayload> {
  return requestData<ModelCatalogPayload>('/ai/engine/models/catalog', getJson());
}

export function fetchModelStatus(): Promise<{ models: ModelStatus[]; disk: ModelDiskUsage }> {
  return requestData<{ models: ModelStatus[]; disk: ModelDiskUsage }>('/ai/engine/models/status', getJson());
}

export function fetchModelDisk(): Promise<ModelDiskUsage> {
  return requestData<ModelDiskUsage>('/ai/engine/models/disk', getJson());
}

export function downloadModel(modelId: string, sourceUrl?: string): Promise<ModelStatus> {
  return requestData<ModelStatus>('/ai/engine/models/download', postJson({ modelId, sourceUrl }));
}

export function pauseModel(modelId: string): Promise<ModelStatus> {
  return requestData<ModelStatus>('/ai/engine/models/pause', postJson({ modelId }));
}

export function cancelModel(modelId: string): Promise<ModelStatus> {
  return requestData<ModelStatus>('/ai/engine/models/cancel', postJson({ modelId }));
}

export function retryModel(modelId: string): Promise<ModelStatus> {
  return requestData<ModelStatus>('/ai/engine/models/retry', postJson({ modelId }));
}

export function deleteModel(modelId: string): Promise<ModelStatus> {
  return requestData<ModelStatus>('/ai/engine/models/delete', postJson({ modelId }));
}

export function loadModel(modelId: string): Promise<ModelStatus & { loadedRuntime?: string; runtimeModel?: string }> {
  return requestData<ModelStatus & { loadedRuntime?: string; runtimeModel?: string }>(
    '/ai/engine/models/load',
    postJson({ modelId }),
  );
}

export function unloadModel(modelId: string): Promise<ModelStatus> {
  return requestData<ModelStatus>('/ai/engine/models/unload', postJson({ modelId }));
}
