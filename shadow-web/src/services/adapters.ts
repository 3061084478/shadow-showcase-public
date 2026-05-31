import type {
  ArchiveSummary,
  ChatMessage,
  FriendListItemLite,
  GlobalSocialStructureBlock,
  GlobalStructureGraph,
  GlobalStructureMetric,
  GlobalTop3Block,
  GenreBalanceItem,
  MusicRelationData,
  RankedFriendMetric,
  ShadowCandidate,
  ShadowTarget,
  ShadowTargetOption,
  TopArtistItem,
} from '../types';

function toArray(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.map((item) => String(item ?? '').trim()).filter(Boolean);
}

function hasCompletedArchive(summary?: ArchiveSummary) {
  const backfillStatus = String(summary?.backfill_status?.status ?? '').trim().toLowerCase();
  return Boolean(
    summary?.newest_archived_time
      || summary?.oldest_archived_time
      || summary?.backfill_status?.last_backfill_at
      || backfillStatus === 'completed',
  );
}

function normalizeSyncStatus(friend: Record<string, unknown>, summary?: ArchiveSummary): FriendListItemLite['friend_sync_status'] {
  if (!hasCompletedArchive(summary)) return 'needs_sync';
  return 'ok';
}

function normalizeArchiveStatus(summary?: ArchiveSummary): FriendListItemLite['archive_status'] {
  if (!hasCompletedArchive(summary)) return 'never_archived';
  return 'ready';
}

export function adaptFriend(friend: Record<string, unknown>, summary?: ArchiveSummary): FriendListItemLite {
  return {
    friend_uid: String(friend.uid ?? '').trim(),
    nickname: String(friend.nickname ?? friend.friend_name ?? '未命名好友').trim() || '未命名好友',
    avatar_url: String(friend.avatar_url ?? '').trim() || null,
    is_pinned: Boolean(friend.is_pinned),
    archive_status: normalizeArchiveStatus(summary),
    friend_sync_status: normalizeSyncStatus(friend, summary),
    last_synced_at:
      typeof friend.synced_at === 'string' && friend.synced_at.trim()
        ? friend.synced_at.trim()
        : typeof friend.last_used_at === 'string' && friend.last_used_at.trim()
          ? friend.last_used_at.trim()
          : null,
    message_count: Number(summary?.message_count ?? friend.message_count ?? 0),
    shared_song_count: Number(summary?.shared_song_count ?? friend.shared_song_count ?? 0),
    genre_unknown_count: Number(summary?.unknown_song_count ?? friend.genre_unknown_count ?? 0),
  };
}

export function adaptChatRow(row: Record<string, unknown>, friendName: string): ChatMessage {
  const rawType = String(row.msg_type ?? 'unknown').toLowerCase();
  const type: ChatMessage['type'] =
    rawType === 'song' || rawType === 'text' || rawType === 'image' || rawType === 'video'
      ? rawType
      : 'unknown';
  const isSong = type === 'song';
  const artistNames = toArray(row.artist_names);
  const artistText =
    artistNames.length > 0 ? artistNames.join(' / ') : String(row.artist_name ?? '').trim();

  return {
    id: String(row.msg_id ?? ''),
    sender: String(row.direction ?? '') === 'self' ? 'me' : 'friend',
    type,
    content: String(row.text_content ?? '').trim() || undefined,
    timestamp: String(row.msg_time_str ?? ''),
    song: isSong
      ? {
          id: String(row.song_id ?? '').trim() || undefined,
          name: String(row.song_name ?? '').trim(),
          artist: artistText,
          album: String(row.album_name ?? '').trim(),
          genre: String(row.genre_label ?? '').trim(),
          status: String(row.genre_status ?? '').trim() === 'known' ? 'known' : 'unknown',
          publish_time: String(row.publish_time ?? '').trim() || undefined,
        }
      : undefined,
  };
}

function adaptDistributionItems(items: unknown): { name: string; count: number; ratio?: number }[] {
  if (!Array.isArray(items)) return [];
  return items
    .map((item) => {
      if (!item || typeof item !== 'object') return null;
      const row = item as Record<string, unknown>;
      return {
        name: String(row.name ?? ''),
        count: Number(row.count ?? 0),
        ratio: typeof row.ratio === 'number' ? row.ratio : undefined,
      };
    })
    .filter((item) => Boolean(item?.name)) as { name: string; count: number; ratio?: number }[];
}

