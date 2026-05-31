import type React from 'react';
import { useEffect, useMemo, useRef, useState } from 'react';
import { AnimatePresence, motion } from 'motion/react';
import { Activity, BarChart3, CassetteTape, CheckCircle2, Database, Heart, History, Mail, Pin, RefreshCw, Shield, Users, X } from 'lucide-react';
import { FEATURE_DECOR_CONFIG, HOTSPOT_POLYGONS } from '../constants/homeStage';
import { FriendCapsule, FriendDrawer } from '../components/FriendComponents';
import { ChatInquiryPage } from './ChatInquiryPage';
import { MusicRelationshipPage } from './MusicRelationshipPage';
import { ShadowPlaylistPage } from './ShadowPlaylistPage';
import type { ArchiveSummary, BootstrapSyncStatus, FriendListItemLite, PageKey } from '../types';
import { fetchArchiveSummary, fetchBootstrapSyncStatus, fetchFriendsWithSummary, fetchRecentFriends, pinRecentFriend, rememberFriend, startBootstrapSync, syncFriendRecent, unpinRecentFriend } from '../services/friends';
import { fetchPrivacySettings, flushUnknownSongs, updatePrivacySettings } from '../services/privacy';

function hasCompletedArchive(summary?: ArchiveSummary) {
  const backfillStatus = String(summary?.backfill_status?.status ?? '').trim().toLowerCase();
  return Boolean(
    summary?.newest_archived_time
      || summary?.oldest_archived_time
      || summary?.backfill_status?.last_backfill_at
      || backfillStatus === 'completed',
  );
}

