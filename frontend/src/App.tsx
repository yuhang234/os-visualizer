/**
 * 路由装配（设计文档 §2.1 页面清单）。
 * 全局 Provider：主题 → 鉴权 → 音效 → 回放引擎；登录页独立于外壳布局之外。
 */

import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import { ThemeProvider } from './hooks/useTheme';
import { AuthProvider } from './hooks/useAuth';
import { AudioProvider } from './hooks/useAudioSynth';
import { PlaybackProvider } from './hooks/usePlayback';
import { AppShell } from './components/shell/AppShell';
import { PageRepView } from './views/PageRepView';
import { BankerView } from './views/BankerView';
import { ThreadsView } from './views/ThreadsView';
import { AiChatView } from './views/AiChatView';
import { EngineSettingsView } from './views/EngineSettingsView';
import { SettingsView } from './views/SettingsView';
import { LoginView } from './views/LoginView';

export function App() {
  return (
    <ThemeProvider>
      <AuthProvider>
        <AudioProvider>
          <PlaybackProvider>
            <BrowserRouter>
              <Routes>
                <Route path="/login" element={<LoginView />} />
                <Route element={<AppShell />}>
                  <Route path="/algorithms/page-replacement" element={<PageRepView />} />
                  <Route path="/algorithms/banker" element={<BankerView />} />
                  <Route path="/algorithms/threads" element={<ThreadsView />} />
                  <Route path="/ai-assistant" element={<AiChatView />} />
                  <Route path="/settings/engine" element={<EngineSettingsView />} />
                  <Route path="/settings" element={<SettingsView />} />
                </Route>
                <Route path="/" element={<Navigate to="/algorithms/page-replacement" replace />} />
                <Route path="*" element={<Navigate to="/algorithms/page-replacement" replace />} />
              </Routes>
            </BrowserRouter>
          </PlaybackProvider>
        </AudioProvider>
      </AuthProvider>
    </ThemeProvider>
  );
}
