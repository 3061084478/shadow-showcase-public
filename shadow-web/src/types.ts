import type React from 'react';

export type ConnectionStatus = 'ready' | 'waiting' | 'error';

export type FriendListItemLite = {
  friend_uid: string;
  nickname: string;
  avatar_url: string | null;
  is_pinned: boolean;
  archive_status: 'never_archived' | 'ready' | 'syncing' | 'failed';
  friend_sync_status: 'ok' | 'needs_sync' | 'syncing' | 'error';
  last_synced_at: string | null;
  message_count: number;
  shared_song_count: number;
  genre_unknown_count: number;
};

export type FriendDetailSummary = FriendListItemLite & {
  last_archived_at: string | null;
  last_message_at: string | null;
  message_count: number;
  genre_known_count: number;
  unknown_ratio: number;
  has_relation_snapshot: boolean;
  has_export_ready_data: boolean;
  last_error_message?: string | null;
};

export type SongSnippet = {
  id?: string;
  name: string;
  artist: string;
  album: string;
  genre: string;
  status: 'known' | 'unknown';
  publish_time?: string;
};

export type ChatMessage = {
  id: string;
  sender: 'me' | 'friend';
  type: 'text' | 'song' | 'image' | 'video' | 'unknown';
  content?: string;
  timestamp: string;
  song?: SongSnippet;
};

export type GenreDistributionItem = {
  name: string;
  count: number;
  ratio?: number;
};

export type GenreBalanceItem = {
  genre: string;
  me: number;
  friend: number;
};

export type TopArtistItem = {
  name: string;
  count: number;
  me?: number;
  friend?: number;
};

export type RankedFriendMetric = {
  uid: string;
  nickname: string;
  avatar_url: string | null;
  value: number;
};

export type GlobalHeroBlock = {
  myName: string;
  myAvatarUrl: string | null;
  activeFriendCount: number;
  messageCount: number;
  songCount: number;
  peakPeriod: string;
  socialTag: string;
  coreFriend: string;
};

export type GlobalTop3Block = {
  chatTop3: RankedFriendMetric[];
  songTop3: RankedFriendMetric[];
  temperatureTop3: RankedFriendMetric[];
};

export type GlobalStructureMetric = {
  label: string;
  summary: string;
};

export type GlobalStructureGraphNode = {
  uid: string;
  nickname: string;
  avatar_url: string | null;
  value: number;
};

export type GlobalStructureGraph = {
  title: string;
  summary: string;
  nodes: GlobalStructureGraphNode[];
};

export type GlobalSocialStructureBlock = {
  musicIoType: GlobalStructureMetric;
  chatIoType: GlobalStructureMetric;
  musicCircleDensity: GlobalStructureMetric;
  chatCircleDensity: GlobalStructureMetric;
  musicInputGraph: GlobalStructureGraph;
  musicOutputGraph: GlobalStructureGraph;
  chatInputGraph: GlobalStructureGraph;
  chatOutputGraph: GlobalStructureGraph;
};

export type RelationTrendItem = {
  period: string;
  messageCountRaw: number;
  distinctSongCount: number;
  myDistinctSongCount: number;
  friendDistinctSongCount: number;
  phaseLabel: string;
};

export type RelationTimelineNode = {
  title: string;
  period: string;
  description: string;
};

export type RelationHeatmapHour = {
  hour: number;
  count: number;
  bucket: string;
};

export type RelationHeatmapBucket = {
  label: string;
  count: number;
  ratio: number;
};

export type RelationDualPerspective = {
  label: string;
  myOutputCount: number;
  friendOutputCount: number;
};

export type RelationSilenceBurst = {
  longestSilenceDays: number;
  recoverPeriod: string;
  peakPeriod: string;
  peakSongCount: number;
};

export type RelationAnnualItem = {
  year: string;
  messageCount: number;
  songCount: number;
};

export type RelationEvidenceTrack = {
  title: string;
  period: string;
  songName: string;
  artistNames: string[];
  genreLabel: string;
};

export type MusicRelationData = {
  friendName?: string;
  friendCount?: number;
  temperature: number;
  temperatureLabel?: string;
  messageCount: number;
  activeDays: number;
  totalSongs: number;
  mySongs: number;
  friendSongs: number;
  knownCount: number;
  unknownCount: number;
  lastShare: string;
  trendConclusion?: string;
  activityConclusion?: string;
  genres: GenreDistributionItem[];
  myGenres: GenreDistributionItem[];
  friendGenres: GenreDistributionItem[];
  topArtists: TopArtistItem[];
  decadeDistribution: GenreDistributionItem[];
  distribution: GenreBalanceItem[];
  overlapCount: number;
  trendSeries: RelationTrendItem[];
  timelineNodes: RelationTimelineNode[];
  heatmapHours: RelationHeatmapHour[];
  songHeatmapHours: RelationHeatmapHour[];
  heatmapBuckets: RelationHeatmapBucket[];
  dualPerspective: RelationDualPerspective;
  silenceAndBurst: RelationSilenceBurst;
  commonWorld: {
    sharedGenres: GenreBalanceItem[];
    sharedArtists: TopArtistItem[];
    sharedArtistTotal: number;
    sharedDecades: GenreDistributionItem[];
  };
  annualReview: RelationAnnualItem[];
  evidenceTracks: RelationEvidenceTrack[];
  globalHero?: GlobalHeroBlock;
  globalTop3?: GlobalTop3Block;
  globalSocialStructure?: GlobalSocialStructureBlock;
};