function adaptGenreOverlapBalance(
  raw: Record<string, unknown> | null | undefined,
): GenreBalanceItem[] {
  const genres = Array.isArray(raw?.genres) ? raw.genres : [];
  return genres
    .map((item) => {
      if (!item || typeof item !== 'object') return null;
      const row = item as Record<string, unknown>;
      return {
        genre: String(row.genre_label ?? ''),
        me: Number(row.my_count ?? 0),
        friend: Number(row.friend_count ?? 0),
      };
    })
    .filter((item): item is GenreBalanceItem => Boolean(item?.genre));
}

function adaptTopArtists(items: unknown): TopArtistItem[] {
  if (!Array.isArray(items)) return [];
  return items
    .map((item): TopArtistItem | null => {
      if (!item || typeof item !== 'object') return null;
      const row = item as Record<string, unknown>;
      const name = String(row.name ?? '').trim();
      if (!name) return null;
      return {
        name,
        count: Number(row.count ?? 0),
        me: Number(row.my_count ?? row.me ?? 0),
        friend: Number(row.friend_count ?? row.friend ?? 0),
      };
    })
    .filter((item): item is TopArtistItem => Boolean(item?.name));
}

function adaptTimelineNodes(items: unknown): { title: string; period: string; description: string }[] {
  if (!Array.isArray(items)) return [];
  return items
    .map((item) => {
      if (!item || typeof item !== 'object') return null;
      const row = item as Record<string, unknown>;
      return {
        title: String(row.title ?? '').trim(),
        period: String(row.period ?? '').trim(),
        description: String(row.description ?? '').trim(),
      };
    })
    .filter((item): item is { title: string; period: string; description: string } => Boolean(item?.title));
}

function adaptTrendSeries(items: unknown) {
  if (!Array.isArray(items)) return [];
  return items
    .map((item) => {
      if (!item || typeof item !== 'object') return null;
      const row = item as Record<string, unknown>;
      return {
        period: String(row.period ?? '').trim(),
        messageCountRaw: Number(row.message_count_raw ?? 0),
        distinctSongCount: Number(row.distinct_song_count ?? 0),
        myDistinctSongCount: Number(row.my_distinct_song_count ?? 0),
        friendDistinctSongCount: Number(row.friend_distinct_song_count ?? 0),
        phaseLabel: String(row.phase_label ?? '').trim(),
      };
    })
    .filter((item): item is {
      period: string;
      messageCountRaw: number;
      distinctSongCount: number;
      myDistinctSongCount: number;
      friendDistinctSongCount: number;
      phaseLabel: string;
    } => Boolean(item?.period));
}

function adaptEvidenceTracks(items: unknown) {
  if (!Array.isArray(items)) return [];
  return items
    .map((item) => {
      if (!item || typeof item !== 'object') return null;
      const row = item as Record<string, unknown>;
      return {
        title: String(row.title ?? '').trim(),
        period: String(row.period ?? '').trim(),
        songName: String(row.song_name ?? '').trim(),
        artistNames: toArray(row.artist_names),
        genreLabel: String(row.genre_label ?? '').trim(),
      };
    })
    .filter((item): item is {
      title: string;
      period: string;
      songName: string;
      artistNames: string[];
      genreLabel: string;
    } => Boolean(item?.title));
}

function adaptHeatmapHours(items: unknown) {
  if (!Array.isArray(items)) return [];
  return items
    .map((item) => {
      if (!item || typeof item !== 'object') return null;
      const row = item as Record<string, unknown>;
      return {
        hour: Number(row.hour ?? 0),
        count: Number(row.count ?? 0),
        bucket: String(row.bucket ?? '').trim(),
      };
    })
    .filter((item): item is { hour: number; count: number; bucket: string } => Number.isFinite(item?.hour) && Boolean(item?.bucket));
}

function adaptHeatmapBuckets(items: unknown) {
  if (!Array.isArray(items)) return [];
  return items
    .map((item) => {
      if (!item || typeof item !== 'object') return null;
      const row = item as Record<string, unknown>;
      return {
        label: String(row.label ?? '').trim(),
        count: Number(row.count ?? 0),
        ratio: Number(row.ratio ?? 0),
      };
    })
    .filter((item): item is { label: string; count: number; ratio: number } => Boolean(item?.label));
}

