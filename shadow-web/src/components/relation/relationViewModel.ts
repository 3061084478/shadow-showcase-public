import type {
  FriendListItemLite,
  GenreBalanceItem,
  GenreDistributionItem,
  MusicRelationData,
  RelationEvidenceTrack,
  RelationTimelineNode,
  TopArtistItem,
} from '../../types';

export type OrbitItem = {
  id: string;
  label: string;
  value: string;
  tone: 'blue' | 'pink' | 'violet' | 'green' | 'neutral';
  tooltip: string;
};

export type OrbitTrait = {
  id: string;
  label: string;
  tone: 'blue' | 'pink' | 'violet' | 'green' | 'neutral';
  tooltip: string;
};

export type TimelineMilestone = {
  id: string;
  period: string;
  title: string;
  description: string;
  messageCount: number;
  songCount: number;
  evidence?: RelationEvidenceTrack | null;
};

export type SharedWorldMetric = {
  label: string;
  value: string;
  tone: 'blue' | 'pink' | 'violet' | 'green' | 'neutral';
};

export type SingleFriendProfileViewModel = {
  friendName: string;
  heroSummary: string;
  energyLabel: string;
  socialTag: string;
  activeWindowLabel: string;
  activeBucketLabel: string;
  peakPeriod: string;
  dominantGenreLabel: string;
  coreArtistLabel: string;
  orbitStats: OrbitItem[];
  orbitTraits: OrbitTrait[];
  detailFacts: Array<{ label: string; value: string }>;
  timelineMilestones: TimelineMilestone[];
  commonMetrics: SharedWorldMetric[];
  finalTitle: string;
  finalParagraphs: string[];
};

function normalizeRatio(ratio: number) {
  if (!Number.isFinite(ratio)) return 0;
  return Math.max(0, Math.min(1, ratio));
}

function findPeakTrendPeriod(data: MusicRelationData) {
  if (data.silenceAndBurst.peakPeriod) return data.silenceAndBurst.peakPeriod;
  const peak = [...data.trendSeries].sort((a, b) => b.distinctSongCount + b.messageCountRaw - (a.distinctSongCount + a.messageCountRaw))[0];
  return peak?.period || '近期';
}

function hasAnyRelationData(data: MusicRelationData) {
  return Boolean(
    data.messageCount > 0
      || data.totalSongs > 0
      || data.activeDays > 0
      || data.trendSeries.some((item) => item.messageCountRaw > 0 || item.distinctSongCount > 0)
      || data.heatmapHours.some((item) => item.count > 0)
      || data.songHeatmapHours.some((item) => item.count > 0)
      || data.commonWorld.sharedGenres.length > 0
      || data.commonWorld.sharedArtists.length > 0
      || data.overlapCount > 0,
  );
}

function pickDominantGenre(items: GenreBalanceItem[], fallbackItems: GenreDistributionItem[]) {
  const shared = [...items].sort((a, b) => b.me + b.friend - (a.me + a.friend))[0];
  if (shared?.genre) return shared.genre;
  return [...fallbackItems].sort((a, b) => b.count - a.count)[0]?.name || '共同流派待显形';
}

function pickCoreArtist(items: TopArtistItem[]) {
  return [...items].sort((a, b) => b.count - a.count)[0]?.name || '共同歌手待显形';
}

function buildTemperatureTooltip(temperature: number) {
  if (temperature >= 85) return `${temperature} 分，属于明显偏高的关系温度，互动强度和持续性都很突出。`;
  if (temperature >= 65) return `${temperature} 分，说明这段关系整体温度稳定，长期互动特征已经很明显。`;
  if (temperature >= 50) return `${temperature} 分，说明这段关系已经进入稳定连接区间。`;
  if (temperature >= 25) return `${temperature} 分，说明这段关系目前还是低频连接。`;
  if (temperature > 0) return `${temperature} 分，说明这段关系已经有稳定来往，但还没到特别高温的阶段。`;
  return `${temperature} 分，当前没有足够记录形成关系分。`;
}

function buildMessageTooltip(messageCount: number) {
  if (messageCount >= 3000) return `${messageCount} 条消息，说明你们始终保持着高频交流。`;
  if (messageCount >= 1000) return `${messageCount} 条消息，说明这段关系不是偶尔联系，而是持续互动。`;
  if (messageCount >= 100) return `${messageCount} 条消息，说明你们已经形成了比较稳定的交流。`;
  if (messageCount >= 20) return `${messageCount} 条消息，说明这段关系已经有持续来往，但频率还不算高。`;
  if (messageCount > 0) return `${messageCount} 条消息，说明这段关系刚刚开始留下可见互动。`;
  return `${messageCount} 条消息，当前还看不出明显的高频聊天痕迹。`;
}