export type ShadowTarget = {
  playlist_id: string;
  playlist_name: string;
  strategy: string;
  is_private: boolean;
  last_set_at?: string;
};

export type ShadowTargetOption = {
  id: string;
  name: string;
  track_count?: number;
};

export type ShadowCandidate = {
  song_id: string;
  song_name: string;
  artist_names: string[];
  album_name: string;
  publish_time: string;
  genre_label: string;
  selected: boolean;
};

export type ShadowBuildResult = {
  uid: string;
  friend_name: string;
  playlist_name: string;
  generated_count: number;
  track_ids: string[];
  overwrite: boolean;
  anchor_song_id: string;
  anchor_song_name: string;
  anchor_time: string;
  skipped_duplicates: number;
  stop_reason: string;
};

export type AuthState = 'login' | 'authenticated';

export type AuthAccount = {
  user_id: string;
  nickname: string;
  avatar_url?: string | null;
};

export type AuthStatusPayload = {
  api_ready: boolean;
  cookie_valid: boolean;
  account: Partial<AuthAccount>;
};

export type QrSession = {
  key: string;
  qr_url: string;
  qr_image?: string;
};

export type QrPollPayload = {
  code: number;
  cookie?: string;
  message?: string;
};

export type PageKey = 'home' | 'chat' | 'relation' | 'playlist';

export type PageWrapperProps = {
  title: string;
  subtitle: string;
  className?: string;
  friend?: FriendListItemLite;
  friends?: FriendListItemLite[];
  selectedFriendId?: string | null;
  hideFriendCard?: boolean;
  onSelectFriend?: (uid: string) => void;
  onBack: () => void;
  onRefreshArchive?: (() => void) | null;
  refreshingArchive?: boolean;
  headerBottom?: React.ReactNode;
  children: React.ReactNode;
};

export type ChatQueryScope = 'recent' | 'all' | 'pages' | 'incremental';
export type ChatSenderScope = 'all' | 'self' | 'friend';
export type ChatMessageType = 'all' | 'text' | 'song' | 'image';

export type ChatQueryPayload = {
  scope: ChatQueryScope;
  sender_scope: ChatSenderScope;
  msg_type: ChatMessageType;
  keyword?: string;
  date?: string;
  start_date?: string;
  end_date?: string;
  page?: number;
  limit?: number;
};

export type ChatQueryResult = {
  scope: string;
  total: number;
  rows: ChatMessage[];
  page?: number;
  limit?: number;
};

export type ArchiveSummary = {
  oldest_archived_time?: string | null;
  newest_archived_time?: string | null;
  last_message_at?: string | null;
  active_dates?: string[];
  message_count?: number;
  shared_song_count?: number;
  known_song_count?: number;
  unknown_song_count?: number;
  backfill_status?: {
    last_backfill_at?: string;
    status?: string;
    pages_fetched?: number;
    fetched_count?: number;
    inserted_count?: number;
  } | null;
  processed_count?: number;
  inserted_count?: number;
  skipped_count?: number;
  pages_fetched?: number;
};

export type BootstrapSyncError = {
  friend_uid: string;
  friend_name: string;
  error: string;
};

export type BootstrapSyncStatus = {
  running: boolean;
  finished: boolean;
  total_friends: number;
  completed_friends: number;
  current_friend_uid: string;
  current_friend_name: string;
  succeeded: number;
  failed: number;
  errors: BootstrapSyncError[];
  started_at: string;
  finished_at: string;
  delta_message_count: number;
  delta_song_count: number;
  current_delta_message_count: number;
  current_delta_song_count: number;
  last_friend_result?: {
    friend_uid: string;
    friend_name: string;
    delta_message_count: number;
    delta_song_count: number;
    status: 'ok' | 'error';
    error?: string;
  } | null;
};

export type PrivacySettingsPayload = {
  allow_unknown_song_contribution: boolean;
  description: string;
  queue_summary: {
    pending: number;
    uploaded: number;
    failed: number;
    total: number;
    current_unknown_total: number;
    uploaded_deduped?: number;
  };
};

export type UnknownFlushPayload = {
  ok: boolean;
  uploaded: number;
  reason: string;
};

export type ShadowPlaylistTrack = {
  id: string;
  name: string;
  artist: string;
  genre?: string;
};

export type RelationExportPayload = {
  title: string;
  for_ai_json: Record<string, unknown>;
  prompt_text: string;
  external_copy_text: string;
};
