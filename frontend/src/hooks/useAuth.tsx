/**
 * 鉴权 Hook（设计文档 §11）：JWT 存 localStorage，游客模式零门槛。
 * - 启动时若存在 token 则向后端 /auth/me 校验；失效自动降级为游客
 * - 登录/注册/登出一并维护 localStorage 中的用户快照
 */

import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import { STORAGE_KEYS, setToken } from '../services/client';
import * as authApi from '../services/authApi';
import type { UserInfo } from '../types/auth';

interface AuthContextValue {
  user: UserInfo | null;
  isGuest: boolean;
  ready: boolean;
  login: (username: string, password: string) => Promise<UserInfo>;
  register: (username: string, password: string, displayName?: string) => Promise<UserInfo>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

function readCachedUser(): UserInfo | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEYS.user);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as UserInfo;
    if (parsed && typeof parsed.username === 'string') return parsed;
  } catch {
    /* ignore */
  }
  return null;
}

function cacheUser(user: UserInfo | null): void {
  try {
    if (user) {
      localStorage.setItem(STORAGE_KEYS.user, JSON.stringify(user));
    } else {
      localStorage.removeItem(STORAGE_KEYS.user);
    }
  } catch {
    /* ignore */
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<UserInfo | null>(() => readCachedUser());
  const [ready, setReady] = useState(false);

  useEffect(() => {
    let disposed = false;
    const bootstrap = async () => {
      const token = (() => {
        try {
          return localStorage.getItem(STORAGE_KEYS.token);
        } catch {
          return null;
        }
      })();
      if (!token) {
        setUser(null);
        setReady(true);
        return;
      }
      try {
        const me = await authApi.fetchMe();
        if (disposed) return;
        setUser(me);
        cacheUser(me);
      } catch {
        if (disposed) return;
        // token 失效：清除并回到游客模式
        setToken(null);
        cacheUser(null);
        setUser(null);
      } finally {
        if (!disposed) setReady(true);
      }
    };
    void bootstrap();
    return () => {
      disposed = true;
    };
  }, []);

  const applyLogin = useCallback((result: { accessToken: string; user: UserInfo }) => {
    setToken(result.accessToken);
    cacheUser(result.user);
    setUser(result.user);
    return result.user;
  }, []);

  const login = useCallback(
    async (username: string, password: string) => applyLogin(await authApi.login(username, password)),
    [applyLogin],
  );

  const register = useCallback(
    async (username: string, password: string, displayName?: string) =>
      applyLogin(await authApi.register(username, password, displayName)),
    [applyLogin],
  );

  const logout = useCallback(async () => {
    try {
      await authApi.logout();
    } catch {
      /* 服务端登出失败不影响本地清理 */
    }
    setToken(null);
    cacheUser(null);
    setUser(null);
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({ user, isGuest: user == null, ready, login, register, logout }),
    [user, ready, login, register, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth 必须在 <AuthProvider> 内使用');
  }
  return context;
}
