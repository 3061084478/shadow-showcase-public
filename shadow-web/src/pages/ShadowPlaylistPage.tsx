import { memo, useEffect, useState } from 'react';
import { AnimatePresence, motion } from 'motion/react';
import { CheckCircle2, Info, ListMusic, Search, Settings } from 'lucide-react';
import { DateField } from '../components/DateField';
import { PageWrapper } from '../components/PageWrapper';
import type {
  FriendListItemLite,
  ShadowCandidate,
  ShadowPlaylistTrack,
  ShadowTargetOption,
} from '../types';
import {
  buildShadowPlaylist,
  fetchShadowActiveDates,
  fetchShadowCandidates,
  fetchShadowTargets,
  setShadowTarget,
} from '../services/shadow';
import { syncFriendRecent } from '../services/friends';

type ShadowPlaylistPageProps = {
  friend?: FriendListItemLite;
  friends?: FriendListItemLite[];
  selectedFriendId?: string | null;
  onSelectFriend?: (uid: string) => void;
  onBack: () => void;
};

type CandidateRowProps = {
  candidate: ShadowCandidate;
  selected: boolean;
  onToggle: (id: string) => void;
};

const CandidateRow = memo(function CandidateRow({
  candidate,
  selected,
  onToggle,
}: CandidateRowProps) {
  return (
    <div
      onClick={() => onToggle(candidate.song_id)}
      className={`playlist-candidate-row flex items-center gap-4 p-3 rounded-2xl border transition-all cursor-pointer group ${
        selected ? 'is-selected' : ''
      }`}
    >
      <div
        className={`playlist-check w-5 h-5 rounded-lg border flex items-center justify-center transition-all ${
          selected ? 'is-selected' : ''
        }`}
      >
        <CheckCircle2 size={12} />
      </div>
      <div className="flex-1 min-w-0">
        <p className="playlist-row-title text-[12px] font-bold truncate">
          {candidate.song_name}
        </p>
        <p className="playlist-row-artist text-[10px] truncate">
          {candidate.artist_names.join(' / ')}
        </p>
      </div>
      <span className="playlist-tag text-[9px] px-2 py-0.5 rounded-md uppercase font-bold tracking-widest">
        {candidate.genre_label || 'unknown'}
      </span>
    </div>
  );
});

