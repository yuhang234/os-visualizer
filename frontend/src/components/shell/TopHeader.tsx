import { useNavigate } from 'react-router-dom';
import { useAuth } from '../../hooks/useAuth';
import { AudioControls } from '../common/AudioControls';
import { ThemeToggle } from '../common/ThemeToggle';

/** 顶栏：当前页面标题 + 主题切换 + 音量 + 登录/用户状态（设计文档 §2.2）。 */
export function TopHeader({ title }: { title: string }) {
  const { user, isGuest } = useAuth();
  const navigate = useNavigate();

  return (
    <header className="top-header">
      <span className="breadcrumb-current">{title}</span>
      <span className="header-badge">
        {isGuest ? '游客模式 · 算法全开放' : `已登录 · ${user?.username}`}
      </span>
      <div className="header-actions">
        <ThemeToggle />
        <AudioControls />
        {isGuest ? (
          <button className="btn btn-primary btn-sm" onClick={() => navigate('/login')} type="button">
            登录账户
          </button>
        ) : (
          <span className="badge badge-success">{user?.displayName ?? user?.username}</span>
        )}
      </div>
    </header>
  );
}
