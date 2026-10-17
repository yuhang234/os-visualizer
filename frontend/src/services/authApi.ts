/** 鉴权接口（设计文档 §13.2 第 1 项）。注册成功返回 201。 */

import { getJson, postJson, requestData } from './client';
import type { HealthInfo, LoginResult, UserInfo } from '../types/auth';

export function register(username: string, password: string, displayName?: string): Promise<LoginResult> {
  return requestData<LoginResult>('/auth/register', postJson({ username, password, displayName }));
}

export function login(username: string, password: string): Promise<LoginResult> {
  return requestData<LoginResult>('/auth/login', postJson({ username, password }));
}

export function fetchMe(): Promise<UserInfo> {
  return requestData<UserInfo>('/auth/me', getJson());
}

export function logout(): Promise<{ loggedOut: boolean }> {
  return requestData<{ loggedOut: boolean }>('/auth/logout', postJson({}));
}

export function fetchHealth(): Promise<HealthInfo> {
  return requestData<HealthInfo>('/health', getJson());
}
