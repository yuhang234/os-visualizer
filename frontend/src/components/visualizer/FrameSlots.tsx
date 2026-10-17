import type { PageRepSnapshot } from '../../types/algorithm';

const STATUS_CLASS: Record<string, string> = {
  EMPTY: '',
  IDLE: '',
  HIT: 'hit',
  MISS: 'miss',
};

/** 物理页框堆叠槽位（设计文档 §5.3 FrameSlot / §5.4 深浅配色）。 */
export function FrameSlots({ snapshot }: { snapshot: PageRepSnapshot }) {
  const isClock = snapshot.algorithm === 'CLOCK';
  return (
    <div className="frames-area">
      {snapshot.frames.map((page, index) => {
        const status = snapshot.frameStatus[index] ?? 'EMPTY';
        const isEvicted = snapshot.evictedFrameIndex === index && snapshot.status === 'MISS';
        const className = `frame-slot ${STATUS_CLASS[status] ?? ''}${isEvicted ? ' evicted' : ''}${
          status === 'HIT' || status === 'MISS' ? ' anim-flash' : ''
        }`;
        return (
          <div className={className} key={index}>
            <span className="frame-index">页框 {index}</span>
            <span className="frame-page">{page == null ? '—' : page}</span>
            {isClock && snapshot.clockRefBits ? (
              <span className="frame-refbits" title="CLOCK 访问位">
                <span className={`refbit${snapshot.clockRefBits[index] ? ' on' : ''}`}>{snapshot.clockRefBits[index] ? 1 : 0}</span>
              </span>
            ) : null}
            <span className="frame-note">
              {page == null
                ? '空闲'
                : status === 'HIT'
                  ? '命中，无需置换'
                  : status === 'MISS'
                    ? isEvicted
                      ? `新载入！替换了页面 ${snapshot.evictedPage ?? '—'}`
                      : '新载入，占用空闲页框'
                    : `驻留时间: ${snapshot.residentTime[index]} 步`}
            </span>
          </div>
        );
      })}
    </div>
  );
}