function buildSongTooltip(songCount: number) {
  if (songCount >= 200) return `${songCount} 首歌，说明你们已经不只是偶尔分享，而是形成了很稳定的互相投喂。`;
  if (songCount >= 80) return `${songCount} 首歌，说明音乐分享已经是这段关系里的固定动作。`;
  if (songCount >= 20) return `${songCount} 首歌，说明你们已经积累出比较明确的共同听歌来回。`;
  if (songCount > 0) return `${songCount} 首歌，说明这段关系已经开始出现可感知的音乐交换。`;
  return `${songCount} 首歌，当前还没有形成可感知的歌曲交集。`;
}

function buildActiveDaysTooltip(activeDays: number) {
  if (activeDays >= 120) return `${activeDays} 个活跃日，说明你们的联系是长期持续发生的。`;
  if (activeDays >= 30) return `${activeDays} 个活跃日，说明这段关系分布得比较长，不是短时间爆发。`;
  if (activeDays >= 7) return `${activeDays} 个活跃日，说明这段关系已经不止是一次性的短暂联系。`;
  if (activeDays > 0) return `${activeDays} 个活跃日，说明目前还只是零散互动。`;
  return `${activeDays} 个活跃日，当前还没有积累出明显的长期互动轨迹。`;
}

function buildEnergyTooltip(energyLabel: string, messageCount: number, songCount: number) {
  if (energyLabel.includes('高温')) return `${energyLabel}意味着你们不仅联系频繁，而且互动高峰也足够明显。`;
  if (energyLabel.includes('稳定')) return `${energyLabel}说明这段关系的互动频率和持续性都比较稳。`;
  if (messageCount > 0 || songCount > 0) return `${energyLabel}，说明这段关系已经有自己的互动节奏，但热度还在继续累积。`;
  return `${energyLabel}，但当前数据还不足以支撑更明确的判断。`;
}

function buildSocialTooltip(socialTag: string, mySongs: number, friendSongs: number) {
  if (socialTag.includes('我方主导') || mySongs > friendSongs) return `在这段关系里，你主动发起和输出的比例更高。`;
  if (socialTag.includes('好友输入') || friendSongs > mySongs) return `这段关系更偏向由对方带来新的分享和输入。`;
  return `你们的分享方向比较平衡，没有明显的一方长期主导。`;
}

function buildPeakTooltip(peakPeriod: string, peakMessageCount: number, peakSongCount: number) {
  if (peakMessageCount >= 300 || peakSongCount >= 80) {
    return `${peakPeriod} 是关系高峰期，歌曲 ${peakSongCount} 首，消息 ${peakMessageCount} 条，那个月的互动和分享都冲到了最高。`;
  }
  if (peakMessageCount >= 20 || peakSongCount >= 10) {
    return `${peakPeriod} 是当前最亮的一段时间，歌曲 ${peakSongCount} 首，消息 ${peakMessageCount} 条，热度明显高过其它月份。`;
  }
  if (peakMessageCount > 0 || peakSongCount > 0) {
    return `${peakPeriod} 是当前相对更活跃的时间点，但整体热度其实还不高。`;
  }
  return `${peakPeriod} 是目前最接近高峰的时间点，但详细热度还不够完整。`;
}

function buildGenreTooltip(genreLabel: string, overlapCount: number) {
  if (genreLabel.includes('待显形')) return `共同风格还没有完全成形，当前交集还比较弱。`;
  if (overlapCount >= 5) return `${genreLabel}是你们共同听觉里最明显的重合区域，这类歌最容易把你们连到一起。`;
  if (overlapCount > 0) return `${genreLabel}目前是最容易把你们连接起来的共同偏好，交集已经开始变清楚。`;
  return `${genreLabel}暂时只是弱重合，还需要更多共同听歌把它坐实。`;
}

function buildCoreTooltip(overlapCount: number) {
  if (overlapCount >= 5) return `当前已经有 ${overlapCount} 个明显重合点，你们不只是偶尔分享歌，而是形成了稳定的共同音乐交集。`;
  if (overlapCount > 0) return `当前已经能看到 ${overlapCount} 个重合点，说明共同音乐世界正在慢慢长出来。`;
  return `目前更多还是各自听歌，稳定交集还没有完全长出来。`;
}