export function HomePage() {
  const [currentPage, setCurrentPage] = useState<PageKey>('home');
  const [friends, setFriends] = useState<FriendListItemLite[]>([]);
  const [selectedFriendUID, setSelectedFriendUID] = useState<string | null>(null);
  const [activeFilter, setActiveFilter] = useState<'Recent' | 'All' | 'Pending'>('All');
  const [friendDrawerOpen, setFriendDrawerOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [hoveredFeature, setHoveredFeature] = useState<string | null>(null);
  const [detailFriendUID, setDetailFriendUID] = useState<string | null>(null);
  const [detailSummary, setDetailSummary] = useState<ArchiveSummary | null>(null);
  const [bootstrapStatus, setBootstrapStatus] = useState<BootstrapSyncStatus | null>(null);
  const [bootstrapError, setBootstrapError] = useState('');
  const [recentFriendUIDs, setRecentFriendUIDs] = useState<string[]>([]);
  const [refreshingArchive, setRefreshingArchive] = useState(false);
  const [showBootstrapStatusCard, setShowBootstrapStatusCard] = useState(false);
  const [showPrivacyPanel, setShowPrivacyPanel] = useState(false);
  const [allowUnknownContribution, setAllowUnknownContribution] = useState(false);
  const [privacyDescription, setPrivacyDescription] = useState('');
  const [privacySaving, setPrivacySaving] = useState(false);
  const [privacyMessage, setPrivacyMessage] = useState('');
  const [unknownQueueSummary, setUnknownQueueSummary] = useState({
    pending: 0,
    uploaded: 0,
    failed: 0,
    total: 0,
    currentUnknownTotal: 0,
  });

  const applyPrivacyPayload = (payload: {
    allow_unknown_song_contribution: boolean;
    description: string;
    queue_summary?: {
      pending?: number;
      uploaded?: number;
      uploaded_deduped?: number;
      failed?: number;
      total?: number;
      current_unknown_total?: number;
    };
  }) => {
    setAllowUnknownContribution(payload.allow_unknown_song_contribution);
    setPrivacyDescription(payload.description);
    setUnknownQueueSummary({
      pending: Number(payload.queue_summary?.pending ?? 0),
      uploaded: Number(payload.queue_summary?.uploaded_deduped ?? payload.queue_summary?.uploaded ?? 0),
      failed: Number(payload.queue_summary?.failed ?? 0),
      total: Number(payload.queue_summary?.total ?? 0),
      currentUnknownTotal: Number(payload.queue_summary?.current_unknown_total ?? 0),
    });
    if (payload.allow_unknown_song_contribution) {
      setPrivacyMessage('');
    } else {
      setPrivacyMessage('已关闭 unknown 歌曲贡献，后续只保存在本地。');
    }
  };

  const drawerRef = useRef<HTMLDivElement>(null);
  const stageRef = useRef<HTMLDivElement>(null);
  const svgRef = useRef<SVGSVGElement>(null);

  const loadFriends = async () => {
    const [result, recentRows] = await Promise.all([fetchFriendsWithSummary(), fetchRecentFriends().catch(() => [])]);
    const recentIds = recentRows.map((item) => item.friend_uid);
    const recentPinnedMap = new Map<string, boolean>(recentRows.map((item) => [item.friend_uid, item.is_pinned] as const));
    const merged = result.map((friend) => ({
      ...friend,
      is_pinned: recentPinnedMap.get(friend.friend_uid) ?? friend.is_pinned,
    }));
    setFriends(merged);
    setRecentFriendUIDs(recentIds);
    const preferredSelected = recentIds[0] || merged[0]?.friend_uid || null;
    setSelectedFriendUID((current) => current || preferredSelected);
  };

  useEffect(() => {
    let cancelled = false;

    const loadInitialData = async () => {
      try {
        const [result, syncStatus, recentList] = await Promise.all([
          fetchFriendsWithSummary(),
          fetchBootstrapSyncStatus().catch(() => null),
          fetchRecentFriends().catch(() => []),
        ]);
        if (cancelled) return;
        const recentIds = recentList.map((item) => item.friend_uid);
        const recentPinnedMap = new Map<string, boolean>(recentList.map((item) => [item.friend_uid, item.is_pinned] as const));
        const merged = result.map((friend) => ({
          ...friend,
          is_pinned: recentPinnedMap.get(friend.friend_uid) ?? friend.is_pinned,
        }));
        setFriends(merged);
        setRecentFriendUIDs(recentIds);
        setSelectedFriendUID((current) => current || recentIds[0] || merged[0]?.friend_uid || null);
        setBootstrapStatus(syncStatus && (syncStatus.running || syncStatus.started_at || syncStatus.completed_friends || syncStatus.total_friends || syncStatus.failed || syncStatus.succeeded) ? syncStatus : null);
        if (syncStatus && (syncStatus.running || syncStatus.failed || syncStatus.total_friends > 0 || syncStatus.completed_friends > 0)) {
          setShowBootstrapStatusCard(true);
        }
      } catch {
        if (cancelled) return;
        setFriends([]);
      }
    };

    void loadInitialData();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    const loadPrivacySettings = async () => {
      try {
        const payload = await fetchPrivacySettings();
        if (cancelled) return;
        applyPrivacyPayload(payload);
      } catch {
        if (cancelled) return;
      }
    };
    void loadPrivacySettings();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (currentPage !== 'home') return;
    let cancelled = false;
    const refreshPrivacySummary = async () => {
      try {
        const payload = await fetchPrivacySettings();
        if (cancelled) return;
        applyPrivacyPayload(payload);
      } catch {
        if (cancelled) return;
      }
    };
    const timer = window.setInterval(() => {
      void refreshPrivacySummary();
    }, 5000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [currentPage]);

  useEffect(() => {
    let cancelled = false;

    const beginBootstrapSync = async () => {
      try {
        if (friends.length > 0) return;
        setBootstrapError('');
        const status = await startBootstrapSync();
        if (cancelled) return;
        setBootstrapStatus(status);
        setShowBootstrapStatusCard(true);
      } catch (error) {
        if (cancelled) return;
        const message = error instanceof Error ? error.message : '自动同步启动失败';
        setBootstrapError(message.includes('/sync/bootstrap') || message.includes('未找到路由') ? '后端还是旧进程，重启 shadow_music_site 后再刷新页面。' : message);
        setShowBootstrapStatusCard(true);
      }
    };

    void beginBootstrapSync();
    return () => {
      cancelled = true;
    };
  }, [friends.length]);

  useEffect(() => {
    if (!bootstrapStatus?.running && !bootstrapStatus?.finished) return;
    let cancelled = false;

    const refreshStatus = async () => {
      try {
        const status = await fetchBootstrapSyncStatus();
        if (cancelled) return;
        const normalizedStatus =
          status.running || status.started_at || status.completed_friends || status.total_friends || status.failed || status.succeeded ? status : null;
        setBootstrapStatus(normalizedStatus);
        if (status.finished) {
          await loadFriends();
        }
      } catch (error) {
        if (cancelled) return;
        setBootstrapError(error instanceof Error ? error.message : '同步状态获取失败');
      }
    };

    void refreshStatus();
    const timer = window.setInterval(() => {
      void refreshStatus();
    }, 2200);

    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [bootstrapStatus?.finished, bootstrapStatus?.running]);

  useEffect(() => {
    if (!bootstrapStatus?.finished || bootstrapStatus.running) return;
    const timer = window.setTimeout(() => {
      setShowBootstrapStatusCard(false);
    }, 4500);
    return () => window.clearTimeout(timer);
  }, [bootstrapStatus?.finished, bootstrapStatus?.running, bootstrapStatus?.finished_at]);

  const filteredFriendsBySearch = useMemo(() => {
    let base = [...friends];
    if (activeFilter === 'Recent') {
      const recentSet = new Set(recentFriendUIDs);
      base = friends
        .filter((friend) => recentSet.has(friend.friend_uid))
        .sort((left, right) => recentFriendUIDs.indexOf(left.friend_uid) - recentFriendUIDs.indexOf(right.friend_uid));
    }
    if (activeFilter === 'Pending') base = friends.filter((friend) => friend.genre_unknown_count > 0);

    if (searchQuery.trim()) {
      const lowered = searchQuery.toLowerCase();
      base = base.filter((friend) => friend.nickname.toLowerCase().includes(lowered) || friend.friend_uid.toLowerCase().includes(lowered));
    }

    return base.sort((left, right) => {
      if (left.is_pinned && !right.is_pinned) return -1;
      if (!left.is_pinned && right.is_pinned) return 1;
      return 0;
    });
  }, [friends, activeFilter, searchQuery]);

  const pinnedFriends = useMemo(() => filteredFriendsBySearch.filter((friend) => friend.is_pinned), [filteredFriendsBySearch]);
  const otherFriends = useMemo(() => filteredFriendsBySearch.filter((friend) => !friend.is_pinned), [filteredFriendsBySearch]);

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (friendDrawerOpen && drawerRef.current && !drawerRef.current.contains(event.target as Node)) {
        const capsule = document.querySelector('.friend-capsule');
        if (capsule && capsule.contains(event.target as Node)) return;
        setFriendDrawerOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [friendDrawerOpen]);

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setFriendDrawerOpen(false);
        setDetailFriendUID(null);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  const togglePinFriend = async (event: React.MouseEvent, uid: string) => {
    event.stopPropagation();
    const current = friends.find((friend) => friend.friend_uid === uid);
    if (!current) return;
    try {
      const recentRows = current.is_pinned ? await unpinRecentFriend(uid) : await pinRecentFriend(uid);
      const recentIds = recentRows.map((item) => item.friend_uid);
      const recentPinnedMap = new Map(recentRows.map((item) => [item.friend_uid, item.is_pinned]));
      setRecentFriendUIDs(recentIds);
      setFriends((prev) =>
        prev.map((friend) => ({
          ...friend,
          is_pinned: recentPinnedMap.get(friend.friend_uid) ?? friend.is_pinned,
        })),
      );
    } catch {
      setFriends((prev) => prev);
    }
  };

  const syncFriend = async (event: React.MouseEvent, uid: string) => {
    event.stopPropagation();
    try {
      await syncFriendRecent(uid, 3, 50);
      const summary = await fetchArchiveSummary(uid);
      const archiveReady = hasCompletedArchive(summary);
      setFriends((prev) =>
        prev.map((friend) =>
          friend.friend_uid === uid
            ? {
                ...friend,
                archive_status: archiveReady ? 'ready' : friend.archive_status,
                friend_sync_status: archiveReady ? 'ok' : friend.friend_sync_status,
                message_count: Number(summary.message_count ?? friend.message_count),
                shared_song_count: Number(summary.shared_song_count ?? friend.shared_song_count),
                genre_unknown_count: Number(summary.unknown_song_count ?? friend.genre_unknown_count),
                last_synced_at: summary.backfill_status?.last_backfill_at ?? friend.last_synced_at,
              }
            : friend,
        ),
      );
    } catch {
      setFriends((prev) => prev.map((friend) => (friend.friend_uid === uid ? { ...friend, friend_sync_status: 'error' } : friend)));
    }
  };

  const refreshArchive = async () => {
    try {
      setRefreshingArchive(true);
      setBootstrapError('');
      const status = await startBootstrapSync();
      setBootstrapStatus(status);
      setShowBootstrapStatusCard(true);
    } catch (error) {
      const message = error instanceof Error ? error.message : '刷新归档失败';
      setBootstrapError(message);
      setShowBootstrapStatusCard(true);
    } finally {
      setRefreshingArchive(false);
    }
  };

  const handleToggleUnknownContribution = async () => {
    try {
      setPrivacySaving(true);
      setPrivacyMessage('');
      const payload = await updatePrivacySettings(!allowUnknownContribution);
      applyPrivacyPayload(payload);
      if (payload.allow_unknown_song_contribution) {
        const flushResult = await flushUnknownSongs().catch(() => null);
        if (!flushResult?.ok) {
          setPrivacyMessage('开启贡献后，待上传 unknown 会在后续归档时继续尝试。');
        } else {
          setPrivacyMessage('');
        }
        const latest = await fetchPrivacySettings().catch(() => null);
        if (latest) {
          applyPrivacyPayload(latest);
        }
      }
    } catch (error) {
      setPrivacyMessage(error instanceof Error ? error.message : '隐私设置保存失败');
    } finally {
      setPrivacySaving(false);
    }
  };

  const selectedFriend = friends.find((friend) => friend.friend_uid === selectedFriendUID);
  const detailFriend = friends.find((friend) => friend.friend_uid === detailFriendUID);

  useEffect(() => {
    let cancelled = false;
    const syncRecentSelection = async () => {
      if (!selectedFriendUID) return;
      try {
        const recentRows = await rememberFriend(selectedFriendUID);
        if (cancelled) return;
        const recentIds = recentRows.map((item) => item.friend_uid);
        const recentPinnedMap = new Map(recentRows.map((item) => [item.friend_uid, item.is_pinned]));
        setRecentFriendUIDs(recentIds);
        setFriends((prev) =>
          prev.map((friend) => ({
            ...friend,
            is_pinned: recentPinnedMap.get(friend.friend_uid) ?? friend.is_pinned,
          })),
        );
      } catch {
        if (cancelled) return;
      }
    };
    void syncRecentSelection();
    return () => {
      cancelled = true;
    };
  }, [selectedFriendUID]);

  useEffect(() => {
    let cancelled = false;
    const loadDetailSummary = async () => {
      if (!detailFriendUID) {
        setDetailSummary(null);
        return;
      }
      try {
        const summary = await fetchArchiveSummary(detailFriendUID);
        if (cancelled) return;
        setDetailSummary(summary);
      } catch {
        if (cancelled) return;
        setDetailSummary(null);
      }
    };
    void loadDetailSummary();
    return () => {
      cancelled = true;
    };
  }, [detailFriendUID]);

  const bootstrapProgress =
    bootstrapStatus && bootstrapStatus.total_friends > 0
      ? Math.min(100, Math.round((bootstrapStatus.completed_friends / bootstrapStatus.total_friends) * 100))
      : 0;
  const showBootstrapPanel =
    currentPage === 'home' &&
    (showBootstrapStatusCard || Boolean(bootstrapError)) &&
    Boolean(bootstrapError || bootstrapStatus?.running || bootstrapStatus?.total_friends || bootstrapStatus?.completed_friends || bootstrapStatus?.failed);
  const bootstrapSummaryText =
    bootstrapStatus?.current_delta_message_count || bootstrapStatus?.current_delta_song_count
      ? `新增 ${bootstrapStatus?.current_delta_message_count ?? 0} 条信息 · ${bootstrapStatus?.current_delta_song_count ?? 0} 首歌曲`
      : bootstrapStatus?.running && !(bootstrapStatus?.total_friends ?? 0)
        ? '正在读取好友列表...'
        : bootstrapStatus?.finished || bootstrapStatus?.running
        ? '已更新到最新'
        : '准备同步好友与聊天归档';
  const bootstrapFooterText =
    bootstrapStatus?.delta_message_count || bootstrapStatus?.delta_song_count
      ? `本轮累计新增 ${bootstrapStatus?.delta_message_count ?? 0} 条信息 · ${bootstrapStatus?.delta_song_count ?? 0} 首歌曲`
      : '本轮已更新到最新';
  const latestBootstrapError =
    bootstrapStatus?.errors && bootstrapStatus.errors.length > 0
      ? bootstrapStatus.errors[bootstrapStatus.errors.length - 1]
      : null;

  return (
    <div className="app-shell bg-[#04070a]">
      <div ref={stageRef} className="stage-image font-sans text-white relative">
        <div className="absolute inset-x-0 inset-y-0 z-0">
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 1.2, ease: 'easeOut' }} className="absolute inset-0 z-0">
            <img src="/shadow-home-collage.png" alt="Shadow Home Collage" className="home-bg-image" />
          </motion.div>

          <div className="home-art-overlay z-[1]" />

          <div className="home-stage-art z-10">
            <img src="/shadow-home-collage.png" alt="Shadow Home Collage" className="home-art-image" />

            <div className={`runner-glow ${hoveredFeature === 'relation' ? 'active' : ''}`} />

            <svg className="absolute inset-0 w-full h-full pointer-events-none opacity-0" viewBox="0 0 1672 941" preserveAspectRatio="xMidYMid meet">
              <defs>
                {Object.entries(HOTSPOT_POLYGONS).map(([key]) => (
                  <clipPath id={`clip-${key}`} key={`clip-${key}`}>
                    <polygon points={HOTSPOT_POLYGONS[key as keyof typeof HOTSPOT_POLYGONS].points} />
                  </clipPath>
                ))}
              </defs>
            </svg>

            <svg className="absolute inset-0 w-full h-full pointer-events-none z-10" viewBox="0 0 1672 941" preserveAspectRatio="xMidYMid meet">
              {Object.entries(HOTSPOT_POLYGONS).map(([key, config]) => (
                <g clipPath={`url(#clip-${key})`} key={`hover-${key}`} className="feature-clip-group">
                  <polygon points={config.points} className={`feature-highlight active-${key} ${hoveredFeature === key ? 'active' : ''}`} />
                </g>
              ))}
            </svg>

            {Object.entries(HOTSPOT_POLYGONS).map(([key, polyConfig]) => {
              const config = FEATURE_DECOR_CONFIG[key as keyof typeof FEATURE_DECOR_CONFIG];
              if (!config) return null;

              return (
                <div
                  key={`clip-container-${key}`}
                  className="absolute inset-0 pointer-events-none z-30"
                  style={{
                    clipPath: `polygon(${polyConfig.points
                      .split(' ')
                      .map((point) => {
                        const [x, y] = point.split(',').map(Number);
                        return `${(x / 16.72).toFixed(2)}% ${(y / 9.41).toFixed(2)}%`;
                      })
                      .join(', ')})`,
                    background: 'transparent',
                  }}
                >
                  <AnimatePresence>
                    {hoveredFeature === key && (
                      <motion.div key={`${key}-icon-wrapper`} className="absolute" style={{ left: `${config.icon.x / 16.72}%`, top: `${config.icon.y / 9.41}%` }}>
                        <motion.div
                          initial={{
                            x: key === 'relation' ? '-220%' : key === 'playlist' ? '-180%' : '-50%',
                            y: key === 'chat' ? '-180%' : key === 'playlist' ? '-140%' : '-50%',
                            opacity: 0,
                            rotate: config.icon.rotate - 15,
                            scale: 0.82,
                          }}
                          animate={{ x: '-50%', y: '-50%', opacity: 1, rotate: config.icon.rotate, scale: config.icon.scale }}
                          exit={{
                            x: key === 'relation' ? '-200%' : key === 'playlist' ? '-160%' : '-50%',
                            y: key === 'chat' ? '-160%' : key === 'playlist' ? '-120%' : '-50%',
                            opacity: 0,
                            transition: { duration: 0.2, ease: 'easeIn' },
                          }}
                          transition={{ type: 'spring', damping: 20, stiffness: 120, delay: 0.04 }}
                          className="collage-sticker flex items-center justify-center"
                          style={{ width: 50, height: 50 }}
                        >
                          {key === 'chat' && <Mail size={22} strokeWidth={1.5} />}
                          {key === 'relation' && <Users size={22} strokeWidth={1.5} />}
                          {key === 'playlist' && (
                            <div className="flex flex-col items-center gap-1">
                              <CassetteTape size={24} strokeWidth={1.5} />
                              <div className="w-5 h-0.5 bg-black/10 rounded-full" />
                            </div>
                          )}
                        </motion.div>
                      </motion.div>
                    )}
                  </AnimatePresence>
                </div>
              );
            })}

            {Object.entries(FEATURE_DECOR_CONFIG).map(([key, config]) => (
              <div key={`label-layer-${key}`} className="absolute inset-0 pointer-events-none z-40">
                <AnimatePresence>
                  {hoveredFeature === key && (
                    <motion.div
                      key={`${key}-label`}
                      initial={{
                        left: `${config.label.x / 16.72}%`,
                        top: `${config.label.y / 9.41}%`,
                        opacity: 0,
                        y: 10,
                        scale: 0.96,
                      }}
                      animate={{ opacity: 1, y: 0, scale: config.label.scale }}
                      exit={{ opacity: 0, y: 5, transition: { duration: 0.16 } }}
                      transition={{ duration: 0.28, ease: [0.16, 1, 0.3, 1] }}
                      className="absolute z-30 pointer-events-none"
                      style={{ translateX: '-50%', translateY: '-50%', transformOrigin: 'center center', rotate: `${config.label.rotate}deg` }}
                    >
                      <div className="feature-label">{HOTSPOT_POLYGONS[key as keyof typeof HOTSPOT_POLYGONS].name}</div>
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>
            ))}

            <svg ref={svgRef} className="matrix-layer z-50" viewBox="0 0 1672 941" preserveAspectRatio="xMidYMid meet">
              {Object.entries(HOTSPOT_POLYGONS).map(([key, config]) => (
                <polygon
                  key={`hit-${key}`}
                  points={config.points}
                  className="hotspot-hitarea"
                  onPointerEnter={() => setHoveredFeature(key)}
                  onPointerLeave={() => setHoveredFeature(null)}
                  onClick={() => {
                    if (key === 'chat' || key === 'relation' || key === 'playlist') {
                      setCurrentPage(key as PageKey);
                    }
                  }}
                />
              ))}
            </svg>
          </div>
        </div>

        {currentPage === 'home' && (
          <>
            <div
              className="absolute right-36 top-[22px] z-[90]"
              onMouseEnter={() => setShowPrivacyPanel(true)}
              onMouseLeave={() => setShowPrivacyPanel(false)}
            >
              <div className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-black/45 px-3 py-2 text-white/82 shadow-xl backdrop-blur-md">
                <div className="rounded-full border border-white/10 bg-white/5 p-1.5 text-white/72">
                  <Shield size={12} />
                </div>
                <div className="text-[11px] font-semibold tracking-[0.14em] text-white/86">未知数据贡献授权</div>
              </div>

              <AnimatePresence>
                {showPrivacyPanel && (
                  <motion.div
                    initial={{ opacity: 0, y: -8, scale: 0.98 }}
                    animate={{ opacity: 1, y: 0, scale: 1 }}
                    exit={{ opacity: 0, y: -6, scale: 0.985 }}
                    transition={{ duration: 0.22, ease: 'easeOut' }}
                    className="absolute right-0 top-[calc(100%+10px)] w-[360px] rounded-[22px] border border-white/10 bg-black/45 px-4 py-3 text-white/80 shadow-xl backdrop-blur-md"
                  >
                    <div className="flex items-start gap-3">
                      <div className="mt-0.5 rounded-full border border-white/10 bg-white/5 p-2 text-white/70">
                        <Shield size={12} />
                      </div>
                      <div className="min-w-0">
                        <div className="text-[11px] font-semibold tracking-[0.16em] text-white/86">未知数据贡献授权</div>
                        <p className="mt-1 text-[11px] leading-5 text-white/48">
                          {privacyDescription || '开启后仅上传未知歌曲的歌名、歌手、专辑，不上传聊天、Cookie、好友 UID 或完整歌单。'}
                        </p>
                        <div className="mt-3 flex items-center gap-3">
                          <button
                            type="button"
                            onClick={() => void handleToggleUnknownContribution()}
                            disabled={privacySaving}
                            className={`rounded-full border px-3 py-1.5 text-[10px] font-semibold tracking-[0.14em] transition ${allowUnknownContribution ? 'border-emerald-300/20 bg-emerald-400/15 text-emerald-50 hover:bg-emerald-400/20' : 'border-white/10 bg-white/6 text-white/72 hover:bg-white/10'} disabled:cursor-not-allowed disabled:opacity-60`}
                          >
                            {privacySaving ? '保存中' : allowUnknownContribution ? '已开启' : '未开启'}
                          </button>
                        </div>
                        {allowUnknownContribution ? (
                          <div className="mt-3 flex flex-col gap-1 text-[10px] text-white/52">
                            <span>待上传 {unknownQueueSummary.pending} 条</span>
                            <span>已上传（去重） {unknownQueueSummary.uploaded} 条</span>
                            <span>失败 {unknownQueueSummary.failed} 条</span>
                            <span>本地未知 {unknownQueueSummary.currentUnknownTotal} 条</span>
                          </div>
                        ) : null}
                        {privacyMessage ? <div className="mt-2 text-[10px] text-white/42">{privacyMessage}</div> : null}
                      </div>
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>

            <button
              onClick={() => void refreshArchive()}
              disabled={refreshingArchive || Boolean(bootstrapStatus?.running)}
              className="absolute right-6 top-6 z-[90] flex items-center gap-2 rounded-full border border-white/10 bg-black/45 px-4 py-2 text-[11px] font-semibold tracking-[0.16em] text-white/80 shadow-xl backdrop-blur-md transition hover:bg-black/60 hover:text-white disabled:cursor-not-allowed disabled:opacity-50"
            >
              <RefreshCw size={13} className={refreshingArchive || bootstrapStatus?.running ? 'animate-spin' : ''} />
              刷新归档
            </button>
          </>
        )}

        {currentPage === 'home' && <FriendCapsule selectedFriend={selectedFriend} active={friendDrawerOpen} onClick={() => setFriendDrawerOpen(!friendDrawerOpen)} />}

        <AnimatePresence>
          {currentPage === 'home' && showBootstrapPanel && (
          <motion.div
            className="absolute right-6 bottom-6 z-[95] w-[360px] rounded-[28px] border border-white/10 bg-black/45 p-5 text-white shadow-2xl backdrop-blur-xl"
            initial={{ opacity: 0, y: 14, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 14, scale: 0.98 }}
            transition={{ duration: 0.36, ease: 'easeOut' }}
          >
            <div className="flex items-center justify-between gap-3">
              <div>
                <div className="text-sm font-semibold tracking-wide">{bootstrapStatus?.running ? '好友归档更新中' : '好友归档结果'}</div>
                <div className="mt-1 text-xs text-white/55">
                  {bootstrapError
                    ? bootstrapError
                    : bootstrapStatus?.running
                      ? `正在同步 ${bootstrapStatus.current_friend_name || bootstrapStatus.current_friend_uid || '好友数据'}`
                      : bootstrapStatus?.finished
                        ? bootstrapStatus.failed > 0
                          ? `完成 ${bootstrapStatus.completed_friends}/${bootstrapStatus.total_friends} 位好友，失败 ${bootstrapStatus.failed} 位`
                          : `已完成 ${bootstrapStatus.completed_friends}/${bootstrapStatus.total_friends} 位好友归档`
                        : bootstrapSummaryText}
                </div>
                {!bootstrapError && (bootstrapStatus?.running || bootstrapStatus?.finished) && (
                  <div className="mt-2 text-[11px] text-white/38">{bootstrapSummaryText}</div>
                )}
              </div>
              <div className="text-right text-[11px] text-white/45">
                <div>{bootstrapStatus?.completed_friends ?? 0}/{bootstrapStatus?.total_friends ?? 0}</div>
                <div>{bootstrapStatus?.running ? '同步中' : bootstrapStatus?.failed ? '有异常' : '完成'}</div>
              </div>
            </div>

            <div className="mt-4 h-2 overflow-hidden rounded-full bg-white/10">
              <div
                className="h-full rounded-full bg-white transition-all duration-500"
                style={{ width: `${bootstrapProgress}%` }}
              />
            </div>

            <div className="mt-4 flex items-center gap-4 text-[11px] text-white/55">
              <span>成功 {bootstrapStatus?.succeeded ?? 0}</span>
              <span>失败 {bootstrapStatus?.failed ?? 0}</span>
              <span>{bootstrapFooterText}</span>
            </div>

            {latestBootstrapError && (
              <div className="mt-4 rounded-2xl border border-red-400/10 bg-red-500/5 px-4 py-3">
                <div className="text-[11px] font-semibold text-red-100/90">
                  失败好友：{latestBootstrapError.friend_name || latestBootstrapError.friend_uid || '未知好友'}
                </div>
                <div className="mt-1 text-[11px] leading-relaxed text-red-100/55">
                  {latestBootstrapError.error || '未返回具体失败原因'}
                </div>
              </div>
            )}
          </motion.div>
          )}
        </AnimatePresence>

        <AnimatePresence>
          {currentPage === 'home' && friendDrawerOpen && (
            <FriendDrawer
              drawerRef={drawerRef}
              pinnedFriends={pinnedFriends}
              otherFriends={otherFriends}
              selectedFriendId={selectedFriendUID}
              onSelect={(uid) => {
                setSelectedFriendUID(uid);
                setFriendDrawerOpen(false);
              }}
              onTogglePin={togglePinFriend}
              onClose={() => setFriendDrawerOpen(false)}
              activeFilter={activeFilter}
              setActiveFilter={setActiveFilter}
              searchQuery={searchQuery}
              setSearchQuery={setSearchQuery}
            />
          )}
        </AnimatePresence>

        <AnimatePresence mode="wait">
          {currentPage === 'chat' && <ChatInquiryPage friend={selectedFriend} friends={friends} selectedFriendId={selectedFriendUID} onSelectFriend={setSelectedFriendUID} onBack={() => setCurrentPage('home')} />}
          {currentPage === 'relation' && <MusicRelationshipPage friend={selectedFriend} friends={friends} selectedFriendId={selectedFriendUID} onSelectFriend={setSelectedFriendUID} onBack={() => setCurrentPage('home')} />}
          {currentPage === 'playlist' && <ShadowPlaylistPage friend={selectedFriend} friends={friends} selectedFriendId={selectedFriendUID} onSelectFriend={setSelectedFriendUID} onBack={() => setCurrentPage('home')} />}
        </AnimatePresence>

        <AnimatePresence>
          {detailFriendUID && detailFriend && (
            <>
              <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={() => setDetailFriendUID(null)} className="absolute inset-0 z-[100] bg-black/60 backdrop-blur-md" />
              <motion.div initial={{ x: '100%', opacity: 0.5 }} animate={{ x: 0, opacity: 1 }} exit={{ x: '100%', opacity: 0 }} transition={{ type: 'spring', damping: 28, stiffness: 220 }} className="absolute top-0 right-0 bottom-0 z-[110] w-[440px] bg-[#080d14] border-l border-white/5 shadow-[-20px_0_100px_rgba(0,0,0,0.8)] flex flex-col">
                <div className="h-full flex flex-col relative overflow-hidden">
                  <div className="absolute top-0 right-0 p-8 z-10">
                    <button onClick={() => setDetailFriendUID(null)} className="p-2.5 rounded-full text-white/20 hover:text-white hover:bg-white/5 transition-all">
                      <X size={20} />
                    </button>
                  </div>

                  <div className="p-10 pt-16 flex flex-col items-center">
                    <div className="relative group mb-6">
                      {detailFriend.avatar_url ? <img src={detailFriend.avatar_url} className="w-24 h-24 rounded-[32px] bg-white/5 border border-white/10 shadow-2xl transition-transform duration-500 group-hover:scale-105 object-cover" /> : <div className="w-24 h-24 rounded-[32px] bg-white/[0.03] border border-white/10 shadow-2xl" />}
                      <div className={`absolute -bottom-1 -right-1 w-6 h-6 rounded-full border-4 border-[#080d14] ${detailFriend.friend_sync_status === 'ok' ? 'bg-green-500' : 'bg-amber-500'}`} />
                    </div>

                    <div className="flex flex-col items-center text-center">
                      <div className="flex items-center gap-3 mb-1">
                        <h2 className="text-2xl font-bold text-white tracking-tight">{detailFriend.nickname}</h2>
                        <button onClick={(event) => togglePinFriend(event, detailFriend.friend_uid)} className="p-2 rounded-xl bg-white/5 hover:bg-white/10 text-white/40 hover:text-white transition-colors">
                          {detailFriend.is_pinned ? <Pin size={16} className="fill-current text-white/60" /> : <Pin size={16} />}
                        </button>
                      </div>
                      <span className="text-[10px] text-white/20 uppercase tracking-[0.3em] font-mono font-bold">UID: {detailFriend.friend_uid}</span>
                    </div>
                  </div>

                  <div className="flex-1 overflow-y-auto friend-list-scroll friend-drawer-list px-10 pb-10 space-y-10">
                    <div className="grid grid-cols-2 gap-4">
                      <div className="p-5 rounded-2xl bg-white/[0.03] border border-white/5 space-y-1 hover:bg-white/[0.05] transition-colors group cursor-default">
                        <span className="text-[9px] uppercase tracking-widest text-white/20 font-bold group-hover:text-white/40 transition-colors">存档状态</span>
                        <div className="flex items-center gap-2">
                          <Database size={12} className="text-green-400/40" />
                          <span className="text-[11px] font-bold text-white/80 uppercase tracking-wider">{detailFriend.archive_status === 'ready' ? '就绪' : detailFriend.archive_status}</span>
                        </div>
                      </div>
                      <div className="p-5 rounded-2xl bg-white/[0.03] border border-white/5 space-y-1 hover:bg-white/[0.05] transition-colors group cursor-default">
                        <span className="text-[9px] uppercase tracking-widest text-white/20 font-bold group-hover:text-white/40 transition-colors">同步状态</span>
                        <div className="flex items-center gap-2">
                          <Activity size={12} className="text-blue-400/40" />
                          <span className="text-[11px] font-bold text-white/80 uppercase tracking-wider">{detailFriend.friend_sync_status === 'ok' ? '正常' : detailFriend.friend_sync_status === 'error' ? '错误' : '待同步'}</span>
                        </div>
                      </div>
                      <div className="p-5 rounded-2xl bg-white/[0.03] border border-white/5 space-y-1 hover:bg-white/[0.05] transition-colors group cursor-default">
                        <span className="text-[9px] uppercase tracking-widest text-white/20 font-bold group-hover:text-white/40 transition-colors">共有歌曲</span>
                        <div className="flex items-center gap-2 text-white/80">
                          <Heart size={14} className="fill-current text-red-500/40 group-hover:scale-110 transition-transform" />
                          <span className="text-2xl font-mono font-bold leading-none tracking-tighter">{detailSummary?.shared_song_count ?? detailFriend.shared_song_count}</span>
                        </div>
                      </div>
                      <div className="p-5 rounded-2xl bg-white/[0.03] border border-white/5 space-y-1 hover:bg-white/[0.05] transition-colors group cursor-default">
                        <span className="text-[9px] uppercase tracking-widest text-white/20 font-bold group-hover:text-white/40 transition-colors">未知曲目</span>
                        <div className="flex items-center gap-2 text-white/80">
                          <BarChart3 size={14} className="text-amber-500/40 transition-colors" />
                          <span className="text-2xl font-mono font-bold leading-none tracking-tighter">{detailSummary?.unknown_song_count ?? detailFriend.genre_unknown_count}</span>
                          {Number(detailSummary?.unknown_song_count ?? detailFriend.genre_unknown_count) > 0 && <span className="w-2 h-2 rounded-full bg-amber-500 animate-pulse ml-1" />}
                        </div>
                      </div>
                    </div>

                    <div className="space-y-6">
                      <div className="flex items-center justify-between border-b border-white/5 pb-2">
                        <h3 className="text-[10px] uppercase tracking-[0.2em] font-bold text-white/30">存档时间轴</h3>
                        <History size={12} className="text-white/20" />
                      </div>
                      <div className="space-y-4">
                        <div className="flex items-center justify-between group">
                          <span className="text-xs text-white/40 group-hover:text-white/60 transition-colors">上次同步时间</span>
                          <span className="text-[11px] font-mono text-white/50 bg-white/[0.03] px-2 py-0.5 rounded border border-white/5 group-hover:bg-white/5 transition-colors">{detailFriend.last_synced_at || detailSummary?.backfill_status?.last_backfill_at || '暂无'}</span>
                        </div>
                        <div className="flex items-center justify-between group">
                          <span className="text-xs text-white/40 group-hover:text-white/60 transition-colors">最后消息往来</span>
                          <span className="text-[11px] font-mono text-white/50 bg-white/[0.03] px-2 py-0.5 rounded border border-white/5 group-hover:bg-white/5 transition-colors">{detailSummary?.last_message_at || '暂无'}</span>
                        </div>
                        <div className="flex items-center justify-between group">
                          <span className="text-xs text-white/40 group-hover:text-white/60 transition-colors">归档范围</span>
                          <span className="text-[11px] font-mono text-white/50 bg-white/[0.03] px-2 py-0.5 rounded border border-white/5 group-hover:bg-white/5 transition-colors">
                            {detailSummary?.oldest_archived_time && detailSummary?.newest_archived_time
                              ? `${detailSummary.oldest_archived_time} ~ ${detailSummary.newest_archived_time}`
                              : '暂无'}
                          </span>
                        </div>
                        <div className="flex items-center justify-between group">
                          <span className="text-xs text-white/40 group-hover:text-white/60 transition-colors">消息总数</span>
                          <span className="text-[11px] font-mono text-white/50 bg-white/[0.03] px-2 py-0.5 rounded border border-white/5 group-hover:bg-white/5 transition-colors">{detailSummary?.message_count ?? 0}</span>
                        </div>
                        <div className="flex items-center justify-between group">
                          <span className="text-xs text-white/40 group-hover:text-white/60 transition-colors">回填状态</span>
                          <span className="text-[11px] font-mono text-white/50 bg-white/[0.03] px-2 py-0.5 rounded border border-white/5 group-hover:bg-white/5 transition-colors">{detailSummary?.backfill_status?.status || '未回填'}</span>
                        </div>
                      </div>
                    </div>

                    <div className="p-6 rounded-3xl bg-blue-500/5 border border-blue-500/10 flex items-center gap-5 hover:bg-blue-500/10 transition-colors cursor-default">
                      <div className="w-12 h-12 rounded-2xl bg-blue-500/10 flex items-center justify-center text-blue-400 shrink-0">
                        <CheckCircle2 size={24} strokeWidth={1.5} />
                      </div>
                      <div>
                        <p className="text-sm font-bold text-white/90">分析就绪</p>
                        <p className="text-[11px] text-white/30 leading-relaxed font-medium">
                          {detailSummary?.active_dates?.length
                            ? `当前共有 ${detailSummary.active_dates.length} 个活跃日期，归档数据可直接供聊天记录、音乐关系和影子歌单使用。`
                            : '当前好友的分享归档可直接供聊天记录、音乐关系和影子歌单使用。'}
                        </p>
                      </div>
                    </div>
                  </div>

                  <div className="p-10 border-t border-white/5 bg-[#0a111a]/50 backdrop-blur-xl">
                    <div className="grid grid-cols-2 gap-4">
                      <button onClick={(event) => void syncFriend(event, detailFriend.friend_uid)} className="flex items-center justify-center gap-2.5 py-4 rounded-2xl bg-white text-black font-bold text-[11px] uppercase tracking-widest hover:bg-white/90 transition-all shadow-xl active:scale-95">
                        <RefreshCw size={14} className="hover:rotate-180 transition-transform duration-500" />
                        同步存档
                      </button>
                      <button className="flex items-center justify-center gap-2.5 py-4 rounded-2xl bg-white/[0.05] border border-white/10 text-white font-bold text-[11px] uppercase tracking-widest hover:bg-white/[0.08] transition-all active:scale-95">进入语境</button>
                    </div>
                    <div className="mt-6 flex flex-wrap justify-center gap-6">
                      <button className="text-[10px] font-bold uppercase tracking-widest text-white/20 hover:text-white/60 transition-colors flex items-center gap-2">
                        <BarChart3 size={12} />
                        完整分析
                      </button>
                      <span className="w-1 h-1 rounded-full bg-white/5 self-center" />
                      <button className="text-[10px] font-bold uppercase tracking-widest text-white/20 hover:text-white/60 transition-colors flex items-center gap-2">
                        <Database size={12} />
                        重写数据
                      </button>
                    </div>
                  </div>
                </div>
              </motion.div>
            </>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}
