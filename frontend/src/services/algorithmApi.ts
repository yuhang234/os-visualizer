/** 算法计算接口（设计文档 §13.2 第 2/3/4 项）。 */

import { postJson, requestData, requestRaw } from './client';
import type {
  BankerRequestPayload,
  BankerRequestResult,
  BankerSafetyResult,
  PageRepTrace,
  PageReplacementRequest,
  ThreadsRequest,
  ThreadsTrace,
} from '../types/algorithm';

/** 页面置换：直接返回 ExecutionTrace（无信封）。 */
export function simulatePageReplacement(payload: PageReplacementRequest): Promise<PageRepTrace> {
  return requestRaw<PageRepTrace>('/algorithms/page-replacement/simulate', postJson(payload));
}

/** 银行家安全性检查：`{code,data:{isSafe,safeSequence,steps,trace,state}}`。 */
export function checkBankerSafety(payload: {
  available: number[];
  maxMatrix: number[][];
  allocationMatrix: number[][];
}): Promise<BankerSafetyResult> {
  return requestData<BankerSafetyResult>('/algorithms/banker/check-safety', postJson(payload));
}

/** 银行家资源请求判定。 */
export function requestBankerResource(payload: BankerRequestPayload): Promise<BankerRequestResult> {
  return requestData<BankerRequestResult>('/algorithms/banker/request-resource', postJson(payload));
}

/** 多线程生产者-消费者模拟：直接返回 ExecutionTrace（无信封）。 */
export function simulateThreads(payload: ThreadsRequest): Promise<ThreadsTrace> {
  return requestRaw<ThreadsTrace>('/algorithms/threads/simulate', postJson(payload));
}

/* ------------------------------ 案例持久化（登录用户） ------------------------------ */

export interface ScenarioRecord {
  id: number;
  kind: string;
  name: string;
  payload: Record<string, unknown>;
  updatedAt: string;
}

export function listScenarios(kind?: string): Promise<ScenarioRecord[]> {
  const query = kind ? `?kind=${encodeURIComponent(kind)}` : '';
  return requestData<ScenarioRecord[]>(`/algorithms/scenarios${query}`);
}

export function saveScenario(kind: string, name: string, payload: Record<string, unknown>): Promise<ScenarioRecord> {
  return requestData<ScenarioRecord>('/algorithms/scenarios', postJson({ kind, name, payload }));
}

export function deleteScenario(id: number): Promise<{ deleted: boolean }> {
  return requestData<{ deleted: boolean }>(`/algorithms/scenarios/${id}`, { method: 'DELETE' });
}
