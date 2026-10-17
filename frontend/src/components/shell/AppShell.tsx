import { useEffect, useMemo } from 'react';
import { Outlet, useLocation } from 'react-router-dom';
import { useAudioSynth } from '../../hooks/useAudioSynth';
import { usePlayback } from '../../hooks/usePlayback';
import { PlaybackDock } from './PlaybackDock';
import { Sidebar } from './Sidebar';
import { TopHeader } from './TopHeader';

const PAGE_TITLES: Record<string, string> = {
  '/algorithms/page-replacement': '页面置换算法 (Page Replacement)',
  '/algorithms/banker': "银行家算法 (Banker's Algorithm)",
  '/algorithms/threads': '多线程同步互斥演示 (Producer-Consumer)',
  '/ai-assistant': 'AI 教学助教对话 (AI Assistant)',
  '/settings/engine': '模型引擎设置 (Model Engine Settings)',
  '/settings': '系统通用偏好设置 (Settings)',
};

/** 算法页面常驻吸底播放条；AI 对话 / 设置页自动折叠隐藏（设计文档 §2.2）。 */
const DOCK_ROUTES = ['/algorithms/page-replacement', '/algorithms/banker', '/algorithms/threads'];

export function AppShell() {
  const { pathname } = useLocation();
  const { trace } = usePlayback();
  const { unlock } = useAudioSynth();

  // 浏览器自动播放策略：首次用户手势后预热音频上下文
  useEffect(() => {
    const handler = () => unlock();
    window.addEventListener('pointerdown', handler, { once: true });
    window.addEventListener('keydown', handler, { once: true });
    return () => {
      window.removeEventListener('pointerdown', handler);
      window.removeEventListener('keydown', handler);
    };
  }, [unlock]);

  const title = useMemo(() => PAGE_TITLES[pathname] ?? 'os-visualizer 操作系统教学平台', [pathname]);
  const showDock = DOCK_ROUTES.includes(pathname) && trace != null && trace.totalSteps > 0;

  return (
    <div className="app-shell">
      <Sidebar pathname={pathname} />
      <div className="main-viewport">
        <TopHeader title={title} />
        <main className={`view-content${showDock ? ' with-dock' : ''}`}>
          <Outlet />
        </main>
        {showDock ? <PlaybackDock /> : null}
      </div>
    </div>
  );
}
