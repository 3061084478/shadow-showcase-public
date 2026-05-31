import type React from 'react';
import { AnimatePresence, motion } from 'motion/react';
import { Pin, Search, Users, X } from 'lucide-react';
import type { FriendListItemLite } from '../types';

type FriendCapsuleProps = {
  selectedFriend?: FriendListItemLite;
  onClick: () => void;
  active: boolean;
};

export function FriendCapsule({ selectedFriend, onClick, active }: FriendCapsuleProps) {
  return (
    <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} className={`absolute bottom-7 left-7 z-[60] friend-capsule ${active ? 'active' : ''}`} onClick={onClick}>
      <div className="flex items-center gap-3 w-full">
        <div className="capsule-avatar">
          {selectedFriend?.avatar_url ? (
            <img src={selectedFriend.avatar_url} alt="" className="w-full h-full object-cover" />
          ) : (
            <div className="w-full h-full flex items-center justify-center ui-icon-muted">
              <Users size={18} strokeWidth={1.5} />
            </div>
          )}
        </div>
        <div className="capsule-info">
          <span className="capsule-name">{selectedFriend ? selectedFriend.nickname : '好友列表'}</span>
          {selectedFriend && (
            <div className="capsule-status">
              <div className={`status-dot ${selectedFriend.friend_sync_status === 'ok' ? 'ok' : 'sync'}`} />
              <span className="truncate">
                {selectedFriend.friend_sync_status === 'ok'
                  ? `已同步 · ${selectedFriend.message_count} 条消息 · ${selectedFriend.shared_song_count} 首歌`
                  : `待同步 · ${selectedFriend.message_count} 条消息 · ${selectedFriend.shared_song_count} 首歌`}
              </span>
            </div>
          )}
        </div>
      </div>
    </motion.div>
  );
}

type SelectedFriendCardProps = {
  friend?: FriendListItemLite;
  active?: boolean;
  onClick?: () => void;
};

export function SelectedFriendCard({ friend, active = false, onClick }: SelectedFriendCardProps) {
  if (!friend) return null;

  const syncText =
    friend.friend_sync_status === 'ok'
      ? '已同步'
      : friend.friend_sync_status === 'error'
        ? '同步异常'
        : '待同步';

  return (
    <button type="button" className={`selected-friend-card ${active ? 'active' : ''} ${onClick ? 'is-clickable' : ''}`} onClick={onClick}>
      <div className="selected-friend-avatar">
        {friend.avatar_url ? (
          <img src={friend.avatar_url} alt="" className="w-full h-full object-cover" />
        ) : (
          <div className="w-full h-full flex items-center justify-center ui-icon-muted">
            <Users size={18} strokeWidth={1.5} />
          </div>
        )}
      </div>
      <div className="selected-friend-meta">
        <div className="selected-friend-name">{friend.nickname}</div>
        <div className="selected-friend-stats">
          <span>{syncText}</span>
          <span>{friend.message_count} 条信息</span>
          <span>{friend.shared_song_count} 首歌</span>
        </div>
      </div>
    </button>
  );
}

type FriendDrawerProps = {
  onClose: () => void;
  onSelect: (uid: string) => void;
  onTogglePin: (e: React.MouseEvent, uid: string) => void;
  selectedFriendId: string | null;
  activeFilter: 'Recent' | 'All' | 'Pending';
  setActiveFilter: (v: 'Recent' | 'All' | 'Pending') => void;
  searchQuery: string;
  setSearchQuery: (v: string) => void;
  drawerRef: React.RefObject<HTMLDivElement | null>;
  pinnedFriends: FriendListItemLite[];
  otherFriends: FriendListItemLite[];
};

