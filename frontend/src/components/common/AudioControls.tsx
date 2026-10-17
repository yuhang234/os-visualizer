import { Volume2, VolumeX } from 'lucide-react';
import { useAudioSynth } from '../../hooks/useAudioSynth';

/** 顶栏音量控制：静音开关 + 音量滑条 + 试听（设计文档 §2.2 / §12）。 */
export function AudioControls() {
  const { muted, volume, setMuted, setVolume, testTone } = useAudioSynth();
  return (
    <>
      <button
        className="icon-btn"
        onClick={() => {
          const next = !muted;
          setMuted(next);
          if (!next) testTone();
        }}
        title="一键静音 / 开启音效"
        type="button"
      >
        {muted ? <VolumeX size={16} /> : <Volume2 size={16} />}
      </button>
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
      <button className="btn btn-secondary btn-sm" onClick={testTone} title="试听音效" type="button">
        试听
      </button>
    </>
  );
}