export function ShadowPlaylistPage({
  friend,
  friends = [],
  selectedFriendId,
  onSelectFriend,
  onBack,
}: ShadowPlaylistPageProps) {
  const [candidates, setCandidates] = useState<ShadowCandidate[]>([]);
  const [isLoaded, setIsLoaded] = useState(false);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [targetPanelMode, setTargetPanelMode] = useState<null | 'switch' | 'create'>(null);
  const [targetPlaylist, setTargetPlaylist] = useState('未设置目标歌单');
  const [newPlaylistName, setNewPlaylistName] = useState('');
  const [isPrivate, setIsPrivate] = useState(true);
  const [range, setRange] = useState<'Recent' | 'All' | 'Pages' | 'New'>('Recent');
  const [pageNumber, setPageNumber] = useState('1');
  const [queryMethod, setQueryMethod] = useState<'All' | 'Date' | 'Period'>('All');
  const [date1, setDate1] = useState('');
  const [date2, setDate2] = useState('');
  const [maxCount, setMaxCount] = useState('');
  const [keyword, setKeyword] = useState('');
  const [playlistOptions, setPlaylistOptions] = useState<ShadowTargetOption[]>([]);
  const [currentTracks, setCurrentTracks] = useState<ShadowPlaylistTrack[]>([]);
  const [currentPlaylistId, setCurrentPlaylistId] = useState('');
  const [buildMessage, setBuildMessage] = useState('');
  const [loading, setLoading] = useState(false);
  const [activeDates, setActiveDates] = useState<string[]>([]);
  const [refreshingArchive, setRefreshingArchive] = useState(false);

  useEffect(() => {
    let cancelled = false;

    const loadTargets = async () => {
      try {
        const payload = await fetchShadowTargets();
        if (cancelled) return;
        setPlaylistOptions(payload.playlists);
        setCurrentTracks(payload.currentTracks);
        if (payload.currentTarget) {
          setTargetPlaylist(payload.currentTarget.playlist_name);
          setCurrentPlaylistId(payload.currentTarget.playlist_id);
        }
      } catch {
        if (cancelled) return;
        setPlaylistOptions([]);
      }
    };

    void loadTargets();

    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (range !== 'All') {
      setQueryMethod('All');
      setDate1('');
      setDate2('');
    }
  }, [range]);

  useEffect(() => {
    setDate1('');
    setDate2('');
    setActiveDates([]);
    setCandidates([]);
    setIsLoaded(false);
    setSelectedIds(new Set());
  }, [friend?.friend_uid]);

  useEffect(() => {
    let cancelled = false;

    const loadActiveDates = async () => {
      if (!friend) return;
      try {
        const payload = await fetchShadowActiveDates(friend.friend_uid);
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

  const handleLoad = async () => {
    if (!friend) return;
    setLoading(true);
    setBuildMessage('');

    try {
      const customLimit = maxCount.trim() ? Number(maxCount) || undefined : undefined;
      const rows = await fetchShadowCandidates(friend.friend_uid, {
        scope:
          range === 'Recent'
            ? 'recent'
            : range === 'Pages'
              ? 'pages'
              : range === 'New'
                ? 'incremental'
                : 'all',
        keyword: keyword.trim() || undefined,
        known_only: true,
        limit: range === 'Recent' ? 50 : range === 'New' ? customLimit ?? 50 : customLimit,
        page: range === 'Pages' ? Math.max(1, Number(pageNumber) || 1) : undefined,
        date: range === 'All' && queryMethod === 'Date' ? date1 || undefined : undefined,
        start_date:
          range === 'All' && queryMethod === 'Period' ? date1 || undefined : undefined,
        end_date:
          range === 'All' && queryMethod === 'Period' ? date2 || undefined : undefined,
      });
      setIsLoaded(true);
      setCandidates(rows);
      setSelectedIds(new Set());
    } catch (error) {
      setBuildMessage(error instanceof Error ? error.message : '加载候选歌曲失败');
      setCandidates([]);
      setIsLoaded(false);
    } finally {
      setLoading(false);
    }
  };

  const toggleSelect = (id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const handleSelectAll = () =>
    setSelectedIds(new Set(candidates.map((candidate) => candidate.song_id)));
  const handleSelectNone = () => setSelectedIds(new Set());
  const handleInvert = () => {
    setSelectedIds((prev) => {
      const next = new Set<string>();
      candidates.forEach((candidate) => {
        if (!prev.has(candidate.song_id)) next.add(candidate.song_id);
      });
      return next;
    });
  };

  const handleSwitchTarget = async (playlist: ShadowTargetOption) => {
    try {
      await setShadowTarget({
        strategy: 'use_existing',
        playlist_id: playlist.id,
        playlist_name: playlist.name,
        is_private: false,
      });
      setTargetPlaylist(playlist.name);
      setCurrentPlaylistId(playlist.id);
      setTargetPanelMode(null);
      const payload = await fetchShadowTargets();
      setCurrentTracks(payload.currentTracks);
    } catch (error) {
      setBuildMessage(error instanceof Error ? error.message : '切换目标歌单失败');
    }
  };

  const handleCreateTarget = async () => {
    if (!newPlaylistName.trim()) return;
    try {
      const payload = await setShadowTarget({
        strategy: 'auto_create',
        playlist_name: newPlaylistName.trim(),
        is_private: isPrivate,
      });
      setTargetPlaylist(payload.playlist_name);
      setCurrentPlaylistId(payload.playlist_id);
      setTargetPanelMode(null);
      setNewPlaylistName('');
      const targets = await fetchShadowTargets();
      setCurrentTracks(targets.currentTracks);
    } catch (error) {
      setBuildMessage(error instanceof Error ? error.message : '新建目标歌单失败');
    }
  };

  const handleBuild = async () => {
    if (!friend || selectedIds.size === 0) return;
    try {
      setBuildMessage('正在生成影子歌单...');
      const payload = await buildShadowPlaylist(friend.friend_uid, {
        playlist_id: currentPlaylistId || undefined,
        playlist_name: targetPlaylist,
        song_ids: Array.from(selectedIds),
        overwrite: true,
      });
      setBuildMessage(
        `已写入 ${payload.generated_count} 首歌曲到 ${payload.playlist_name || targetPlaylist}`,
      );
      const targets = await fetchShadowTargets();
      setCurrentTracks(targets.currentTracks);
      setSelectedIds(new Set());
      await handleLoad();
    } catch (error) {
      setBuildMessage(error instanceof Error ? error.message : '生成影子歌单失败');
    }
  };

  const refreshArchive = async () => {
    if (!friend) return;
    try {
      setRefreshingArchive(true);
      await syncFriendRecent(friend.friend_uid, 3, 50);
      const payload = await fetchShadowActiveDates(friend.friend_uid);
      setActiveDates(payload.dates || []);
    } finally {
      setRefreshingArchive(false);
    }
  };

  return (
    <PageWrapper
      title="影子歌单"
      subtitle=""
      friend={friend}
      friends={friends}
      selectedFriendId={selectedFriendId}
      onSelectFriend={onSelectFriend}
      onBack={onBack}
      onRefreshArchive={friend ? () => void refreshArchive() : null}
      refreshingArchive={refreshingArchive}
    >
      {!friend ? (
        <div className="empty-state-card w-full">
          <ListMusic size={64} strokeWidth={1} />
          <h3 className="mt-4">尚未选择好友</h3>
          <p className="ui-empty-note text-[11px] uppercase tracking-widest mt-2">
            请先选择好友
          </p>
        </div>
      ) : (
        <div className="page-content-wrapper">
          <div className="playlist-page-grid">
            <div className="flex flex-col gap-6 shrink-0 h-full overflow-y-auto friend-list-scroll pr-2">
              <div className="relation-panel !p-6 target-card">
                <div className="flex flex-col gap-4">
                  <div className="flex items-center justify-between gap-4">
                    <div className="flex items-center gap-3 min-w-0">
                      <div className="ui-icon-gold w-10 h-10 rounded-xl flex items-center justify-center shrink-0">
                        <ListMusic size={20} />
                      </div>
                      <div className="min-w-0">
                        <p className="playlist-target-kicker text-[10px] uppercase font-bold tracking-widest">
                          目标控制台
                        </p>
                        <p className="playlist-target-title text-[13px] font-bold truncate">
                          {targetPlaylist}
                        </p>
                      </div>
                    </div>
                  </div>

                  <div className="target-actions">
                    <button
                      onClick={() =>
                        setTargetPanelMode(targetPanelMode === 'switch' ? null : 'switch')
                      }
                      className={`ui-segment-button h-10 w-full rounded-xl text-[10px] font-bold uppercase tracking-widest transition-all border ${
                        targetPanelMode === 'switch' ? 'is-active' : ''
                      }`}
                    >
                      切换
                    </button>
                    <button
                      onClick={() =>
                        setTargetPanelMode(targetPanelMode === 'create' ? null : 'create')
                      }
                      className={`ui-segment-button h-10 w-full rounded-xl text-[10px] font-bold uppercase tracking-widest transition-all border ${
                        targetPanelMode === 'create' ? 'is-active' : ''
                      }`}
                    >
                      新建
                    </button>
                  </div>
                </div>

                <AnimatePresence>
                  {targetPanelMode ? (
                    <motion.div
                      key="expansion-area"
                      initial={{ opacity: 0, height: 0 }}
                      animate={{ opacity: 1, height: 'auto' }}
                      exit={{ opacity: 0, height: 0 }}
                      className="target-shared-panel overflow-visible"
                    >
                      <div className="target-shared-panel-inner friend-list-scroll">
                        {targetPanelMode === 'switch' ? (
                          <div className="space-y-1">
                            <div className="px-2 mb-3">
                              <span className="playlist-section-kicker text-[9px] uppercase font-bold tracking-widest">
                                切换已有歌单
                              </span>
                            </div>
                            {playlistOptions.map((playlist) => (
                              <div
                                key={playlist.id}
                                onClick={() => void handleSwitchTarget(playlist)}
                                className={`playlist-item-row ${
                                  currentPlaylistId === playlist.id ? 'selected' : ''
                                }`}
                              >
                                <span
                                  className={`playlist-row-title text-[12px] font-medium truncate ${
                                    currentPlaylistId === playlist.id ? 'playlist-name' : ''
                                  }`}
                                >
                                  {playlist.name}
                                </span>
                                {currentPlaylistId === playlist.id ? (
                                  <CheckCircle2
                                    size={14}
                                    className="playlist-selection-count"
                                  />
                                ) : null}
                              </div>
                            ))}
                          </div>
                        ) : null}

                        {targetPanelMode === 'create' ? (
                          <div className="space-y-5">
                            <div className="px-2">
                              <span className="playlist-section-kicker text-[9px] uppercase font-bold tracking-widest">
                                新建影子歌单
                              </span>
                            </div>
                            <div className="space-y-2 px-1">
                              <label className="playlist-label-muted text-[10px] font-bold uppercase">
                                歌单名称
                              </label>
                              <input
                                className="search-input-field !h-10 !text-[12px]"
                                placeholder="输入新歌单名称"
                                value={newPlaylistName}
                                onChange={(event) => setNewPlaylistName(event.target.value)}
                              />
                            </div>
                            <div className="flex items-center justify-between px-1">
                              <span className="playlist-label-muted text-[10px] font-bold uppercase">
                                设为私密
                              </span>
                              <div
                                className={`switch-track ${isPrivate ? 'active' : ''}`}
                                onClick={() => setIsPrivate(!isPrivate)}
                              >
                                <motion.div className="switch-thumb" />
                              </div>
                            </div>
                            <div className="grid grid-cols-2 gap-3 mt-2 px-1">
                              <button
                                onClick={() => void handleCreateTarget()}
                                className="ui-action-primary w-full py-3.5 rounded-xl font-bold text-[10px] uppercase tracking-widest active:scale-95 transition-all shadow-lg"
                              >
                                确认创建
                              </button>
                              <button
                                onClick={() => setTargetPanelMode(null)}
                                className="ui-action-secondary w-full py-3.5 rounded-xl border font-bold text-[10px] uppercase tracking-widest active:scale-95 transition-all"
                              >
                                取消
                              </button>
                            </div>
                          </div>
                        ) : null}
                      </div>
                    </motion.div>
                  ) : null}
                </AnimatePresence>
              </div>

              <div className="relation-panel !p-6">
                <div className="flex items-center justify-between border-b ui-divider-soft pb-2 mb-5">
                  <span className="ui-eyebrow text-[10px] uppercase font-bold tracking-[0.2em]">
                    候选歌曲查询
                  </span>
                  <Settings size={12} className="ui-icon-muted" />
                </div>

                <div className="space-y-5">
                  <div className="space-y-2">
                    <label className="ui-eyebrow text-[9px] uppercase tracking-widest font-bold">
                      范围
                    </label>
                    <div className="grid grid-cols-2 gap-2">
                      {['Recent', 'All', 'Pages', 'New'].map((item) => (
                        <button
                          key={item}
                          onClick={() => setRange(item as 'Recent' | 'All' | 'Pages' | 'New')}
                          className={`ui-segment-button px-3 py-2.5 rounded-xl text-[10px] font-bold transition-all border ${
                            range === item ? 'is-active' : ''
                          }`}
                        >
                          {item === 'Recent'
                            ? '最近50首'
                            : item === 'All'
                              ? '全部历史'
                              : item === 'Pages'
                                ? '最近N页'
                                : '新增内容'}
                        </button>
                      ))}
                    </div>
                    {range === 'Pages' ? (
                      <motion.input
                        initial={{ opacity: 0, y: -5 }}
                        animate={{ opacity: 1, y: 0 }}
                        className="search-input-field !h-10 !text-[12px] !pl-4"
                        placeholder="输入页数"
                        value={pageNumber}
                        onChange={(event) => setPageNumber(event.target.value)}
                      />
                    ) : null}
                  </div>

                  <div className="space-y-2">
                    <label className="ui-eyebrow text-[9px] uppercase tracking-widest font-bold">
                      最多歌曲
                    </label>
                    <input
                      className="search-input-field !h-10 !text-[11px] !pl-3"
                      placeholder="留空不限"
                      value={maxCount}
                      onChange={(event) => setMaxCount(event.target.value)}
                    />
                  </div>

                  {range === 'All' ? (
                    <div className="space-y-4">
                      <label className="ui-eyebrow text-[9px] uppercase tracking-widest font-bold">
                        查询方式
                      </label>
                      <div className="flex gap-2">
                        {['All', 'Date', 'Period'].map((item) => (
                          <button
                            key={item}
                            onClick={() => setQueryMethod(item as 'All' | 'Date' | 'Period')}
                            className={`ui-segment-button flex-1 px-3 py-2.5 rounded-xl text-[10px] font-bold transition-all border ${
                              queryMethod === item ? 'is-active' : ''
                            }`}
                          >
                            {item === 'All'
                              ? '全部'
                              : item === 'Date'
                                ? '按日期'
                                : '按时间段'}
                          </button>
                        ))}
                      </div>
                      {queryMethod === 'Date' ? (
                        <DateField value={date1} onChange={setDate1} activeDates={activeDates} />
                      ) : null}
                      {queryMethod === 'Period' ? (
                        <div className="flex flex-col gap-3">
                          <DateField
                            value={date1}
                            onChange={setDate1}
                            activeDates={activeDates}
                          />
                          <DateField
                            value={date2}
                            onChange={setDate2}
                            activeDates={activeDates}
                            minDate={date1}
                          />
                        </div>
                      ) : null}
                    </div>
                  ) : null}

                  <div className="space-y-2">
                    <label className="ui-eyebrow text-[9px] uppercase tracking-widest font-bold">
                      检索词
                    </label>
                    <div className="relative">
                      <Search
                        size={14}
                        className="absolute left-3 top-1/2 -translate-y-1/2 ui-icon-muted"
                      />
                      <input
                        className="search-input-field !h-12 !text-[12px] !pl-10"
                        placeholder="歌名 / 歌手"
                        value={keyword}
                        onChange={(event) => setKeyword(event.target.value)}
                      />
                    </div>
                  </div>

                  <button
                    className="ui-action-primary w-full py-4 rounded-2xl font-bold text-[11px] uppercase tracking-widest transition-all shadow-xl mt-4 active:scale-95 disabled:opacity-60"
                    onClick={() => void handleLoad()}
                    disabled={loading}
                  >
                    {loading ? '查询中...' : '开始查询'}
                  </button>
                </div>
              </div>
            </div>

            <div className="flex-1 flex flex-col gap-6 min-w-0 h-full overflow-hidden">
              <div className="h-[40%] relation-panel flex flex-col overflow-hidden">
                <div className="flex items-center justify-between border-b ui-divider-soft pb-3 mb-4 shrink-0">
                  <div className="flex items-center gap-3">
                    <span className="ui-eyebrow text-[10px] uppercase font-bold tracking-[0.2em]">
                      当前歌单内容
                    </span>
                    <span className="playlist-count-badge px-2 py-0.5 rounded-md text-[10px] font-mono font-bold">
                      {currentTracks.length}
                    </span>
                  </div>
                  <Info size={12} className="ui-icon-subtle" />
                </div>

                <div className="flex-1 overflow-y-auto friend-list-scroll pr-2 space-y-2">
                  {currentTracks.map((item) => (
                    <div
                      key={item.id}
                      className="playlist-current-row flex items-center justify-between p-3 rounded-xl border group transition-colors"
                    >
                      <div className="flex-1 min-w-0">
                        <p className="playlist-row-title text-[12px] font-bold truncate">
                          {item.name}
                        </p>
                        <p className="playlist-row-artist text-[10px] truncate">
                          {item.artist}
                        </p>
                      </div>
                      <span className="playlist-track-meta text-[9px] font-mono uppercase font-bold tracking-widest">
                        {item.genre || 'track'}
                      </span>
                    </div>
                  ))}
                </div>
              </div>

              <div className="flex-1 relation-panel flex flex-col overflow-hidden">
                <div className="flex items-center justify-between border-b ui-divider-soft pb-3 mb-4 shrink-0">
                  <div className="flex items-center gap-4">
                    <span className="ui-eyebrow text-[10px] uppercase font-bold tracking-[0.2em]">
                      候选加载结果
                    </span>
                    {isLoaded && candidates.length > 0 ? (
                      <div className="flex gap-4">
                        <button
                          onClick={handleSelectAll}
                          className="playlist-inline-action text-[9px] font-bold uppercase tracking-widest transition-colors"
                        >
                          全选
                        </button>
                        <button
                          onClick={handleSelectNone}
                          className="playlist-inline-action text-[9px] font-bold uppercase tracking-widest transition-colors"
                        >
                          清空
                        </button>
                        <button
                          onClick={handleInvert}
                          className="playlist-inline-action text-[9px] font-bold uppercase tracking-widest transition-colors"
                        >
                          反选
                        </button>
                      </div>
                    ) : null}
                  </div>
                  <span className="playlist-inline-count text-[11px] font-mono font-bold">
                    {selectedIds.size} / {candidates.length}
                  </span>
                </div>

                <div className="flex-1 overflow-y-auto friend-list-scroll pr-2 space-y-2">
                  {!isLoaded ? (
                    <div className="h-full flex flex-col items-center justify-center ui-empty-ghost gap-3">
                      <Search size={32} strokeWidth={1} />
                      <p className="text-[9px] uppercase font-bold tracking-[0.2em]">
                        待加载候选
                      </p>
                    </div>
                  ) : candidates.length === 0 ? (
                    <div className="h-full flex flex-col items-center justify-center ui-empty-note gap-3">
                      <Info size={32} strokeWidth={1} />
                      <p className="text-[9px] uppercase font-bold tracking-[0.2em]">
                        候选为空
                      </p>
                    </div>
                  ) : (
                    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="space-y-2">
                      {candidates.map((candidate) => (
                        <CandidateRow
                          key={candidate.song_id}
                          candidate={candidate}
                          selected={selectedIds.has(candidate.song_id)}
                          onToggle={toggleSelect}
                        />
                      ))}
                    </motion.div>
                  )}
                </div>

                <div className="shrink-0 pt-4 border-t ui-divider-soft flex items-center justify-between">
                  <div className="flex flex-col">
                    <span className="ui-eyebrow text-[10px] font-bold uppercase tracking-widest">
                      已选分析项目
                    </span>
                    <span className="playlist-selection-count text-[12px] font-mono font-bold">
                      {selectedIds.size} 首歌曲将写入
                    </span>
                  </div>
                  <button
                    disabled={selectedIds.size === 0}
                    className="playlist-build-button px-8 py-4 rounded-2xl font-bold text-[11px] uppercase tracking-widest transition-all hover:scale-[1.02] active:scale-[0.98]"
                    onClick={() => void handleBuild()}
                  >
                    生成影子歌单
                  </button>
                </div>
              </div>

              {buildMessage ? (
                <div className="playlist-message-strip rounded-2xl border px-5 py-3 text-[11px]">
                  {buildMessage}
                </div>
              ) : null}
            </div>
          </div>
        </div>
      )}
    </PageWrapper>
  );
}