export function FriendDrawer({
  onClose,
  onSelect,
  onTogglePin,
  selectedFriendId,
  activeFilter,
  setActiveFilter,
  searchQuery,
  setSearchQuery,
  drawerRef,
  pinnedFriends,
  otherFriends,
}: FriendDrawerProps) {
  const isPendingMode = activeFilter === 'Pending';

  const renderFriendList = (list: FriendListItemLite[]) =>
    list.map((friend) => (
      <div key={friend.friend_uid} onClick={() => onSelect(friend.friend_uid)} className={`friend-list-row group ${selectedFriendId === friend.friend_uid ? 'selected' : ''}`}>
        <div className="row-avatar">
          {friend.avatar_url ? (
            <img src={friend.avatar_url} alt="" className="w-full h-full object-cover" />
          ) : (
            <div className="w-full h-full flex items-center justify-center ui-icon-muted">
              <Users size={14} strokeWidth={1.5} />
            </div>
          )}
        </div>
        <div className="row-content">
          <span className="row-name">{friend.nickname}</span>
          <div className="row-meta">
            {isPendingMode
              ? `待补充 · ${friend.genre_unknown_count} 首`
              : friend.friend_sync_status === 'ok'
                ? `已同步 · ${friend.message_count} 条消息 · ${friend.shared_song_count} 首歌`
                : friend.friend_sync_status === 'needs_sync'
                  ? `待同步 · ${friend.message_count} 条消息 · ${friend.shared_song_count} 首歌`
                  : '同步错误'}
          </div>
        </div>
        <button onClick={(e) => onTogglePin(e, friend.friend_uid)} className={`pin-btn ${friend.is_pinned ? 'pinned' : ''}`}>
          <Pin size={12} className={friend.is_pinned ? 'fill-current' : ''} />
        </button>
      </div>
    ));

  return (
    <motion.div ref={drawerRef} initial={{ opacity: 0, y: 30, scale: 0.95 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, y: 20, scale: 0.98 }} transition={{ type: 'spring', damping: 25, stiffness: 350 }} className="absolute bottom-[92px] left-7 z-[70] friend-drawer">
      <div className="drawer-header">
        <h3>好友</h3>
        <button onClick={onClose} className="p-2 rounded-xl ui-icon-muted hover:bg-white/5 hover:text-white transition-all">
          <X size={16} />
        </button>
      </div>

      <div className="drawer-search-area">
        <div className="search-input-area">
          <Search size={14} className="search-icon" />
          <input type="text" placeholder="搜索昵称 / UID" value={searchQuery} onChange={(e) => setSearchQuery(e.target.value)} className="search-input-field" />
        </div>
      </div>

      <div className="drawer-tabs-area">
        <div onClick={() => setActiveFilter('Recent')} className={`filter-tab ${activeFilter === 'Recent' ? 'active' : ''}`}>
          最近
        </div>
        <div onClick={() => setActiveFilter('All')} className={`filter-tab ${activeFilter === 'All' ? 'active' : ''}`}>
          全部
        </div>
        <div onClick={() => setActiveFilter('Pending')} className={`filter-tab ${activeFilter === 'Pending' ? 'active' : ''}`}>
          待补充
        </div>
      </div>

      <div className="friend-list-scroll">
        {pinnedFriends.length > 0 && (
          <div className="flex flex-col gap-2">
            <div className="list-section-header">
              <span>置顶</span>
            </div>
            {renderFriendList(pinnedFriends)}
          </div>
        )}

        <div className="flex flex-col gap-2">
          {pinnedFriends.length > 0 && (
            <div className="list-section-header">
              <span>其他好友</span>
            </div>
          )}
          {renderFriendList(otherFriends)}
        </div>

        {pinnedFriends.length === 0 && otherFriends.length === 0 && (
          <div className="py-20 flex flex-col items-center justify-center ui-empty-ghost gap-3">
            <Search size={32} strokeWidth={1} />
            <p className="text-[10px] uppercase font-bold tracking-widest opacity-30">无匹配结果</p>
          </div>
        )}
      </div>
    </motion.div>
  );
}
