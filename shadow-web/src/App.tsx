import { useEffect, useState } from 'react';
import { HomePage } from './pages/HomePage';
import { LoginPage } from './pages/LoginPage';
import type { AuthState, ConnectionStatus } from './types';
import { fetchAuthStatus } from './services/auth';

function formatAuthStatusError(error: unknown) {
  const message = error instanceof Error ? error.message : String(error || '状态检测失败');
  if (/failed to fetch/i.test(message)) return '无法连接本地服务，请确认后端已启动';
  if (/networkerror|load failed/i.test(message)) return '网络请求失败，请稍后重试';
  return message || '状态检测失败';
}

export default function App() {
  const [apiStatus, setApiStatus] = useState<ConnectionStatus>('waiting');
  const [cookieStatus, setCookieStatus] = useState<ConnectionStatus>('waiting');
  const [accountStatus, setAccountStatus] = useState<'not_connected' | 'connected'>('not_connected');
  const [authState, setAuthState] = useState<AuthState>('login');
  const [statusMessage, setStatusMessage] = useState('等待连接本地 API');
  const [statusVersion, setStatusVersion] = useState(0);

  useEffect(() => {
    let cancelled = false;

    const loadStatus = async () => {
      try {
        const status = await fetchAuthStatus();
        if (cancelled) return;

        setApiStatus(status.api_ready ? 'ready' : 'waiting');
        setCookieStatus(status.cookie_valid ? 'ready' : 'waiting');
        setAccountStatus(status.cookie_valid ? 'connected' : 'not_connected');

        if (status.api_ready && status.cookie_valid) {
          setStatusMessage(status.account.nickname ? `已连接：${status.account.nickname}` : '登录态已就绪');
          setAuthState('authenticated');
          return;
        }

        if (!status.api_ready) {
          setStatusMessage('等待启动本地 API');
        } else if (!status.cookie_valid) {
          setStatusMessage('API 已就绪，请扫码登录');
        }
      } catch (error) {
        if (cancelled) return;
        setApiStatus('error');
        setCookieStatus('error');
        setStatusMessage(formatAuthStatusError(error));
      }
    };

    void loadStatus();
    return () => {
      cancelled = true;
    };
  }, [statusVersion]);

  const handleAuthenticated = () => {
    setApiStatus('ready');
    setCookieStatus('ready');
    setAccountStatus('connected');
    setStatusMessage('登录成功');
    setStatusVersion((value) => value + 1);
    if (authState !== 'authenticated') {
      setAuthState('authenticated');
    }
  };

  const handleReset = () => {
    setApiStatus('waiting');
    setCookieStatus('waiting');
    setAccountStatus('not_connected');
    setAuthState('login');
    setStatusMessage('重新检测连接状态');
    setStatusVersion((value) => value + 1);
  };

  if (authState === 'authenticated') {
    return <HomePage />;
  }

  return (
    <LoginPage
      apiStatus={apiStatus}
      cookieStatus={cookieStatus}
      accountStatus={accountStatus}
      statusMessage={statusMessage}
      onAuthenticated={handleAuthenticated}
      onReset={handleReset}
      onStatusMessage={setStatusMessage}
      onRefreshStatus={() => setStatusVersion((value) => value + 1)}
    />
  );
}