function buildTimelineMilestoneDescription(title: string, period: string, messageCount: number, songCount: number) {
  if (title.includes('爆发')) {
    if (songCount >= messageCount && songCount > 0) return `歌曲 ${songCount} 首，消息 ${messageCount} 条。${period} 开始明显升温，歌曲分享先一步冲了起来。`;
    return `歌曲 ${songCount} 首，消息 ${messageCount} 条。${period} 开始明显升温，聊天和分享都在快速抬头。`;
  }
  if (title.includes('高峰')) {
    return `歌曲 ${songCount} 首，消息 ${messageCount} 条。这是整段关系里最亮的峰值月，互动和分享都压到了最高。`;
  }
  if (title.includes('第一次')) {
    return `歌曲 ${songCount} 首，消息 ${messageCount} 条。${period} 第一次出现明确的分享动作，关系从这里开始变得可见。`;
  }
  if (title.includes('回落')) {
    return `歌曲 ${songCount} 首，消息 ${messageCount} 条。热度虽然回落了，但联系没有断掉，只是从高点退了下来。`;
  }
  if (title.includes('恢复') || title.includes('再次')) {
    return `歌曲 ${songCount} 首，消息 ${messageCount} 条。${period} 又重新回到可感知的节奏里，说明这段关系没有停住。`;
  }
  if (title.includes('稳定')) {
    return `歌曲 ${songCount} 首，消息 ${messageCount} 条。这个阶段不算爆发，但互动还在稳稳继续。`;
  }
  return `歌曲 ${songCount} 首，消息 ${messageCount} 条。${period} 是这段关系里一个值得记住的节点。`;
}

function buildActiveWindow(hours: MusicRelationData['heatmapHours']) {
  if (!hours.length || !hours.some((item) => item.count > 0)) {
    return {
      label: '暂无时段数据',
      bucket: '节律待定',
    };
  }
  const sorted = [...hours].sort((a, b) => b.count - a.count);
  const peak = sorted[0];
  const start = peak.hour;
  const end = (peak.hour + 3) % 24;
  const label = `${String(start).padStart(2, '0')}:00 - ${String(end).padStart(2, '0')}:00`;
  return {
    label,
    bucket: peak.bucket || '节律待定',
  };
}

function buildOverlapRatio(items: GenreBalanceItem[]) {
  if (!items.length) return 0;
  let numerator = 0;
  let denominator = 0;
  for (const item of items) {
    numerator += Math.min(item.me, item.friend);
    denominator += Math.max(item.me, item.friend);
  }
  if (denominator <= 0) return 0;
  return numerator / denominator;
}

function resolveEventCounts(period: string, data: MusicRelationData) {
  const match = data.trendSeries.find((item) => item.period === period);
  return {
    messageCount: match?.messageCountRaw ?? 0,
    songCount: match?.distinctSongCount ?? 0,
  };
}

function createFallbackMilestones(data: MusicRelationData): RelationTimelineNode[] {
  const nodes: RelationTimelineNode[] = [];
  const first = data.trendSeries[0];
  const latest = data.trendSeries[data.trendSeries.length - 1];
  const peak = [...data.trendSeries].sort((a, b) => b.distinctSongCount + b.messageCountRaw - (a.distinctSongCount + a.messageCountRaw))[0];
  if (first) {
    nodes.push({
      period: first.period,
      title: '第一次分享',
      description: `${first.period} 是这段关系的起点，当月已经出现第一波明确分享。`,
    });
  }
  if (peak && peak.period !== first?.period) {
    nodes.push({
      period: peak.period,
      title: '高峰阶段',
      description: `${peak.period} 是关系高峰期，互动和歌曲热度同时抬到最高。`,
    });
  }
  if (data.silenceAndBurst.recoverPeriod) {
    nodes.push({
      period: data.silenceAndBurst.recoverPeriod,
      title: '沉寂后恢复',
      description: `${data.silenceAndBurst.recoverPeriod} 开始重新回温，这段关系没有停在沉寂里。`,
    });
  }
  if (latest && latest.period !== peak?.period) {
    nodes.push({
      period: latest.period,
      title: '当前稳定期',
      description: `最近阶段保持稳定，没有爆发，但也没有断掉。`,
    });
  }
  return nodes;
}

