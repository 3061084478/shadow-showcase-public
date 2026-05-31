import { useEffect, useMemo, useState } from 'react';
import { AnimatePresence, motion } from 'motion/react';
import { CheckCircle2, QrCode, RefreshCcw } from 'lucide-react';
import type { ConnectionStatus } from '../types';
import { StatusChip } from '../components/StatusChip';
import { pollQrSession, startLocalApi, startQrSession } from '../services/auth';

const loginBg = '/shadow-login-background.jpg';

function formatLoginError(error: unknown, fallback: string) {
  const message = error instanceof Error ? error.message : String(error || fallback);
  if (/failed to fetch/i.test(message)) return '无法连接本地服务，请确认后端已启动';
  if (/networkerror|load failed/i.test(message)) return '网络请求失败，请稍后重试';
  return message || fallback;
}

type LoginPageProps = {
  apiStatus: ConnectionStatus;
  cookieStatus: ConnectionStatus;
  accountStatus: 'not_connected' | 'connected';
  statusMessage: string;
  onAuthenticated: () => void;
  onReset: () => void;
  onStatusMessage: (message: string) => void;
  onRefreshStatus: () => void;
};

export function LoginPage({
  apiStatus,
  cookieStatus,
  accountStatus,
  statusMessage,
  onAuthenticated,
  onReset,
  onStatusMessage,
  onRefreshStatus,
}: LoginPageProps) {
  const [isStartingApi, setIsStartingApi] = useState(false);
  const [isCreatingQr, setIsCreatingQr] = useState(false);
  const [qrKey, setQrKey] = useState('');
  const [qrDataUrl, setQrDataUrl] = useState('');
  const [polling, setPolling] = useState(false);
  const [localError, setLocalError] = useState('');

  const containerVariants = useMemo(
    () => ({
      initial: { opacity: 0 },
      animate: {
        opacity: 1,
        transition: {
          staggerChildren: 0.15,
          delayChildren: 0.4,
        },
      },
    }),
    [],
  );

  const itemVariants = useMemo(
    () => ({
      initial: { opacity: 0, y: 15 },
      animate: {
        opacity: 1,
        y: 0,
        transition: { duration: 0.8, ease: [0.21, 0.47, 0.32, 0.98] as const },
      },
    }),
    [],
  );

  useEffect(() => {
    if (!qrKey || accountStatus === 'connected') {
      setPolling(false);
      return;
    }

    let cancelled = false;
    setPolling(true);

    const timer = window.setInterval(async () => {
      try {
        const payload = await pollQrSession(qrKey);
        if (cancelled) return;

        const message = payload.message || '等待扫码确认';
        onStatusMessage(message);

        if (payload.code === 803) {
          setPolling(false);
          onStatusMessage('登录成功，正在进入 SHADOW');
          onRefreshStatus();
          onAuthenticated();
        }
      } catch (error) {
        if (cancelled) return;
        setPolling(false);
        setLocalError(error instanceof Error ? error.message : '二维码轮询失败');
      }
    }, 1800);

    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [accountStatus, onAuthenticated, onRefreshStatus, onStatusMessage, qrKey]);

  const handleStartApi = async () => {
    try {
      setIsStartingApi(true);
      setLocalError('');
      onStatusMessage('正在启动本地 API');
      await startLocalApi();
      onStatusMessage('本地 API 已启动');
      onRefreshStatus();
      return true;
    } catch (error) {
      const message = formatLoginError(error, '启动本地 API 失败');
      setLocalError(message);
      onStatusMessage(message);
      return false;
    } finally {
      setIsStartingApi(false);
    }
  };

  const handleStartQr = async () => {
    try {
      setIsCreatingQr(true);
      setLocalError('');
      onStatusMessage('正在生成二维码');
      const session = await startQrSession();
      const url = session.qr_image || '';
      setQrKey(session.key);
      setQrDataUrl(url);
      onStatusMessage('请使用网易云音乐扫码登录');
      onRefreshStatus();
    } catch (error) {
      const message = formatLoginError(error, '生成二维码失败');
      setLocalError(message);
      onStatusMessage(message);
    } finally {
      setIsCreatingQr(false);
    }
  };

  const actionLabel = apiStatus !== 'ready' ? '启动 API 并获取二维码' : qrKey ? '重新生成二维码' : '开始二维码登录';
  const apiStatusLabel = isStartingApi ? '启动中' : apiStatus === 'ready' ? '已启动' : apiStatus === 'error' ? '启动失败' : '未启动';
  const cookieStatusLabel = isCreatingQr ? '检测中' : cookieStatus === 'ready' ? '已就绪' : cookieStatus === 'error' ? '检测失败' : '未检测';
  const accountStatusLabel = accountStatus === 'connected' ? '已连接' : polling ? '连接中' : '未连接';

  const handlePrimaryAction = async () => {
    if (apiStatus !== 'ready') {
      const started = await handleStartApi();
      if (!started) return;
    }
    await handleStartQr();
  };

  return (
    <div className="app-shell">
      <div className="stage-16x9 font-sans text-white">
        <img
          src={loginBg}
          alt=""
          className="bg-image select-none"
          onError={(event) => {
            event.currentTarget.style.display = 'none';
          }}
        />

        <div className="login-bg-overlay" />

        <div className="login-safe">
          <motion.div variants={containerVariants} initial="initial" animate="animate" className="absolute left-0 right-0 flex flex-col items-center pointer-events-none" style={{ top: '12%' }}>
            <motion.h1 variants={itemVariants} className="login-title uppercase text-center">
              SHADOW
            </motion.h1>
          </motion.div>

          <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 1, duration: 1, ease: 'easeOut' }} className="login-status-row absolute left-0 right-0 flex flex-wrap justify-center pointer-events-auto" style={{ top: '37%' }}>
            <StatusChip label="Local API" status={apiStatus} customLabel={apiStatusLabel} variant={isStartingApi ? 'progress' : 'idle'} />
            <StatusChip label="Cookie" status={cookieStatus} customLabel={cookieStatusLabel} variant={isCreatingQr ? 'progress' : 'idle'} />
            <StatusChip label="Account" status={accountStatus === 'connected' ? 'ready' : 'waiting'} customLabel={accountStatusLabel} variant={polling ? 'progress' : 'idle'} />
          </motion.div>

          <motion.div initial={{ opacity: 0, scale: 0.98, y: 20 }} animate={{ opacity: 1, scale: 1, y: 0 }} transition={{ delay: 1.2, duration: 1, ease: [0.21, 0.47, 0.32, 0.98] }} className="login-card absolute left-1/2 -translate-x-1/2 overflow-hidden pointer-events-auto" style={{ top: '47%' }}>
            <div className="flex flex-col items-center h-full">
              <div className="qr-box login-qr-box relative mt-2 flex items-center justify-center group overflow-hidden">
                <AnimatePresence mode="wait">
                  {qrDataUrl ? (
                    <motion.div key="qr-ready" initial={{ opacity: 0, scale: 0.92 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0, scale: 1.04 }} className="relative flex h-full w-full items-center justify-center">
                      <img src={qrDataUrl} alt="" className="h-[220px] w-[220px] object-contain" />
                      {polling && <motion.div animate={{ top: ['10%', '90%', '10%'] }} transition={{ repeat: Infinity, duration: 3, ease: 'easeInOut' }} className="absolute left-0 right-0 h-[1px] bg-white/20 shadow-[0_0_8px_white]" />}
                    </motion.div>
                  ) : accountStatus === 'connected' ? (
                    <motion.div key="success" initial={{ scale: 0.8, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} className="flex flex-col items-center gap-2 text-green-400">
                      <CheckCircle2 size={40} strokeWidth={1.5} />
                      <div className="text-center">
                        <p className="text-[10px] font-bold tracking-[0.1em] uppercase text-white/90">SHADOW 用户</p>
                      </div>
                    </motion.div>
                  ) : (
                    <motion.div key="placeholder" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="flex flex-col items-center gap-3 text-white/20">
                      <QrCode size={40} strokeWidth={0.5} />
                      <span className="text-[8px] uppercase tracking-[0.2em] font-medium text-center px-4">二维码就绪</span>
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>

              <div className="mt-5 min-h-[20px] text-center text-[11px] text-white/55">{statusMessage}</div>

              <div className="w-full flex flex-col gap-3.5 mt-6">
                <motion.button
                  whileHover={{ scale: 1.01 }}
                  whileTap={{ scale: 0.98 }}
                  onClick={() => void handlePrimaryAction()}
                  disabled={isStartingApi || isCreatingQr}
                  className="login-primary-button w-full"
                >
                  {isStartingApi ? '启动中...' : isCreatingQr ? '生成中...' : actionLabel}
                </motion.button>

                <button onClick={onReset} className="login-secondary-button flex w-full items-center justify-center gap-2">
                  <RefreshCcw size={10} className={isStartingApi || isCreatingQr ? 'animate-spin-slow' : ''} />
                  重新检测
                </button>
              </div>
            </div>
          </motion.div>
        </div>
      </div>
    </div>
  );
}
