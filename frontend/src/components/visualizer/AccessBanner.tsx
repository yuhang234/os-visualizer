import { useEffect, useRef } from 'react';

/** 参考串时序横幅：已访置灰、当前高亮、待访弱化（设计文档 §5.2 / §5.4）。 */
export function AccessBanner({ referenceString, accessedCount }: { referenceString: number[]; accessedCount: number }) {
  const currentRef = useRef<HTMLSpanElement | null>(null);

  useEffect(() => {
    currentRef.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest', inline: 'center' });
  }, [accessedCount]);

  return (
    <div className="access-banner">
      {referenceString.map((page, index) => {
        const isCurrent = index === accessedCount - 1 && accessedCount > 0;
        const visited = index < accessedCount;
        const className = `access-tag${isCurrent ? ' current' : visited ? ' visited' : ''}`;
        return (
          <span className={className} key={`${index}-${page}`} ref={isCurrent ? currentRef : undefined}>
            <span className="tag-index">{index + 1}</span>
            {page}
          </span>
        );
      })}
    </div>
  );
}
