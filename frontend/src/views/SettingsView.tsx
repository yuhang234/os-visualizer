/**
 * 系统通用偏好设置页（设计文档 §2.2 / §3.4 / §12）。
 * 主题三态控制器（深色 / 浅色 / 跟随系统，持久化于 localStorage）、
 * 音效开关与音量、本地缓存清理、账号信息与后端健康状态。
 */

import { useCallback, useEffect, useState } from 'react';
import { LogIn, LogOut, Moon, Monitor, Sun, Trash2, Volume2 } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { useTheme, type ThemeMode } from '../hooks/useTheme';
import { useAudioSynth } from '../hooks/useAudioSynth';
import { useAuth } from '../hooks/useAuth';
import { fetchHealth } from '../services/authApi';
import { errorMessage } from '../services/client';
import { Badge } from '../components/common/Badge';
import type { HealthInfo } from '../types/auth';

const THEME_OPTIONS: { mode: ThemeMode; label: string; hint: string; icon: typeof Moon }[] = [
  { mode: 'dark', label: '🌙 深色模式 (Dark)', hint: '默认：适合长时间实验与演示投影', icon: Moon },
  { mode: 'light', label: '☀️ 浅色模式 (Light)', hint: '明亮环境高对比度，网格配色已专属适配', icon: Sun },
  { mode: 'system', label: '💻 跟随系统 (System)', hint: '跟随操作系统外观自动切换', icon: Monitor },
];