function buildTimelineMilestones(data: MusicRelationData) {
  const nodes = data.timelineNodes;
  const evidenceByPeriod = new Map<string, RelationEvidenceTrack>();
  for (const item of data.evidenceTracks) {
    if (!evidenceByPeriod.has(item.period)) {
      evidenceByPeriod.set(item.period, item);
    }
  }
  const milestones: TimelineMilestone[] = [];
  const grouped = new Map<string, RelationTimelineNode[]>();
  for (const node of nodes) {
    if (!node.period || !node.title) continue;
    grouped.set(node.period, [...(grouped.get(node.period) ?? []), node]);
  }
  for (const [period, periodNodes] of grouped) {
    const counts = resolveEventCounts(period, data);
    const titles = periodNodes.map((node) => node.title).filter(Boolean);
    const descriptions = periodNodes.map((node) => {
      const rawDescription = String(node.description || '').trim();
      return rawDescription || buildTimelineMilestoneDescription(node.title, node.period, counts.messageCount, counts.songCount);
    });
    milestones.push({
      id: `${period}-${titles.join('-')}`,
      period,
      title: titles.length > 1 ? titles.join(' / ') : titles[0],
      description: descriptions.join('\n'),
      messageCount: counts.messageCount,
      songCount: counts.songCount,
      evidence: evidenceByPeriod.get(period) ?? null,
    });
  }
  return milestones;
}

export function buildEnergyLabel(data: MusicRelationData) {
  if (!hasAnyRelationData(data)) return '尚未形成关系轨道';
  return data.temperatureLabel || (data.temperature >= 85 ? '核心共振' : data.temperature >= 70 ? '高温关系' : data.temperature >= 50 ? '稳定连接' : data.temperature >= 25 ? '低频连接' : '微弱留痕');
}

export function buildSocialTag(data: MusicRelationData, mode: 'Single' | 'Global') {
  if (!hasAnyRelationData(data)) return mode === 'Global' ? '暂无社交流向' : '暂无分享方向';
  if (data.dualPerspective.label) return data.dualPerspective.label;
  if (mode === 'Global') {
    if (data.mySongs > data.friendSongs * 1.4) return '输出驱动型';
    if (data.friendSongs > data.mySongs * 1.4) return '输入吸纳型';
    return '双向流动型';
  }
  if (data.overlapCount >= 5) return '高耦合共振';
  if (data.mySongs > data.friendSongs * 1.4) return '我方主导型';
  if (data.friendSongs > data.mySongs * 1.4) return '好友输入型';
  return '平衡交换型';
}

