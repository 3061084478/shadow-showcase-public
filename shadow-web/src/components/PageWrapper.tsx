import { useEffect, useRef, useState } from 'react';
import { AnimatePresence, motion } from 'motion/react';
import { ArrowLeft, Info, RefreshCw } from 'lucide-react';
import type { PageWrapperProps } from '../types';
import { SelectedFriendCard } from './FriendComponents';

export function PageWrapper({
  title,
  subtitle,
  className = '',
  friend,
  friends = [],
  selectedFriendId,
  hideFriendCard = false,
  onSelectFriend,
  onBack,
  onRefreshArchive,
  refreshingArchive = false,
  headerBottom,
  children,
}: PageWrapperProps) {
  const [friendMenuOpen, setFriendMenuOpen] = useState(false);
  const switcherRef = useRef<HTMLDivElement | null>(null);
  const canSwitchFriend = Boolean(friend && onSelectFriend && friends.length > 0);
  const visibleFriends = friends.filter((item) => item.friend_uid !== friend?.friend_uid).slice(0, 12);

  useEffect(() => {
    if (!friendMenuOpen) return;
    const handleClickOutside = (event: MouseEvent) => {
      if (switcherRef.current && !switcherRef.current.contains(event.target as Node)) {
        setFriendMenuOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [friendMenuOpen]);

  useEffect(() => {
    setFriendMenuOpen(false);
  }, [selectedFriendId, friend?.friend_uid]);

  return (
    <motion.div initial={{ opacity: 0, backdropFilter: 'blur(0px)' }} animate={{ opacity: 1, backdropFilter: 'blur(10px)' }} exit={{ opacity: 0 }} transition={{ duration: 0.4 }} className={`page-container ${className}`}>
      <div className={`page-header px-12 pt-10 pb-6 ${headerBottom ? 'page-header--stacked' : ''}`}>
        <div className="page-header__top flex w-full items-center justify-between">
          <div className="flex items-center gap-5">
            <button onClick={onBack} className="ui-back-button p-3 rounded-2xl border transition-all active:scale-95">
              <ArrowLeft size={20} />
            </button>
            <div className="page-title-group">
              <h1 className="flex items-center gap-4 text-2xl font-bold tracking-tight text-white mb-0">{title}</h1>
              {subtitle ? <p>{subtitle}</p> : null}
            </div>
          </div>

          <div className="flex items-center gap-2.5">
            {!hideFriendCard && friend ? (
              <div className="page-friend-switcher" ref={switcherRef}>
                <SelectedFriendCard friend={friend} active={friendMenuOpen} onClick={canSwitchFriend ? () => setFriendMenuOpen((value) => !value) : undefined} />
                <AnimatePresence>
                  {canSwitchFriend && friendMenuOpen ? (
                    <motion.div
                      className="page-friend-dropdown friend-list-scroll"
                      initial={{ opacity: 0, y: -8, scale: 0.98 }}
                      animate={{ opacity: 1, y: 0, scale: 1 }}
                      exit={{ opacity: 0, y: -6, scale: 0.98 }}
                      transition={{ duration: 0.18 }}
                    >
                      {visibleFriends.length > 0 ? (
                        visibleFriends.map((item) => (
                          <button
                            type="button"
                            key={item.friend_uid}
                            className="page-friend-option"
                            onClick={() => {
                              onSelectFriend?.(item.friend_uid);
                              setFriendMenuOpen(false);
                            }}
                          >
                            <span className="page-friend-option__avatar">
                              {item.avatar_url ? <img src={item.avatar_url} alt="" /> : null}
                            </span>
                            <span className="page-friend-option__meta">
                              <strong>{item.nickname}</strong>
                              <small>{item.message_count} 条信息 · {item.shared_song_count} 首歌</small>
                            </span>
                          </button>
                        ))
                      ) : (
                        <div className="page-friend-option is-empty">没有其它可切换好友</div>
                      )}
                    </motion.div>
                  ) : null}
                </AnimatePresence>
              </div>
            ) : !hideFriendCard ? (
              <div className="ui-empty-callout px-6 py-2 rounded-full border text-[10px] font-bold uppercase tracking-widest flex items-center gap-2">
                <Info size={12} />
                请先选择好友
              </div>
            ) : null}
            {onRefreshArchive ? (
              <button
                onClick={onRefreshArchive}
                disabled={refreshingArchive}
                className="ui-refresh-button flex items-center gap-2 rounded-full border px-3.5 py-2 text-[10px] font-semibold tracking-[0.14em] shadow-xl backdrop-blur-md transition disabled:cursor-not-allowed disabled:opacity-50"
              >
                <RefreshCw size={12} className={refreshingArchive ? 'animate-spin' : ''} />
                重新归档
              </button>
            ) : null}
          </div>
        </div>
        {headerBottom ? <div className="page-header__bottom w-full">{headerBottom}</div> : null}
      </div>

      <div className="page-content px-12">{children}</div>
    </motion.div>
  );
}
