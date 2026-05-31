import { Copy } from 'lucide-react';
import type { RelationExportPayload } from '../../types';
import type { SingleFriendProfileViewModel } from './relationViewModel';

type RelationshipSummaryCardProps = {
  viewModel: SingleFriendProfileViewModel;
  exporting: boolean;
  exportPayload: RelationExportPayload | null;
  exportMessage: string;
  onExport: () => void;
};

export function RelationshipSummaryCard({
  viewModel,
  exporting,
  exportPayload,
  exportMessage,
  onExport,
}: RelationshipSummaryCardProps) {
  const hasExport = Boolean(exportPayload);

  return (
    <section className="relation-ending-screen">
      <div className="relation-ending-copy">
        <div className="relation-eyebrow">Final Verdict</div>
        <h3 className="relation-screen-title">最终关系总结</h3>
        <div className="relation-final-title">{viewModel.finalTitle}</div>
        <div className="relation-final-copy">
          {viewModel.finalParagraphs.map((paragraph) => (
            <p key={paragraph}>{paragraph}</p>
          ))}
        </div>
      </div>

      <div className="relation-ending-export">
        <div className="relation-ending-export-line">如果你要继续把这段关系送进外部分析链路，导出入口留在这里，但不再占据页面主体。</div>
        <button className="relation-ending-export-button" onClick={onExport} disabled={exporting}>
          <Copy size={14} />
          {exporting ? '生成中...' : '生成分析三件套'}
        </button>
        {exportMessage ? <div className="relation-ending-export-status">{exportMessage}</div> : null}
        {hasExport ? <div className="relation-ending-export-hint">三件套已生成，本页不再直接展示终端式内容。</div> : null}
      </div>
    </section>
  );
}