export function buildSingleFriendProfileViewModel(data: MusicRelationData, friend?: FriendListItemLite): SingleFriendProfileViewModel {
  const friendName = data.friendName || friend?.nickname || '未命名好友';
  const hasData = hasAnyRelationData(data);
  const energyLabel = buildEnergyLabel(data);
  const socialTag = buildSocialTag(data, 'Single');
  const peakPeriod = hasData ? findPeakTrendPeriod(data) : '暂无峰值';
  const dominantGenreLabel = hasData ? pickDominantGenre(data.commonWorld.sharedGenres, data.decadeDistribution) : '暂无共同流派';
  const coreArtistLabel = hasData ? pickCoreArtist(data.commonWorld.sharedArtists) : '暂无共同歌手';
  const activeWindow = buildActiveWindow(data.heatmapHours);
  const overlapRatio = normalizeRatio(buildOverlapRatio(data.commonWorld.sharedGenres.length ? data.commonWorld.sharedGenres : data.distribution));
  const heroSummary =
    data.trendConclusion ||
    (hasData
      ? `${friendName} 这条关系轨道在 ${peakPeriod} 达到高峰，当前维持着 ${socialTag} 的节奏，互动主要落在 ${activeWindow.label}。`
      : `${friendName} 当前没有归档到聊天或歌曲记录，恒星环只显示真实为空的关系状态。`);

  const orbitStats: OrbitItem[] = [
    {
      id: 'temperature',
      label: '关系分',
      value: String(data.temperature || 0),
      tone: 'blue',
      tooltip: buildTemperatureTooltip(data.temperature || 0),
    },
    {
      id: 'messages',
      label: '消息总数',
      value: String(data.messageCount || 0),
      tone: 'violet',
      tooltip: buildMessageTooltip(data.messageCount || 0),
    },
    {
      id: 'songs',
      label: '歌曲总数',
      value: String(data.totalSongs || 0),
      tone: 'pink',
      tooltip: buildSongTooltip(data.totalSongs || 0),
    },
    {
      id: 'days',
      label: '活跃天数',
      value: String(data.activeDays || 0),
      tone: 'green',
      tooltip: buildActiveDaysTooltip(data.activeDays || 0),
    },
  ];

  const orbitTraits: OrbitTrait[] = [
    {
      id: 'energy',
      label: energyLabel,
      tone: 'blue',
      tooltip: buildEnergyTooltip(energyLabel, data.messageCount || 0, data.totalSongs || 0),
    },
    {
      id: 'social',
      label: socialTag,
      tone: 'pink',
      tooltip: buildSocialTooltip(socialTag, data.mySongs || 0, data.friendSongs || 0),
    },
    {
      id: 'bucket',
      label: hasData ? activeWindow.bucket || '节律待定' : '暂无活跃时段',
      tone: 'violet',
      tooltip: hasData ? `当前最强互动时段落在 ${activeWindow.bucket || '未知时段'}。` : '没有消息或歌曲记录，因此无法形成真实活跃时段。',
    },
    {
      id: 'peak',
      label: hasData ? `高峰 ${peakPeriod}` : '暂无高峰',
      tone: 'green',
      tooltip: hasData
        ? buildPeakTooltip(
            peakPeriod,
            data.trendSeries.find((item) => item.period === peakPeriod)?.messageCountRaw ?? 0,
            data.trendSeries.find((item) => item.period === peakPeriod)?.distinctSongCount ?? 0,
          )
        : '没有可统计的月份趋势，因此不存在真实高峰。',
    },
    {
      id: 'genre',
      label: dominantGenreLabel,
      tone: 'pink',
      tooltip: buildGenreTooltip(dominantGenreLabel, data.overlapCount || 0),
    },
    {
      id: 'core',
      label: hasData ? data.overlapCount >= 5 ? '核心好友' : '持续互听' : '共同区未形成',
      tone: 'neutral',
      tooltip: hasData ? buildCoreTooltip(data.overlapCount || 0) : '当前没有共同歌曲、共同歌手或共同流派记录。',
    },
  ];

  const detailFacts = [
    { label: '最近关系判断', value: heroSummary },
    { label: '峰值月份', value: hasData ? peakPeriod : '暂无真实峰值' },
    { label: '最长沉寂', value: data.silenceAndBurst.longestSilenceDays ? `${data.silenceAndBurst.longestSilenceDays} 天` : '暂无明显沉寂' },
    { label: '主导方向', value: data.dualPerspective.label || socialTag },
  ];

  const commonMetrics: SharedWorldMetric[] = [
    {
      label: '共同流派重合度',
      value: `${Math.round(overlapRatio * 100)}%`,
      tone: 'green',
    },
    {
      label: '共同歌手数',
      value: String(data.commonWorld.sharedArtists.length),
      tone: 'pink',
    },
    {
      label: '核心连接歌手',
      value: coreArtistLabel,
      tone: 'blue',
    },
    {
      label: '主导共同风格',
      value: dominantGenreLabel,
      tone: 'violet',
    },
  ];

  const finalTitle =
    !hasData
      ? '一条尚未留下归档痕迹的空轨道'
      : data.temperature >= 85
      ? '一条高压却稳定的共振轨道'
      : data.temperature >= 65
        ? '一条已经形成自我节律的长期连线'
        : '一条仍在扩张中的交换轨道';

  const finalParagraphs = hasData
    ? [
        data.activityConclusion || `${friendName} 和你并不是随机分享，而是在 ${activeWindow.label} 这段时间里形成了最稳定的连接感。`,
        `${peakPeriod} 是这条轨道最亮的时刻，${data.dualPerspective.label || socialTag} 的方向性也在那之后逐渐稳定下来。`,
        `${dominantGenreLabel} 与 ${coreArtistLabel} 把这段关系缝在同一张听觉地图上，让它不只是互动频率，而是一块真正能被辨认出的共同世界。`,
      ]
    : [
        `${friendName} 当前没有归档到聊天记录，也没有歌曲分享记录。`,
        '所有卡片只保留真实的 0 值与未形成状态，不生成关系温度、活跃时段或共同音乐结论。',
        '这不是错误状态，而是一次完整归档后的空关系样本。',
      ];

  return {
    friendName,
    heroSummary,
    energyLabel,
    socialTag,
    activeWindowLabel: activeWindow.label,
    activeBucketLabel: activeWindow.bucket,
    peakPeriod,
    dominantGenreLabel,
    coreArtistLabel,
    orbitStats,
    orbitTraits,
    detailFacts,
    timelineMilestones: buildTimelineMilestones(data),
    commonMetrics,
    finalTitle,
    finalParagraphs,
  };
}
