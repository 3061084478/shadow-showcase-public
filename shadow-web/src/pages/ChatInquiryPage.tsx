import { memo, useEffect, useMemo, useState } from 'react';
import { motion } from 'motion/react';
import { Image as ImageIcon, Info, MoreHorizontal, Search, Users } from 'lucide-react';
import type { ChatMessage, ChatMessageType, ChatQueryPayload, ChatQueryScope, ChatSenderScope, FriendListItemLite } from '../types';
import { DateField } from '../components/DateField';
import { PageWrapper } from '../components/PageWrapper';
import { fetchChatActiveDates, queryChatMessages } from '../services/chat';
import { syncFriendRecent } from '../services/friends';

type ChatInquiryPageProps = {
  friend?: FriendListItemLite;
  friends?: FriendListItemLite[];
  selectedFriendId?: string | null;
  onSelectFriend?: (uid: string) => void;
  onBack: () => void;
};

type MessageRowProps = {
  message: ChatMessage;
  friendName: string;
  keyword: string;
  onPreviewImage: (src: string) => void;
};

const ChatMessageRow = memo(function ChatMessageRow({ message, friendName, keyword, onPreviewImage }: MessageRowProps) {
  const normalizedKeyword = keyword.trim();
  const highlightPattern = useMemo(
    () =>
      normalizedKeyword
        ? new RegExp(`(${normalizedKeyword.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')})`, 'gi')
        : null,
    [normalizedKeyword],
  );

  const renderHighlighted = (text: string | undefined, className = 'chat-highlight font-bold underline underline-offset-4') => {
    if (!text) return text;
    if (!highlightPattern || !normalizedKeyword) return text;
    return text.split(highlightPattern).map((part, innerIndex) =>
      part.toLowerCase() === normalizedKeyword.toLowerCase() ? (
        <span key={innerIndex} className={className}>
          {part}
        </span>
      ) : (
        part
      ),
    );
  };

  const imageContent = message.type === 'image' ? message.content?.trim() : '';
  const isImageUrl = Boolean(imageContent && /^(https?:\/\/|data:image\/|\/)/i.test(imageContent));

  return (
    <div className={`message-card flex flex-col gap-4 ${message.type === 'song' ? 'song-message-card' : ''}`}>
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className={`text-[10px] font-bold uppercase tracking-widest ${message.sender === 'me' ? 'chat-sender-self' : 'chat-sender-friend'}`}>{message.sender === 'me' ? 'Me' : friendName}</span>
          <span className="chat-message-time text-[9px] font-mono">{message.timestamp}</span>
        </div>
        <MoreHorizontal size={14} className="chat-message-more" />
      </div>

      {message.type !== 'song' ? (
        message.type === 'image' ? (
          <div className="chat-image-message">
            {isImageUrl ? (
              <button type="button" className="chat-image-message__preview" onClick={() => onPreviewImage(imageContent || '')}>
                <img src={imageContent} alt="图片消息" loading="lazy" />
              </button>
            ) : (
              <div className="chat-image-message__fallback">
                <ImageIcon size={18} />
                <span>{renderHighlighted(imageContent || '图片消息')}</span>
              </div>
            )}
          </div>
        ) : (
          <p className="chat-message-body text-[14px] leading-relaxed font-medium">{renderHighlighted(message.content)}</p>
        )
      ) : (
        <div className="flex gap-6 items-center">
          <div className="flex-1 min-w-0">
            <h4 className="chat-song-title text-[15px] font-bold truncate">
              {renderHighlighted(message.song?.name, 'chat-highlight-strong')}
            </h4>
            <p className="chat-song-artist text-[12px] font-medium truncate mt-1">{message.song?.artist}</p>
            <div className="flex items-center gap-2 mt-3">
              <span className={`text-[9px] px-3 py-1 rounded-full uppercase tracking-widest font-bold border ${message.song?.status === 'known' ? 'chat-song-badge-known' : 'chat-song-badge-unknown'}`}>
                {message.song?.status === 'known' ? message.song?.genre || 'MUSIC' : 'unknown'}
              </span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
});

export function ChatInquiryPage({ friend, friends = [], selectedFriendId, onSelectFriend, onBack }: ChatInquiryPageProps) {
  const [range, setRange] = useState<'Recent' | 'All' | 'Pages' | 'New'>('Recent');
  const [pageNumber, setPageNumber] = useState('1');
  const [sender, setSender] = useState<'Both' | 'Me' | 'Friend'>('Both');
  const [msgType, setMsgType] = useState<'All' | 'Text' | 'Song' | 'Image'>('All');
  const [queryMethod, setQueryMethod] = useState<'All' | 'Date' | 'Period'>('All');
  const [date1, setDate1] = useState('');
  const [date2, setDate2] = useState('');
  const [keyword, setKeyword] = useState('');
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [loading, setLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState('');
  const [hasLoadedOnce, setHasLoadedOnce] = useState(false);
  const [activeDates, setActiveDates] = useState<string[]>([]);
  const [refreshingArchive, setRefreshingArchive] = useState(false);
  const [previewImage, setPreviewImage] = useState<string | null>(null);

  const scope = useMemo<ChatQueryScope>(() => {
    if (range === 'Recent') return 'recent';
    if (range === 'Pages') return 'pages';
    if (range === 'New') return 'incremental';
    return 'all';
  }, [range]);

  const senderScope = useMemo<ChatSenderScope>(() => {
    if (sender === 'Me') return 'self';
    if (sender === 'Friend') return 'friend';
    return 'all';
  }, [sender]);

  const normalizedMsgType = useMemo<ChatMessageType>(() => {
    if (msgType === 'Text') return 'text';
    if (msgType === 'Song') return 'song';
    if (msgType === 'Image') return 'image';
    return 'all';
  }, [msgType]);

  const friendDisplayName = friend?.nickname || '好友';

  const buildPayload = (): ChatQueryPayload => {
    const payload: ChatQueryPayload = {
      scope,
      sender_scope: senderScope,
      msg_type: normalizedMsgType,
      keyword: keyword.trim() || undefined,
      limit: range === 'Recent' || range === 'New' ? 50 : undefined,
      page: range === 'Pages' ? Math.max(1, Number(pageNumber) || 1) : undefined,
    };

    if (range === 'All' && queryMethod === 'Date' && date1) {
      payload.date = date1;
    }
    if (range === 'All' && queryMethod === 'Period') {
      payload.start_date = date1 || undefined;
      payload.end_date = date2 || undefined;
    }
    return payload;
  };

  const runQuery = async () => {
    if (!friend) return;
    try {
      setLoading(true);
      setErrorMessage('');
      const result = await queryChatMessages(friend.friend_uid, buildPayload(), friend.nickname);
      setMessages(result.rows);
      setHasLoadedOnce(true);
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : '聊天记录查询失败');
      setMessages([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    setMessages([]);
    setErrorMessage('');
    setHasLoadedOnce(false);
    setDate1('');
    setDate2('');
    setActiveDates([]);
  }, [friend?.friend_uid]);

  useEffect(() => {
    let cancelled = false;
    const loadActiveDates = async () => {
      if (!friend) return;
      try {
        const payload = await fetchChatActiveDates(friend.friend_uid);
        if (cancelled) return;
        setActiveDates(payload.dates || []);
      } catch {
        if (cancelled) return;
        setActiveDates([]);
      }
    };
    void loadActiveDates();
    return () => {
      cancelled = true;
    };
  }, [friend?.friend_uid]);

  useEffect(() => {
    if (range !== 'All') {
      setQueryMethod('All');
      setDate1('');
      setDate2('');
    }
  }, [range]);

  const handleClear = () => {
    setRange('Recent');
    setPageNumber('1');
    setSender('Both');
    setMsgType('All');
    setQueryMethod('All');
    setDate1('');
    setDate2('');
    setKeyword('');
    setErrorMessage('');
  };

  const refreshArchive = async () => {
    if (!friend) return;
    try {
      setRefreshingArchive(true);
      await syncFriendRecent(friend.friend_uid, 3, 50);
      const payload = await fetchChatActiveDates(friend.friend_uid);
      setActiveDates(payload.dates || []);
    } finally {
      setRefreshingArchive(false);
    }
  };

  return (
    <PageWrapper title="聊天记录查询" subtitle="" friend={friend} friends={friends} selectedFriendId={selectedFriendId} onSelectFriend={onSelectFriend} onBack={onBack} onRefreshArchive={friend ? () => void refreshArchive() : null} refreshingArchive={refreshingArchive}>
      <>
        {!friend ? (
          <div className="empty-state-card w-full">
            <Users size={64} strokeWidth={1} />
            <h3 className="mt-4">尚未选择好友</h3>
            <p className="ui-empty-note text-[11px] uppercase tracking-widest mt-2">请先选择好友</p>
          </div>
        ) : (
          <div className="page-content-wrapper">
          <div className="chat-page-grid">
            <div className="search-tools-panel h-full overflow-y-auto friend-list-scroll">
              <div className="space-y-6">
                <div className="flex items-center justify-between border-b ui-divider-soft pb-2">
                  <span className="ui-eyebrow text-[10px] uppercase font-bold tracking-[0.2em]">查询控制台</span>
                  <Info size={12} className="ui-icon-muted" />
                </div>

                <div className="space-y-4">
                  <label className="ui-eyebrow text-[10px] uppercase font-bold tracking-widest">范围</label>
                  <div className="grid grid-cols-2 gap-2">
                    {['Recent', 'All', 'Pages', 'New'].map((item) => (
                      <button
                        key={item}
                        onClick={() => setRange(item as 'Recent' | 'All' | 'Pages' | 'New')}
                        className={`ui-segment-button px-3 py-2.5 rounded-xl text-[10px] font-bold transition-all border ${range === item ? 'is-active' : ''}`}
                      >
                        {item === 'Recent' ? '最近50条' : item === 'All' ? '全部历史' : item === 'Pages' ? '最近N页' : '新增内容'}
                      </button>
                    ))}
                  </div>
                  {range === 'Pages' && (
                    <motion.input
                      initial={{ opacity: 0, y: -5 }}
                      animate={{ opacity: 1, y: 0 }}
                      className="search-input-field !h-10 !text-[12px] !pl-4"
                      placeholder="输入页数"
                      value={pageNumber}
                      onChange={(event) => setPageNumber(event.target.value)}
                    />
                  )}
                </div>

                <div className="space-y-4">
                  <label className="ui-eyebrow text-[10px] uppercase font-bold tracking-widest">发送方</label>
                  <div className="flex gap-2">
                    {['Both', 'Me', 'Friend'].map((item) => (
                      <button
                        key={item}
                        onClick={() => setSender(item as 'Both' | 'Me' | 'Friend')}
                        className={`ui-segment-button flex-1 px-3 py-2.5 rounded-xl text-[10px] font-bold transition-all border ${sender === item ? 'is-active' : ''}`}
                      >
                        {item === 'Both' ? '双方' : item === 'Me' ? '我方' : '好友'}
                      </button>
                    ))}
                  </div>
                </div>

                <div className="space-y-4">
                  <label className="ui-eyebrow text-[10px] uppercase font-bold tracking-widest">信息类型</label>
                  <div className="flex flex-wrap gap-2">
                    {['All', 'Text', 'Song', 'Image'].map((item) => (
                      <button
                        key={item}
                        onClick={() => setMsgType(item as 'All' | 'Text' | 'Song' | 'Image')}
                        className={`ui-segment-button px-3 py-2.5 rounded-xl text-[10px] font-bold transition-all border ${msgType === item ? 'is-active' : ''}`}
                      >
                        {item === 'All' ? '全部' : item === 'Text' ? '文本' : item === 'Song' ? '歌曲' : '图片'}
                      </button>
                    ))}
                  </div>
                </div>

                {range === 'All' && (
                  <div className="space-y-4">
                    <label className="ui-eyebrow text-[10px] uppercase font-bold tracking-widest">查询方式</label>
                    <div className="flex gap-2">
                      {['All', 'Date', 'Period'].map((item) => (
                        <button
                          key={item}
                          onClick={() => setQueryMethod(item as 'All' | 'Date' | 'Period')}
                          className={`ui-segment-button flex-1 px-3 py-2.5 rounded-xl text-[10px] font-bold transition-all border ${queryMethod === item ? 'is-active' : ''}`}
                        >
                          {item === 'All' ? '全部' : item === 'Date' ? '按日期' : '按时间段'}
                        </button>
                      ))}
                    </div>
                    {queryMethod === 'Date' && (
                      <div className="mt-2">
                        <DateField value={date1} onChange={setDate1} activeDates={activeDates} />
                      </div>
                    )}
                    {queryMethod === 'Period' && (
                      <div className="flex flex-col gap-3 mt-2">
                        <DateField value={date1} onChange={setDate1} activeDates={activeDates} />
                        <DateField value={date2} onChange={setDate2} activeDates={activeDates} minDate={date1} />
                      </div>
                    )}
                  </div>
                )}

                <div className="space-y-4">
                  <label className="ui-eyebrow text-[10px] uppercase font-bold tracking-widest">关键词</label>
                  <div className="relative">
                    <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 ui-icon-muted" />
                    <input className="search-input-field !h-12 !text-[13px] !pl-10" placeholder="输入关键词 / 歌曲名 / 歌手" value={keyword} onChange={(event) => setKeyword(event.target.value)} />
                  </div>
                </div>
              </div>

              <div className="mt-12 flex flex-col gap-3">
                <button className="ui-action-primary w-full py-4 rounded-2xl font-bold text-[11px] uppercase tracking-widest transition-all shadow-xl active:scale-95 disabled:opacity-60" onClick={() => void runQuery()} disabled={loading}>
                  {loading ? '查询中...' : '开始查询'}
                </button>
                <button className="ui-action-secondary w-full py-3 rounded-2xl border font-bold text-[10px] uppercase tracking-widest transition-all active:scale-95" onClick={handleClear}>
                  重置条件
                </button>
              </div>
            </div>

            <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
              <div className="flex items-center justify-between border-b ui-divider-soft pb-4 mb-6 px-2 shrink-0">
                <span className="ui-eyebrow text-[10px] uppercase font-bold tracking-[0.2em]">查询归档时间线</span>
                <span className="ui-meta-text text-[10px] font-mono">HITS: {messages.length}</span>
              </div>

              <div className="flex-1 overflow-y-auto friend-list-scroll pr-2 pb-12">
                {errorMessage ? (
                  <div className="flex flex-col items-center justify-center gap-4 mt-24" style={{ color: 'var(--ui-danger-soft)' }}>
                    <Info size={42} strokeWidth={1} />
                    <p className="text-[11px] uppercase font-bold tracking-widest">{errorMessage}</p>
                  </div>
                ) : loading && !hasLoadedOnce ? (
                  <div className="flex flex-col items-center justify-center ui-empty-note gap-4 mt-24">
                    <Search size={42} strokeWidth={1} />
                    <p className="text-[11px] uppercase font-bold tracking-widest">正在加载聊天记录</p>
                  </div>
                ) : messages.length === 0 ? (
                  <div className="flex flex-col items-center justify-center ui-empty-ghost gap-4 mt-32">
                    <Search size={48} strokeWidth={1} />
                    <p className="text-[11px] uppercase font-bold tracking-widest">暂无匹配聊天记录</p>
                  </div>
                ) : (
                  <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="flex flex-col gap-6">
                    {messages.map((message) => (
                      <ChatMessageRow key={message.id} message={message} friendName={friendDisplayName} keyword={keyword} onPreviewImage={setPreviewImage} />
                    ))}
                  </motion.div>
                )}
              </div>
            </div>
          </div>
          </div>
        )}
        {previewImage ? (
          <div className="chat-image-lightbox" onClick={() => setPreviewImage(null)}>
            <button type="button" className="chat-image-lightbox__close" onClick={() => setPreviewImage(null)}>关闭</button>
            <img src={previewImage} alt="原图预览" onClick={(event) => event.stopPropagation()} />
          </div>
        ) : null}
      </>
    </PageWrapper>
  );
}
