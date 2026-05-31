import type { ConnectionStatus } from '../types';

type StatusChipProps = {
  label: string;
  status: ConnectionStatus;
  customLabel?: string;
  variant?: 'idle' | 'progress';
};

export function StatusChip({ label, status, customLabel, variant = 'idle' }: StatusChipProps) {
  const getStatusText = () => {
    if (customLabel) return customLabel;
    switch (status) {
      case 'ready':
        return '已就绪';
      case 'waiting':
        return variant === 'progress' ? '检测中' : '未就绪';
      case 'error':
        return '错误';
    }
  };

  const translatedLabel = label === 'Account' ? '账号连接' : label === 'Cookie' ? '浏览器 Cookie' : label === 'Local API' ? '本地服务' : label;
  const toneClass = status === 'waiting' && variant === 'progress' ? 'status-chip--progress' : `status-chip--${status}`;

  return (
    <div className={`status-chip ${toneClass}`}>
      <div className="status-chip__dot" />
      <span>
        {translatedLabel} · {getStatusText()}
      </span>
    </div>
  );
}
