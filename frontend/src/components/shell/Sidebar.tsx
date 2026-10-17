import { Activity, Bot, Cpu, Layers, LogOut, Settings, Table, User } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../../hooks/useAuth';

const NAV_SECTIONS: {
  title: string;
  items: { to: string; label: string; icon: typeof Layers }[];
}[] = [
  {
    title: '算法仿真实验',
    items: [
      { to: '/algorithms/page-replacement', label: '页面置换算法', icon: Layers },
      { to: '/algorithms/banker', label: '银行家算法', icon: Table },
      { to: '/algorithms/threads', label: '多线程并发演示', icon: Activity },
    ],
  },
  {
    title: 'AI 助教与引擎设置',
    items: [
      { to: '/ai-assistant', label: 'AI 助教对话', icon: Bot },
      { to: '/settings/engine', label: '模型引擎设置', icon: Cpu },
      { to: '/settings', label: '系统通用设置', icon: Settings },
    ],
  },
];

export function Sidebar({ pathname, onNavigate }: { pathname: string; onNavigate?: () => void }) {
  const navigate = useNavigate();
  const { user, isGuest, logout } = useAuth();

  const go = (to: string) => {
    navigate(to);
    onNavigate?.();
  };

  return (
    <aside className="sidebar">
      <div className="sidebar-brand" onClick={() => go('/algorithms/page-replacement')} style={{ cursor: 'pointer' }}>
        <span className="brand-logo">OS</span>
        <span>
          <div className="brand-title">OS Visualizer</div>
          <div className="brand-subtitle">操作系统核心原理教学平台</div>
        </span>
      </div>

      <nav className="sidebar-nav">
        {NAV_SECTIONS.map((section) => (
          <div key={section.title}>
            <div className="nav-section-title">{section.title}</div>
            {section.items.map((item) => {
              const active = pathname === item.to || pathname.startsWith(`${item.to}/`);
              const Icon = item.icon;
              return (
                <div
                  key={item.to}
                  className={`nav-item${active ? ' active' : ''}`}
                  onClick={() => go(item.to)}
                  role="button"
                  tabIndex={0}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter') go(item.to);
                  }}
                >
                  <span className="nav-icon">
                    <Icon size={17} />
                  </span>
                  {item.label}
                </div>
              );
            })}
          </div>
        ))}
      </nav>

      <div className="sidebar-footer">
        <div className="user-card">
          <span className="user-avatar">{isGuest ? <User size={16} /> : (user?.displayName ?? user?.username ?? 'U').slice(0, 1).toUpperCase()}</span>
          <div className="user-meta">
            <div className="user-name">{isGuest ? '游客体验中' : user?.displayName ?? user?.username}</div>
            <div className="user-role">{isGuest ? '点击登录，云端保存案例' : `@${user?.username}`}</div>
          </div>
          {isGuest ? (
            <button className="btn btn-primary btn-sm" onClick={() => go('/login')} type="button">
              登录
            </button>
          ) : (
            <button
              className="icon-btn"
              title="登出"
              type="button"
              onClick={() => {
                void logout();
              }}
            >
              <LogOut size={15} />
            </button>
          )}
        </div>
      </div>
    </aside>
  );
}
