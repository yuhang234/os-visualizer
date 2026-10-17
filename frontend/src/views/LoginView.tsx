/**
 * 用户登录 / 注册页（设计文档 §11.3 线框图）。
 * - 登录与注册双 Tab，用户名 ≥3 位、密码 ≥6 位的本地校验与后端校验一致
 * - 游客模式一键体验（无需账号），登录成功回到上一个页面
 */

import { useState } from 'react';
import { LogIn, Rocket, UserPlus, Zap } from 'lucide-react';
import { useLocation, useNavigate } from 'react-router-dom';
import { useAuth } from '../hooks/useAuth';
import { PasswordField } from '../components/common/PasswordField';
import { errorMessage } from '../services/client';

type Mode = 'login' | 'register';

export function LoginView() {
  const { login, register } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [mode, setMode] = useState<Mode>('login');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [displayName, setDisplayName] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const redirectTo = (() => {
    const state = location.state as { from?: string } | null;
    return state?.from && state.from !== '/login' ? state.from : '/algorithms/page-replacement';
  })();

  const validate = (): string | null => {
    if (username.trim().length < 3) return '用户名长度不少于 3 个字符';
    if (password.length < 6) return '密码不少于 6 位';
    if (mode === 'register' && displayName.trim().length > 32) return '显示名称不能超过 32 个字符';
    return null;
  };

  const handleSubmit = async () => {
    const invalid = validate();
    if (invalid) {
      setError(invalid);
      return;
    }
    setBusy(true);
    setError(null);
    try {
      if (mode === 'login') {
        await login(username.trim(), password);
      } else {
        await register(username.trim(), password, displayName.trim() || undefined);
      }
      navigate(redirectTo, { replace: true });
    } catch (thrown) {
      setError(errorMessage(thrown));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="login-view">
      <div className="login-card">
        <div className="login-brand">
          <h1>OS Visualizer 操作系统教学平台</h1>
          <p>理解核心原理，掌控计算机内核底层 · 双主题 · 多模型 AI 助教</p>
        </div>

        <div className="login-tabs">
          <button className={`login-tab${mode === 'login' ? ' active' : ''}`} onClick={() => setMode('login')} type="button">
            登录 (Sign In)
          </button>
          <button
            className={`login-tab${mode === 'register' ? ' active' : ''}`}
            onClick={() => setMode('register')}
            type="button"
          >
            注册 (Register)
          </button>
        </div>

        <div className="flex-col">
          <label className="field">
            <span className="field-label">用户名 / 学号</span>
            <input
              className="input-field"
              value={username}
              placeholder="student_os"
              autoComplete="username"
              onChange={(event) => setUsername(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'Enter') void handleSubmit();
              }}
            />
          </label>

          {mode === 'register' ? (
            <label className="field">
              <span className="field-label">显示名称（可选）</span>
              <input
                className="input-field"
                value={displayName}
                placeholder="例如：操作系统 2026 级 张三"
                onChange={(event) => setDisplayName(event.target.value)}
              />
            </label>
          ) : null}

          <PasswordField
            label="登录密码"
            value={password}
            onChange={setPassword}
            placeholder="不少于 6 位"
            autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
          />

          <div className="help-text">
            [!] 用户名长度不少于 3 个字符，密码不少于 6 位；密码经 PBKDF2 加盐哈希存储，不保存明文。
          </div>

          {error ? <div className="alert alert-error">{error}</div> : null}

          <button className="btn btn-primary btn-block" onClick={() => void handleSubmit()} disabled={busy} type="button">
            {busy ? <span className="spinner" /> : mode === 'login' ? <LogIn size={16} /> : <UserPlus size={16} />}
            {busy ? '处理中…' : mode === 'login' ? '🚀 立即登录' : '🚀 注册并登录'}
          </button>
        </div>

        <div className="divider-text">或者是课堂演示 / 临时体验？</div>

        <button className="btn btn-secondary btn-block" onClick={() => navigate('/algorithms/page-replacement')} type="button">
          <Zap size={16} /> ⚡ 以游客身份快速体验 (无需账号)
        </button>

        <div className="login-foot">
          <Rocket size={12} /> 游客模式算法仿真全开放；使用服务器默认密钥的 AI 对话受每日限额约束，登录后解除。
        </div>
      </div>
    </div>
  );
}
