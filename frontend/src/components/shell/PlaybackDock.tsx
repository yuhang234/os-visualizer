import { ChevronFirst, ChevronLast, Pause, Play, SkipBack, SkipForward, Volume2, VolumeX } from 'lucide-react';
import { useAudioSynth } from '../../hooks/useAudioSynth';
import { usePlayback } from '../../hooks/usePlayback';
import { PLAYBACK_SPEEDS, type PlaybackSpeed } from '../../types/algorithm';

const STATUS_TEXT: Record<string, string> = {
  IDLE: '待机',
  LOADING: '计算中',
  READY: '就绪',
  PLAYING: '自动播放中',
  FINISHED: '已到末步',
};

/** 底部全局时间旅行播放控制条（设计文档 §2.2 / §4.3）。 */
export function PlaybackDock() {
  const { trace, index, totalSteps, status, speed, setSpeed, goto, next, prev, first, last, toggle } = usePlayback();
  const { muted, setMuted } = useAudioSynth();

  const disabled = !trace || totalSteps === 0;
  const lastIndex = Math.max(0, totalSteps - 1);

  return (
    <footer className="playback-dock" id="global-playback-dock">
      <div className="dock-group">
        <button className="dock-btn" onClick={first} disabled={disabled || index === 0} title="跳至起始步骤 (Home)" type="button">
          <ChevronFirst size={18} />
        </button>
        <button className="dock-btn" onClick={prev} disabled={disabled || index === 0} title="单步后退 (←)" type="button">
          <SkipBack size={18} />
        </button>
        <button
          className="dock-btn dock-btn-main"
          onClick={toggle}
          disabled={disabled || totalSteps <= 1}
          title={status === 'PLAYING' ? '暂停自动播放 (Space)' : '自动播放 (Space)'}
          type="button"
        >
          {status === 'PLAYING' ? <Pause size={20} /> : <Play size={20} />}
        </button>
        <button className="dock-btn" onClick={next} disabled={disabled || index >= lastIndex} title="单步前进 (→)" type="button">
          <SkipForward size={18} />
        </button>
        <button
          className="dock-btn"
          onClick={last}
          disabled={disabled || index >= lastIndex}
          title="跳至最终步骤 (End)"
          type="button"
        >
          <ChevronLast size={18} />
        </button>
      </div>

      <span className="step-counter">
        步骤 {disabled ? 0 : index + 1} / {totalSteps}
      </span>

      <input
        className="timeline-slider"
        type="range"
        min={0}
        max={lastIndex}
        value={Math.min(index, lastIndex)}
        disabled={disabled}
        onChange={(event) => goto(Number(event.target.value))}
        title="拖动直达任意步骤"
      />

      <span className="dock-status">{STATUS_TEXT[status] ?? status}</span>

      <div className="dock-sep" />

      <select
        className="input-field input-inline"
        style={{ padding: '4px 8px', fontSize: 'var(--font-size-xs)' }}
        value={speed}
        onChange={(event) => setSpeed(Number(event.target.value) as PlaybackSpeed)}
        title="播放速度档位 (- / = 加减速)"
      >
        {PLAYBACK_SPEEDS.map((item) => (
          <option key={item} value={item}>
            {item.toFixed(1)}x
          </option>
        ))}
      </select>

      <button className="dock-btn" onClick={() => setMuted(!muted)} title="音效开关" type="button">
        {muted ? <VolumeX size={16} /> : <Volume2 size={16} />}
      </button>
    </footer>
  );
}