export function SettingsView() {
  const { mode, setMode, resolved } = useTheme();
  const { muted, volume, setMuted, setVolume, testTone } = useAudioSynth();
  const { user, isGuest, logout } = useAuth();
  const navigate = useNavigate();

  const [health, setHealth] = useState<HealthInfo | null>(null);
  const [healthError, setHealthError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    let disposed = false;
    fetchHealth()
      .then((result) => {
        if (!disposed) {
          setHealth(result);
          setHealthError(null);
        }
      })
      .catch((thrown) => {
        if (!disposed) setHealthError(errorMessage(thrown));
      });
    return () => {
      disposed = true;
    };
  }, []);

  const clearCache = useCallback(() => {
    const keys: string[] = [];
    try {
      for (let index = 0; index < localStorage.length; index += 1) {
        const key = localStorage.key(index);
        if (key && (key.startsWith('osvis_') || key === 'os_theme')) keys.push(key);
      }
      // 保留身份类键：登录令牌 osvis_token / osvis_user，以及游客实例标识 osvis_guest_id
      // （游客每日对话额度按 浏览器实例 + IP 计数，清缓存不应等于重置额度）。
      for (const key of keys) {
        if (key === 'osvis_token' || key === 'osvis_user' || key === 'osvis_guest_id') continue;
        localStorage.removeItem(key);
      }
    } catch {
      /* ignore */
    }
    setMessage('本地缓存已清空（主题、播放速度、音量与对话设置已重置；登录状态与游客标识保留）。');
  }, []);

  return (
    <div className="settings-wrap">
      <div className="page-head">
        <span className="page-title">系统通用偏好设置</span>
        <div className="page-actions">
          <Badge tone="info">当前解析主题：{resolved === 'dark' ? '深色' : '浅色'}</Badge>
        </div>
      </div>

      {message ? (
        <div className="alert alert-success mb-12" onClick={() => setMessage(null)} role="presentation">
          {message}
        </div>
      ) : null}

      <div className="card settings-section">
        <div className="card-title">外观主题模式 (Theme Mode)</div>
        <div className="theme-options">
          {THEME_OPTIONS.map((option) => {
            const Icon = option.icon;
            return (
              <label key={option.mode} className={`radio-card${mode === option.mode ? ' selected' : ''}`}>
                <input
                  type="radio"
                  name="setting-theme"
                  value={option.mode}
                  checked={mode === option.mode}
                  onChange={() => setMode(option.mode)}
                />
                <span className="row-inline">
                  <Icon size={16} />
                  <strong>{option.label}</strong>
                </span>
                <span className="help-text">{option.hint}</span>
              </label>
            );
          })}
        </div>
        <div className="help-text mt-12">
          主题令牌一一对应（深色 / 浅色同名令牌），切换时整站含算法网格、矩阵表格、日志控制台一起翻转并持久化。
        </div>
      </div>

      <div className="card settings-section">
        <div className="card-title">Web Audio 算法音效</div>
        <div className="flex-between">
          <div>
            <label className="row-inline" style={{ cursor: 'pointer' }}>
              <span className="switch">
                <input type="checkbox" checked={!muted} onChange={(event) => setMuted(!event.target.checked)} />
              </span>
              <span>{muted ? '音效已静音' : '音效已开启'}</span>
            </label>
            <div className="help-text">
              原生振荡器程序化实时合成，零网络延迟与零资源依赖；命中 / 缺页 / 阻塞 / 唤醒等事件映射不同音色。
            </div>
          </div>
          <div className="row-inline" style={{ minWidth: 260 }}>
            <Volume2 size={16} />
            <input
              className="volume-slider"
              type="range"
              min={0}
              max={1}
              step={0.05}
              value={volume}
              onChange={(event) => setVolume(Number(event.target.value))}
              title="全局音量"
            />
            <span className="mono-xs">{Math.round(volume * 100)}%</span>
            <button className="btn btn-secondary btn-sm" onClick={testTone} type="button">
              试听音效
            </button>
          </div>
        </div>
      </div>

      <div className="card settings-section">
        <div className="card-title">本地缓存与预设</div>
        <div className="flex-between">
          <div className="help-text">
            清理浏览器本地存储中的播放速度、音量、主题与「附带算法快照」等偏好；账号令牌与后端数据库不受影响。
          </div>
          <button className="btn btn-secondary btn-sm btn-danger" onClick={clearCache} type="button">
            <Trash2 size={15} /> 清理本地全部缓存数据
          </button>
        </div>
      </div>

      <div className="card settings-section">
        <div className="card-title">账号</div>
        {isGuest ? (
          <div className="flex-between">
            <div className="help-text">
              当前为游客模式：算法仿真与内置演示后端全部可用；使用服务器默认密钥的 AI 对话受每日限额约束。
            </div>
            <button className="btn btn-primary btn-sm" onClick={() => navigate('/login')} type="button">
              <LogIn size={15} /> 登录 / 注册账户
            </button>
          </div>
        ) : (
          <div className="flex-between">
            <div>
              <div>
                <strong>{user?.displayName ?? user?.username}</strong>
                <span className="help-text"> @{user?.username} · 用户 ID {user?.id}</span>
              </div>
              <div className="help-text">登录账号的引擎配置与对话历史保存在后端 SQLite，可跨终端漫游。</div>
            </div>
            <button
              className="btn btn-secondary btn-sm"
              onClick={() => {
                void logout().then(() => setMessage('已登出，当前降级为游客模式。'));
              }}
              type="button"
            >
              <LogOut size={15} /> 退出登录
            </button>
          </div>
        )}
      </div>

      <div className="card settings-section mb-16">
        <div className="card-title">后端服务状态</div>
        {health ? (
          <dl className="kv-list">
            <dt>服务状态</dt>
            <dd>
              <Badge tone="success">{health.status}</Badge>
            </dd>
            <dt>应用标识</dt>
            <dd>{health.app}</dd>
            <dt>数据目录（相对后端）</dt>
            <dd>{health.dataDirLabel}</dd>
            <dt>模型缓存目录（相对后端）</dt>
            <dd>{health.modelsDirLabel}</dd>
            <dt>游客每日对话限额</dt>
            <dd>{health.guestDailyChatLimit} 次</dd>
          </dl>
        ) : (
          <div className="alert alert-warning">{healthError ? `健康检查失败：${healthError}` : '正在检测后端服务……'}</div>
        )}
      </div>
    </div>
  );
}