function adaptRankedFriends(items: unknown): RankedFriendMetric[] {
  if (!Array.isArray(items)) return [];
  return items
    .map((item) => {
      if (!item || typeof item !== 'object') return null;
      const row = item as Record<string, unknown>;
      const uid = String(row.uid ?? '').trim();
      const nickname = String(row.nickname ?? uid).trim();
      if (!uid && !nickname) return null;
      return {
        uid,
        nickname: nickname || uid,
        avatar_url: String(row.avatar_url ?? '').trim() || null,
        value: Number(row.value ?? 0),
      };
    })
    .filter((item): item is RankedFriendMetric => Boolean(item?.nickname));
}

function adaptGlobalStructureMetric(raw: unknown, fallbackLabel: string): GlobalStructureMetric {
  const row = raw && typeof raw === 'object' ? (raw as Record<string, unknown>) : {};
  return {
    label: String(row.label ?? fallbackLabel).trim() || fallbackLabel,
    summary: String(row.summary ?? '待形成').trim() || '待形成',
  };
}

function adaptGlobalStructureGraph(raw: unknown, fallbackTitle: string): GlobalStructureGraph {
  const row = raw && typeof raw === 'object' ? (raw as Record<string, unknown>) : {};
  return {
    title: String(row.title ?? fallbackTitle).trim() || fallbackTitle,
    summary: String(row.summary ?? '').trim(),
    nodes: adaptRankedFriends(row.nodes),
  };
}

function adaptGlobalTop3(raw: unknown): GlobalTop3Block {
  const row = raw && typeof raw === 'object' ? (raw as Record<string, unknown>) : {};
  return {
    chatTop3: adaptRankedFriends(row.chat_top3),
    songTop3: adaptRankedFriends(row.song_top3),
    temperatureTop3: adaptRankedFriends(row.temperature_top3),
  };
}

function adaptGlobalSocialStructure(raw: unknown): GlobalSocialStructureBlock {
  const row = raw && typeof raw === 'object' ? (raw as Record<string, unknown>) : {};
  return {
    musicIoType: adaptGlobalStructureMetric(row.music_io_type, '音乐输入/输出类型'),
    chatIoType: adaptGlobalStructureMetric(row.chat_io_type, '聊天输入/输出类型'),
    musicCircleDensity: adaptGlobalStructureMetric(row.music_circle_density, '音乐圈层浓度'),
    chatCircleDensity: adaptGlobalStructureMetric(row.chat_circle_density, '聊天圈层浓度'),
    musicInputGraph: adaptGlobalStructureGraph(row.music_input_graph, '音乐输入'),
    musicOutputGraph: adaptGlobalStructureGraph(row.music_output_graph, '音乐输出'),
    chatInputGraph: adaptGlobalStructureGraph(row.chat_input_graph, '聊天输入'),
    chatOutputGraph: adaptGlobalStructureGraph(row.chat_output_graph, '聊天输出'),
  };
}

