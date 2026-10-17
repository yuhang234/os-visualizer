import { Moon, Sun } from 'lucide-react';
import { useAudioSynth } from '../../hooks/useAudioSynth';
import { useTheme } from '../../hooks/useTheme';

/** 顶栏常驻主题快捷开关（设计文档 §3.4），切换时伴随微弱咔哒触觉声。 */
export function ThemeToggle() {
  const { resolved, toggle } = useTheme();
  const { playTone, muted } = useAudioSynth();

  const handleClick = () => {
    toggle();
    if (!muted) playTone('TONE_STEP');
  };

  return (
    <button className="icon-btn" onClick={handleClick} title="切换浅色 / 深色模式 (T)" type="button">
      {resolved === 'dark' ? <Moon size={16} /> : <Sun size={16} />}
      <span className="nowrap">{resolved === 'dark' ? '深色' : '浅色'}</span>
    </button>
  );
}