export function adaptFriendRelation(raw: Record<string, unknown>): MusicRelationData {
  const relationTemperature = raw.relation_temperature as Record<string, unknown> | undefined;
  const knownCount = Number(raw.known_song_count ?? 0);
  const unknownCount = Number(raw.unknown_song_count ?? 0);
  const genreOverlap = raw.genre_overlap as Record<string, unknown> | undefined;
  const activityHeatmap = raw.activity_heatmap as Record<string, unknown> | undefined;
  const dualPerspective = raw.dual_perspective as Record<string, unknown> | undefined;
  const timelineVisual = raw.timeline_visual as Record<string, unknown> | undefined;
  const silenceAndBurst = raw.silence_and_burst as Record<string, unknown> | undefined;
  const commonWorld = raw.common_world as Record<string, unknown> | undefined;
  return {
    friendName: String(raw.friend_name ?? '').trim() || undefined,
    friendCount: 1,
    temperature: Number(relationTemperature?.score ?? 0),
    temperatureLabel: String(relationTemperature?.label ?? '').trim(),
    messageCount: Number(raw.message_count_total ?? 0),
    activeDays: Number(raw.active_days_total ?? 0),
    totalSongs: Number(raw.song_share_count_total ?? 0),
    mySongs: Number(raw.my_song_count ?? 0),
    friendSongs: Number(raw.friend_song_count ?? 0),
    knownCount,
    unknownCount,
    lastShare: String(raw.cover_line ?? raw.trend_conclusion ?? '暂无数据'),
    genres: adaptDistributionItems(raw.overall_top_genres),
    myGenres: adaptDistributionItems(raw.my_top_genres),
    friendGenres: adaptDistributionItems(raw.friend_top_genres),
    topArtists: adaptTopArtists(raw.top_artists),
    decadeDistribution: adaptDistributionItems(raw.decade_distribution),
    distribution: adaptGenreOverlapBalance(genreOverlap),
    overlapCount: Number(genreOverlap?.overlap_count ?? 0),
    trendConclusion: String(raw.trend_conclusion ?? '').trim(),
    activityConclusion: String(raw.activity_conclusion ?? '').trim(),
    trendSeries: adaptTrendSeries(raw.trend_series),
    timelineNodes: adaptTimelineNodes(timelineVisual?.nodes),
    heatmapHours: adaptHeatmapHours(activityHeatmap?.hours),
    songHeatmapHours: adaptHeatmapHours(activityHeatmap?.song_hours),
    heatmapBuckets: adaptHeatmapBuckets(activityHeatmap?.bucket_ratios),
    dualPerspective: {
      label: String(dualPerspective?.label ?? '').trim(),
      myOutputCount: Number(dualPerspective?.my_output_count ?? 0),
      friendOutputCount: Number(dualPerspective?.friend_output_count ?? 0),
    },
    silenceAndBurst: {
      longestSilenceDays: Number(silenceAndBurst?.longest_silence_days ?? 0),
      recoverPeriod: String(silenceAndBurst?.recover_period ?? '').trim(),
      peakPeriod: String(silenceAndBurst?.peak_period ?? '').trim(),
      peakSongCount: Number(silenceAndBurst?.peak_song_count ?? 0),
    },
    commonWorld: {
      sharedGenres: adaptGenreOverlapBalance({ genres: commonWorld?.shared_genres }),
      sharedArtists: adaptTopArtists(commonWorld?.shared_artists),
      sharedArtistTotal: Number(commonWorld?.shared_artist_total ?? 0),
      sharedDecades: adaptDistributionItems(commonWorld?.shared_decades),
    },
    annualReview: Array.isArray((raw.annual_review as Record<string, unknown> | undefined)?.years)
      ? ((raw.annual_review as Record<string, unknown>).years as Array<Record<string, unknown>>).map((row) => ({
          year: String(row.year ?? '').trim(),
          messageCount: Number(row.message_count ?? 0),
          songCount: Number(row.song_count ?? 0),
        }))
      : [],
    evidenceTracks: adaptEvidenceTracks(raw.evidence_tracks),
  };
}

export function adaptSelfRelation(raw: Record<string, unknown>): MusicRelationData {
  const genreOverlap = raw.genre_overlap_summary_global as Record<string, unknown> | undefined;
  const relationTemperature = raw.relation_temperature as Record<string, unknown> | undefined;
  const activityHeatmap = raw.activity_heatmap as Record<string, unknown> | undefined;
  const dualPerspective = raw.dual_perspective as Record<string, unknown> | undefined;
  const timelineVisual = raw.timeline_visual as Record<string, unknown> | undefined;
  const silenceAndBurst = raw.silence_and_burst as Record<string, unknown> | undefined;
  const commonWorld = raw.common_world as Record<string, unknown> | undefined;
  const globalHero = raw.global_hero as Record<string, unknown> | undefined;
  return {
    friendCount: Number(raw.friend_count ?? 0),
    temperature: Number(relationTemperature?.score ?? Math.min(100, Number(raw.known_song_count ?? 0))),
    temperatureLabel: String(relationTemperature?.label ?? '').trim(),
    messageCount: Number(raw.message_count_total ?? 0),
    activeDays: Number(raw.active_days_total ?? 0),
    totalSongs: Number(raw.known_song_count ?? 0),
    mySongs: Number(raw.my_song_count ?? 0),
    friendSongs: Number(raw.friends_song_count ?? 0),
    knownCount: Number(raw.known_song_count ?? 0),
    unknownCount: 0,
    lastShare: String(raw.cover_line ?? raw.trend_conclusion ?? '暂无数据'),
    genres: adaptDistributionItems(raw.overall_top_genres_global),
    myGenres: adaptDistributionItems(raw.my_genre_distribution_global),
    friendGenres: adaptDistributionItems(raw.friends_genre_distribution_global),
    topArtists: adaptTopArtists(raw.top_artists_global),
    decadeDistribution: adaptDistributionItems(raw.decade_distribution_global),
    distribution: adaptGenreOverlapBalance(genreOverlap),
    overlapCount: Number(genreOverlap?.overlap_count ?? 0),
    trendConclusion: String(raw.trend_conclusion ?? '').trim(),
    activityConclusion: String(raw.activity_conclusion ?? '').trim(),
    trendSeries: adaptTrendSeries(raw.trend_series_global),
    timelineNodes: adaptTimelineNodes(timelineVisual?.nodes),
    heatmapHours: adaptHeatmapHours(activityHeatmap?.hours),
    songHeatmapHours: adaptHeatmapHours(activityHeatmap?.song_hours),
    heatmapBuckets: adaptHeatmapBuckets(activityHeatmap?.bucket_ratios),
    dualPerspective: {
      label: String(dualPerspective?.label ?? '').trim(),
      myOutputCount: Number(dualPerspective?.my_output_count ?? 0),
      friendOutputCount: Number(dualPerspective?.friend_output_count ?? 0),
    },
    silenceAndBurst: {
      longestSilenceDays: Number(silenceAndBurst?.longest_silence_days ?? 0),
      recoverPeriod: String(silenceAndBurst?.recover_period ?? '').trim(),
      peakPeriod: String(silenceAndBurst?.peak_period ?? '').trim(),
      peakSongCount: Number(silenceAndBurst?.peak_song_count ?? 0),
    },
    commonWorld: {
      sharedGenres: adaptGenreOverlapBalance({ genres: commonWorld?.shared_genres }),
      sharedArtists: adaptTopArtists(commonWorld?.shared_artists),
      sharedArtistTotal: Number(commonWorld?.shared_artist_total ?? 0),
      sharedDecades: adaptDistributionItems(commonWorld?.shared_decades),
    },
    annualReview: Array.isArray((raw.annual_review as Record<string, unknown> | undefined)?.years)
      ? ((raw.annual_review as Record<string, unknown>).years as Array<Record<string, unknown>>).map((row) => ({
          year: String(row.year ?? '').trim(),
          messageCount: Number(row.message_count ?? 0),
          songCount: Number(row.song_count ?? 0),
        }))
      : [],
    evidenceTracks: adaptEvidenceTracks(raw.evidence_tracks),
    globalHero: {
      myName: String(globalHero?.my_name ?? '我').trim() || '我',
      myAvatarUrl: String(globalHero?.my_avatar_url ?? '').trim() || null,
      activeFriendCount: Number(globalHero?.active_friend_count ?? raw.active_friend_count ?? raw.friend_count ?? 0),
      messageCount: Number(globalHero?.message_count ?? raw.message_count_total ?? 0),
      songCount: Number(globalHero?.song_count ?? raw.known_song_count ?? 0),
      peakPeriod: String(globalHero?.peak_period ?? silenceAndBurst?.peak_period ?? '').trim(),
      socialTag: String(globalHero?.social_tag ?? dualPerspective?.label ?? '').trim(),
      coreFriend: String(globalHero?.core_friend ?? '').trim(),
    },
    globalTop3: adaptGlobalTop3(raw.global_top3),
    globalSocialStructure: adaptGlobalSocialStructure(raw.global_social_structure),
  };
}

export function adaptShadowTarget(raw: Record<string, unknown> | null | undefined): ShadowTarget | null {
  if (!raw) return null;
  const playlistId = String(raw.playlist_id ?? '').trim();
  if (!playlistId) return null;
  return {
    playlist_id: playlistId,
    playlist_name: String(raw.playlist_name ?? '').trim() || playlistId,
    strategy: String(raw.strategy ?? '').trim() || 'use_existing',
    is_private: Boolean(raw.is_private),
    last_set_at: String(raw.last_set_at ?? '').trim() || undefined,
  };
}

export function adaptShadowTargetOptions(rows: unknown): ShadowTargetOption[] {
  if (!Array.isArray(rows)) return [];
  return rows
    .map((item) => {
      if (!item || typeof item !== 'object') return null;
      const row = item as Record<string, unknown>;
      const id = String(row.id ?? '').trim();
      if (!id) return null;
      return {
        id,
        name: String(row.name ?? '').trim() || id,
        track_count: typeof row.trackCount === 'number' ? row.trackCount : Number(row.trackCount ?? 0),
      };
    })
    .filter((item) => Boolean(item?.id)) as ShadowTargetOption[];
}

export function adaptShadowCandidate(row: Record<string, unknown>): ShadowCandidate {
  return {
    song_id: String(row.song_id ?? '').trim(),
    song_name: String(row.song_name ?? '').trim(),
    artist_names: toArray(row.artist_names),
    album_name: String(row.album_name ?? '').trim(),
    publish_time: String(row.publish_time ?? '').trim(),
    genre_label: String(row.genre_label ?? '').trim(),
    selected: Boolean(row.selected),
  };
}
