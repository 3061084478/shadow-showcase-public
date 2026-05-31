import { useEffect, useMemo, useRef, useState } from 'react';
import { Copy, Crown, MessageCircle, Music2, Sparkles, UserRound } from 'lucide-react';
import { motion, useReducedMotion } from 'motion/react';
import type {
  GlobalStructureGraph,
  MusicRelationData,
  RankedFriendMetric,
  RelationExportPayload,
} from '../../types';
import { SharedSoundWorld } from './SharedSoundWorld';
import { SonicTimelineRiver } from './SonicTimelineRiver';
import { buildSocialTag, type SingleFriendProfileViewModel } from './relationViewModel';
import './relationImmersive.css';

type GlobalMusicSocialProfileProps = {
  data: MusicRelationData;
  exportPayload: RelationExportPayload | null;
  exportMessage: string;
  exporting: boolean;
  onExport: () => Promise<RelationExportPayload | null>;
};

type GlobalOrbitNode = {
  id: string;
  label: string;
  value?: string;
  tooltip: string;
  tone: 'blue' | 'pink' | 'violet' | 'green' | 'neutral';
};

type OrbitRenderNode = GlobalOrbitNode & {
  x: number;
  y: number;
  depth: number;
  scale: number;
  alpha: number;
  zIndex: number;
  visible: boolean;
};

const TRACK_TILT = -12;

function compactNumber(value: number) {
  if (value >= 10000) return `${(value / 10000).toFixed(1)}w`;
  return String(value);
}

function hasGlobalSocialData(data: MusicRelationData) {
  const hero = data.globalHero;
  return Boolean(
    (hero?.activeFriendCount ?? data.friendCount ?? 0) > 0
      || (hero?.messageCount ?? data.messageCount ?? 0) > 0
      || (hero?.songCount ?? data.totalSongs ?? 0) > 0
      || data.trendSeries.some((item) => item.messageCountRaw > 0 || item.distinctSongCount > 0)
      || data.globalTop3?.chatTop3.length
      || data.globalTop3?.songTop3.length
      || data.globalTop3?.temperatureTop3.length,
  );
}

function resolveGlobalStatus(friendCount: number, messageCount: number, songCount: number) {
  if (friendCount <= 0 && messageCount <= 0 && songCount <= 0) return '社交轨道未点亮';
  if (friendCount <= 2 && messageCount < 100 && songCount < 20) return '低频社交';
  if (friendCount >= 13 || messageCount >= 5000 || songCount >= 400) return '高密度社交网';
  if (friendCount >= 6 || messageCount >= 1000 || songCount >= 100) return '稳定社交圈';
  return '小型音乐圈';
}

function resolveGlobalNodeCount(data: MusicRelationData) {
  const names = new Set<string>();
  data.globalTop3?.chatTop3.forEach((item) => names.add(item.uid || item.nickname));
  data.globalTop3?.songTop3.forEach((item) => names.add(item.uid || item.nickname));
  data.globalTop3?.temperatureTop3.forEach((item) => names.add(item.uid || item.nickname));
  return names.size || data.globalHero?.activeFriendCount || data.friendCount || 0;
}
function normalizeAngle(angle: number) {
  const mod = angle % 360;
  return mod < 0 ? mod + 360 : mod;
}

function buildNodePosition(
  item: GlobalOrbitNode,
  index: number,
  total: number,
  radiusX: number,
  radiusY: number,
  orbitRotation: number,
): OrbitRenderNode {
  const baseAngle = (360 / total) * index;
  const angle = normalizeAngle(baseAngle + orbitRotation);
  const rad = (angle * Math.PI) / 180;
  const depth = Math.sin(rad);
  const frontness = Math.max(0, depth);
  return {
    ...item,
    x: Math.cos(rad) * radiusX,
    y: Math.sin(rad) * radiusY,
    depth,
    scale: 0.78 + frontness * 0.38,
    alpha: depth > 0.08 ? 0.42 + frontness * 0.58 : 0,
    zIndex: Math.round((depth + 1) * 100),
    visible: depth > 0.08,
  };
}

function GlobalOrbitTrack({
  className,
  items,
  trackType,
  radiusX,
  radiusY,
  orbitRotation,
  selectedId,
  hoveredId,
  lockedId,
  onPointerEnter,
  onPointerLeave,
  onPointerDown,
}: {
  className: string;
  items: GlobalOrbitNode[];
  trackType: 'stat' | 'tag';
  radiusX: number;
  radiusY: number;
  orbitRotation: number;
  selectedId: string | null;
  hoveredId: string | null;
  lockedId: string | null;
  onPointerEnter: (id: string) => void;
  onPointerLeave: (id: string) => void;
  onPointerDown: (id: string) => void;
}) {
  const nodes = useMemo(
    () => items.map((item, index) => buildNodePosition(item, index, items.length, radiusX, radiusY, orbitRotation)),
    [items, orbitRotation, radiusX, radiusY],
  );

  return (
    <div className={`shadow-orbit-track ${className}`}>
      {nodes.map((node) => {
        const focusedId = lockedId ?? hoveredId;
        const selected = selectedId === node.id;
        const dimmed = Boolean(focusedId) && focusedId !== node.id;
        const canInteract = node.visible;
        return (
          <div
            key={node.id}
            className={`shadow-orbit-track__hitbox shadow-orbit-track__hitbox--${trackType} ${selected ? 'is-selected' : ''} ${dimmed ? 'is-dimmed' : ''}`}
            style={{
              transform: `translate(${node.x}px, ${node.y}px) translate(-50%, -50%) scale(${selected ? node.scale * 1.08 : node.scale})`,
              opacity: selected ? 1 : node.alpha,
              zIndex: selected ? 999 : node.zIndex,
              pointerEvents: canInteract ? 'auto' : 'none',
            }}
            onPointerEnter={() => canInteract && onPointerEnter(node.id)}
            onPointerLeave={() => canInteract && onPointerLeave(node.id)}
            onPointerDown={(event) => {
              event.stopPropagation();
              if (canInteract) onPointerDown(node.id);
            }}
          >
            <div className={`shadow-orbit-track__shell shadow-orbit-track__shell--${trackType} shadow-orbit-track__shell--${node.tone}`} style={{ transform: `rotate(${TRACK_TILT}deg)` }}>
              <div className={`shadow-orbit-track__node shadow-orbit-track__node--${trackType}`}>
                {trackType === 'stat' ? (
                  <>
                    <span className="shadow-orbit-track__kicker">{node.label}</span>
                    <strong className="shadow-orbit-track__value">{node.value}</strong>
                  </>
                ) : (
                  <span className="shadow-orbit-track__tag">{node.label}{node.value ? ` · ${node.value}` : ''}</span>
                )}
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}

function buildGlobalViewModel(data: MusicRelationData): SingleFriendProfileViewModel {
  const hero = data.globalHero;
  const peakPeriod = hero?.peakPeriod || data.silenceAndBurst.peakPeriod || '近期';
  const milestoneGroups = new Map<string, typeof data.timelineNodes>();
  data.timelineNodes.forEach((node) => {
    if (!node.period || !node.title) return;
    milestoneGroups.set(node.period, [...(milestoneGroups.get(node.period) ?? []), node]);
  });
  return {
    friendName: hero?.myName || '我',
    heroSummary: '',
    energyLabel: hero?.socialTag || buildSocialTag(data, 'Global'),
    socialTag: hero?.socialTag || buildSocialTag(data, 'Global'),
    activeWindowLabel: peakPeriod,
    activeBucketLabel: '全部好友',
    peakPeriod,
    dominantGenreLabel: data.commonWorld.sharedGenres[0]?.genre || data.genres[0]?.name || '共同流派待形成',
    coreArtistLabel: data.commonWorld.sharedArtists[0]?.name || '共同歌手待形成',
    orbitStats: [],
    orbitTraits: [],
    detailFacts: [],
    timelineMilestones: Array.from(milestoneGroups.entries()).map(([period, nodes]) => {
      const match = data.trendSeries.find((item) => item.period === period);
      const titles = nodes.map((node) => node.title).filter(Boolean);
      return {
        id: `${period}-${titles.join('-')}`,
        period,
        title: titles.length > 1 ? titles.join(' / ') : titles[0],
        description: nodes.map((node) => node.description).filter(Boolean).join('\n'),
        messageCount: match?.messageCountRaw ?? 0,
        songCount: match?.distinctSongCount ?? 0,
      };
    }),
    commonMetrics: [],
    finalTitle: '',
    finalParagraphs: [],
  };
}

function GlobalOrbitHero({ data }: { data: MusicRelationData }) {
  const reduceMotion = useReducedMotion();
  const [hoveredId, setHoveredId] = useState<string | null>(null);
  const [lockedId, setLockedId] = useState<string | null>(null);
  const [innerRotation, setInnerRotation] = useState(-18);
  const [outerRotation, setOuterRotation] = useState(12);
  const hero = data.globalHero;
  const structure = data.globalSocialStructure;
  const activeFriendCount = hero?.activeFriendCount ?? data.friendCount ?? 0;
  const messageCount = hero?.messageCount ?? data.messageCount ?? 0;
  const songCount = hero?.songCount ?? data.totalSongs ?? 0;
  const hasData = hasGlobalSocialData(data);
  const globalStatus = resolveGlobalStatus(activeFriendCount, messageCount, songCount);
  const peakLabel = hasData ? hero?.peakPeriod || data.silenceAndBurst.peakPeriod || '暂无活跃峰值' : '暂无活跃峰值';
  const socialTag = hasData ? hero?.socialTag || buildSocialTag(data, 'Global') : '暂无社交标签';
  const coreFriend = hasData ? hero?.coreFriend || '' : '';
  const musicIoLabel = hasData ? structure?.musicIoType.summary || '暂无音乐流向' : '暂无音乐流向';
  const chatIoLabel = hasData ? structure?.chatIoType.summary || '暂无聊天流向' : '暂无聊天流向';
  const innerNodes: GlobalOrbitNode[] = [
    {
      id: 'friends',
      label: '活跃好友数',
      value: compactNumber(activeFriendCount),
      tone: 'blue',
      tooltip: activeFriendCount > 0 ? `当前全局画像覆盖 ${activeFriendCount} 位有归档互动或歌曲记录的好友。` : '当前没有好友形成可统计的互动记录。',
    },
    {
      id: 'messages',
      label: '消息总数',
      value: compactNumber(messageCount),
      tone: 'violet',
      tooltip: messageCount > 0 ? `全部好友归档消息共 ${messageCount} 条。` : '暂无全好友聊天记录。',
    },
    {
      id: 'songs',
      label: '歌曲总数',
      value: compactNumber(songCount),
      tone: 'pink',
      tooltip: songCount > 0 ? `全部好友已识别歌曲共 ${songCount} 首。` : '暂无全好友歌曲分享记录。',
    },
  ];
  const outerNodes: GlobalOrbitNode[] = [
    {
      id: 'status',
      label: globalStatus,
      tone: 'blue',
      tooltip: hasData ? `整体状态：${globalStatus}。` : '没有全局消息、歌曲或活跃好友记录，因此社交轨道尚未点亮。',
    },
    {
      id: 'music-io',
      label: musicIoLabel,
      tone: 'pink',
      tooltip: hasData && musicIoLabel !== '暂无音乐流向' ? `音乐输入/输出类型：${musicIoLabel}。` : '没有足够歌曲流向数据，暂时无法判断音乐输入输出。',
    },
    {
      id: 'chat-io',
      label: chatIoLabel,
      tone: 'violet',
      tooltip: hasData && chatIoLabel !== '暂无聊天流向' ? `聊天输入/输出类型：${chatIoLabel}。` : '没有足够聊天流向数据，暂时无法判断聊天输入输出。',
    },
    {
      id: 'peak',
      label: peakLabel,
      tone: 'green',
      tooltip: hasData && peakLabel !== '暂无活跃峰值' ? `${peakLabel} 是全局音乐社交里最明显的峰值阶段。` : '暂无可统计的全局活跃峰值。',
    },
    {
      id: 'tag',
      label: socialTag,
      tone: 'neutral',
      tooltip: hasData && socialTag !== '暂无社交标签' ? `整体社交标签：${socialTag}。` : '当前没有形成可命名的全局社交标签。',
    },
    {
      id: 'core',
      label: coreFriend ? `核心好友 ${coreFriend}` : '暂无核心好友',
      tone: 'blue',
      tooltip: coreFriend ? `${coreFriend} 是当前全局关系强度最突出的好友。` : '当前还没有形成可展示的核心好友。',
    },
  ];
  const activeId = lockedId ?? hoveredId;
  const activeNode = [...innerNodes, ...outerNodes].find((item) => item.id === activeId) ?? null;
  const shouldPause = Boolean(activeId) || reduceMotion;

  useEffect(() => {
    if (shouldPause) return;
    const timer = window.setInterval(() => {
      setInnerRotation((value) => normalizeAngle(value + 0.35));
      setOuterRotation((value) => normalizeAngle(value - 0.24));
    }, 40);
    return () => window.clearInterval(timer);
  }, [shouldPause]);

  useEffect(() => {
    const handlePointerDown = () => {
      setLockedId(null);
      setHoveredId(null);
    };
    window.addEventListener('pointerdown', handlePointerDown);
    return () => window.removeEventListener('pointerdown', handlePointerDown);
  }, []);

  return (
    <section className="shadow-orbit-hero shadow-global-orbit">
      <div className="shadow-orbit-hero__mist shadow-orbit-hero__mist--blue" />
      <div className="shadow-orbit-hero__mist shadow-orbit-hero__mist--pink" />
      <div className="shadow-orbit-hero__grain" />
      <div className="shadow-orbit-hero__head">
        <h2 className="shadow-orbit-hero__title">我的音乐社交恒星环</h2>
      </div>
      <div
        className="shadow-orbit-hero__stage shadow-global-orbit__stage"
        onPointerDown={() => setLockedId(null)}
        onPointerLeave={() => {
          if (!lockedId) setHoveredId(null);
        }}
      >
        <div className="shadow-orbit-hero__support-ring" />
        <div className="shadow-orbit-hero__ring shadow-orbit-hero__ring--inner shadow-orbit-hero__ring--back" />
        <div className="shadow-orbit-hero__ring shadow-orbit-hero__ring--outer shadow-orbit-hero__ring--back" />
        <GlobalOrbitTrack
          className="shadow-orbit-track--inner"
          items={innerNodes}
          trackType="stat"
          radiusX={350}
          radiusY={132}
          orbitRotation={innerRotation}
          selectedId={activeId}
          hoveredId={hoveredId}
          lockedId={lockedId}
          onPointerEnter={(id) => !lockedId && setHoveredId(id)}
          onPointerLeave={(id) => {
            if (!lockedId && hoveredId === id) setHoveredId(null);
          }}
          onPointerDown={(id) => setLockedId((current) => (current === id ? null : id))}
        />
        <GlobalOrbitTrack
          className="shadow-orbit-track--outer"
          items={outerNodes}
          trackType="tag"
          radiusX={484}
          radiusY={186}
          orbitRotation={outerRotation}
          selectedId={activeId}
          hoveredId={hoveredId}
          lockedId={lockedId}
          onPointerEnter={(id) => !lockedId && setHoveredId(id)}
          onPointerLeave={(id) => {
            if (!lockedId && hoveredId === id) setHoveredId(null);
          }}
          onPointerDown={(id) => setLockedId((current) => (current === id ? null : id))}
        />
        <div className="shadow-orbit-hero__core-occlusion shadow-global-orbit__core">
          <div className="shadow-orbit-hero__core-glow" />
          <div className="shadow-orbit-hero__avatar-shell">
            <div className="shadow-orbit-hero__avatar">
              {hero?.myAvatarUrl ? (
                <img src={hero.myAvatarUrl} alt="" className="h-full w-full object-cover" />
              ) : (
                <div className="shadow-orbit-hero__avatar-fallback">
                  <UserRound size={48} strokeWidth={1.6} />
                </div>
              )}
            </div>
          </div>
          <div className="shadow-orbit-hero__copy">
            <div className="shadow-orbit-hero__name">{hero?.myName || '我'}</div>
          </div>
        </div>
        <div className="shadow-orbit-hero__ring shadow-orbit-hero__ring--inner shadow-orbit-hero__ring--front" />
        <div className="shadow-orbit-hero__ring shadow-orbit-hero__ring--outer shadow-orbit-hero__ring--front" />
        {activeNode ? (
          <motion.div
            className="shadow-orbit-hero__focus-note"
            initial={false}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            transition={{ duration: 0.18, ease: [0.16, 1, 0.3, 1] }}
          >
            <div className="shadow-orbit-hero__focus-label">{activeNode.label}</div>
            <div className="shadow-orbit-hero__focus-text">{activeNode.tooltip}</div>
          </motion.div>
        ) : null}
      </div>
    </section>
  );
}

function RankColumn({
  title,
  suffix,
  items,
  tone,
  activeName,
  onActiveNameChange,
}: {
  title: string;
  suffix: string;
  items: RankedFriendMetric[];
  tone: 'chat' | 'song' | 'heat';
  activeName: string | null;
  onActiveNameChange: (name: string | null) => void;
}) {
  const podiumItems = [
    { item: items[1], rank: 2 },
    { item: items[0], rank: 1 },
    { item: items[2], rank: 3 },
  ].filter((entry): entry is { item: RankedFriendMetric; rank: number } => Boolean(entry.item));
  const MotifIcon = tone === 'chat' ? MessageCircle : tone === 'song' ? Music2 : Sparkles;

  return (
    <section className={`shadow-global-rank__podium shadow-global-rank__podium--${tone}`}>
      <div className="shadow-global-rank__motifs" aria-hidden>
        {[0, 1, 2, 3, 4, 5].map((index) => (
          <MotifIcon key={index} className={`shadow-global-rank__motif shadow-global-rank__motif--${index + 1}`} strokeWidth={1.35} />
        ))}
      </div>
      <h4>{title}</h4>
      <div className="shadow-global-rank__podium-stage">
        {podiumItems.length ? (
          podiumItems.map(({ item, rank }) => {
            const active = activeName === item.nickname;
            const dimmed = Boolean(activeName) && !active;
            return (
              <button
                key={`${title}-${item.uid || item.nickname}`}
                type="button"
                className={`shadow-global-rank__podium-item shadow-global-rank__podium-item--${rank} ${active ? 'is-active' : ''} ${dimmed ? 'is-dimmed' : ''}`}
                onPointerEnter={() => onActiveNameChange(item.nickname)}
                onPointerLeave={() => onActiveNameChange(null)}
              >
                <span className="shadow-global-rank__halo" />
                <span className="shadow-global-rank__avatar">
                  {rank === 1 ? (
                    <span className="shadow-global-rank__crown" aria-hidden>
                      <Crown size={30} strokeWidth={1.8} />
                    </span>
                  ) : null}
                  {item.avatar_url ? <img src={item.avatar_url} alt="" /> : <UserRound size={rank === 1 ? 34 : 25} />}
                </span>
                <span className="shadow-global-rank__medal">{rank}</span>
                <strong>{item.nickname}</strong>
                <span className="shadow-global-rank__value">{item.value}</span>
                <em>{suffix}</em>
                <span className="shadow-global-rank__tooltip">
                  {item.nickname}
                  <br />
                  {title.replace(' Top3', '')} {item.value} {suffix}
                </span>
              </button>
            );
          })
        ) : (
          <div className="shadow-global-empty">暂无真实排行数据</div>
        )}
      </div>
    </section>
  );
}

function GlobalTop3Section({ data }: { data: MusicRelationData }) {
  const [activeName, setActiveName] = useState<string | null>(null);
  const top3 = data.globalTop3;
  return (
    <section className="shadow-global-block shadow-global-rank">
      <h3 className="shadow-global-title">关系强度 Top3</h3>
      <div className="shadow-global-rank__grid">
        <RankColumn title="聊天 Top3" suffix="条" tone="chat" items={top3?.chatTop3 ?? []} activeName={activeName} onActiveNameChange={setActiveName} />
        <RankColumn title="歌曲 Top3" suffix="首" tone="song" items={top3?.songTop3 ?? []} activeName={activeName} onActiveNameChange={setActiveName} />
        <RankColumn title="关系温度 Top3" suffix="分" tone="heat" items={top3?.temperatureTop3 ?? []} activeName={activeName} onActiveNameChange={setActiveName} />
      </div>
    </section>
  );
}

function hashText(value: string) {
  let hash = 0;
  for (let index = 0; index < value.length; index += 1) {
    hash = (hash * 31 + value.charCodeAt(index)) >>> 0;
  }
  return hash;
}

function graphNodePosition(graphKey: string, uid: string, index: number, ratio: number) {
  const anchors = [
    { x: 27, y: 31 },
    { x: 50, y: 18 },
    { x: 73, y: 31 },
    { x: 28, y: 73 },
    { x: 72, y: 73 },
  ];
  const anchor = anchors[index % anchors.length];
  const seed = hashText(`${graphKey}-${uid}-${index}`);
  const center = { x: 50, y: 58 };
  const pull = 0.04 + ratio * 0.08;
  const x = anchor.x + (center.x - anchor.x) * pull + ((seed % 5) - 2);
  const y = anchor.y + (center.y - anchor.y) * pull + (((seed >> 4) % 5) - 2);
  return {
    x: Math.max(18, Math.min(82, x)),
    y: Math.max(22, Math.min(82, y)),
  };
}

function quadraticPointAtMiddle(
  start: { x: number; y: number },
  control: { x: number; y: number },
  end: { x: number; y: number },
) {
  return {
    x: start.x * 0.25 + control.x * 0.5 + end.x * 0.25,
    y: start.y * 0.25 + control.y * 0.5 + end.y * 0.25,
  };
}

function StructureGraph({ graph, myAvatarUrl }: { graph?: GlobalStructureGraph; myAvatarUrl?: string | null }) {
  const [hoveredUid, setHoveredUid] = useState<string | null>(null);
  const [lockedUid, setLockedUid] = useState<string | null>(null);
  const nodes = graph?.nodes ?? [];
  const max = Math.max(...nodes.map((item) => item.value), 1);
  const min = Math.min(...nodes.map((item) => item.value), max);
  const total = nodes.reduce((sum, node) => sum + node.value, 0);
  const center = { x: 50, y: 58 };
  const graphTitle = graph?.title || '音乐输入';
  const isOutput = graphTitle.includes('输出');
  const activeUid = lockedUid ?? hoveredUid;
  const positionedNodes = nodes.map((node, index) => {
    const ratio = max === min ? 1 : (node.value - min) / Math.max(1, max - min);
    const position = graphNodePosition(graphTitle, node.uid || node.nickname, index, ratio);
    const start = isOutput ? center : position;
    const end = isOutput ? position : center;
    const control = {
      x: (position.x + center.x) / 2 + (index - 2) * 2.2,
      y: (position.y + center.y) / 2 - (index % 2 === 0 ? 9 : 5),
    };
    const path = `M ${start.x} ${start.y} Q ${control.x} ${control.y} ${end.x} ${end.y}`;
    const anchor = quadraticPointAtMiddle(start, control, end);
    return {
      ...node,
      ...position,
      ratio,
      size: 50 + ratio * 30,
      path,
      control,
      anchor,
      share: total > 0 ? node.value / total : 0,
      relationType: ratio >= 0.72 ? '核心输入对象' : ratio >= 0.34 ? '主要连接对象' : '轻量连接对象',
    };
  });
  const activeNode = activeUid ? positionedNodes.find((node) => (node.uid || node.nickname) === activeUid) : null;

  return (
    <section
      className="shadow-global-structure__graph shadow-global-structure__graph--single"
      onPointerDown={() => setLockedUid(null)}
    >
      <div className="shadow-global-structure__network shadow-global-structure__network--single">
        <div className={`shadow-global-structure__soundfield ${activeUid ? 'is-active' : ''}`} />
        <div className="shadow-global-structure__stars" />
        <svg className="shadow-global-structure__edges" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden>
          <defs>
            <filter id="shadow-social-flow-glow" x="-30%" y="-30%" width="160%" height="160%">
              <feGaussianBlur stdDeviation="1.2" result="blur" />
              <feMerge>
                <feMergeNode in="blur" />
                <feMergeNode in="SourceGraphic" />
              </feMerge>
            </filter>
          </defs>
          {positionedNodes.map((node) => (
            <g key={`edge-${graph?.title}-${node.uid || node.nickname}`}>
              <path
                d={node.path}
                className={`shadow-global-structure__edge ${hoveredUid === (node.uid || node.nickname) ? 'is-active' : ''} ${hoveredUid && hoveredUid !== (node.uid || node.nickname) ? 'is-dimmed' : ''}`}
                style={{
                  opacity: activeUid && activeUid !== (node.uid || node.nickname) ? 0.16 : 0.38 + node.ratio * 0.42,
                }}
              />
              <path d={node.path} className="shadow-global-structure__edge-aura" />
              {activeUid === (node.uid || node.nickname) ? (
                <circle r={0.32 + node.ratio * 0.18} className="shadow-global-structure__flow-dot is-active">
                  <animateMotion dur={`${4.2 - node.ratio * 1.2}s`} repeatCount="indefinite" path={node.path} />
                </circle>
              ) : null}
            </g>
          ))}
        </svg>
        {positionedNodes.map((node) => (
          <div
            key={`label-${graph?.title}-${node.uid || node.nickname}`}
            className={`shadow-global-structure__edge-label ${hoveredUid === (node.uid || node.nickname) ? 'is-active' : ''} ${hoveredUid && hoveredUid !== (node.uid || node.nickname) ? 'is-dimmed' : ''}`}
            style={{
              left: `${node.anchor.x}%`,
              top: `${node.anchor.y}%`,
              ['--edge-scale' as string]: String(0.35 + node.ratio * 0.65),
            }}
            onPointerEnter={() => setHoveredUid(node.uid || node.nickname)}
            onPointerLeave={() => setHoveredUid((current) => (current === (node.uid || node.nickname) ? null : current))}
            onPointerDown={(event) => {
              event.stopPropagation();
              setLockedUid((current) => (current === (node.uid || node.nickname) ? null : node.uid || node.nickname));
            }}
          >
            {node.value}
          </div>
        ))}
        <div className="shadow-global-structure__me shadow-global-structure__me--avatar">
          {myAvatarUrl ? <img src={myAvatarUrl} alt="" /> : <span>我</span>}
          <strong>我</strong>
        </div>
        {positionedNodes.length ? (
          positionedNodes.map((node, index) => {
            const key = node.uid || node.nickname;
            const active = activeUid === key;
            const dimmed = Boolean(activeUid) && activeUid !== key;
            return (
              <button
                key={`${graph?.title}-${key}`}
                type="button"
                className={`shadow-global-structure__friend shadow-global-structure__friend--avatar ${active ? 'is-active' : ''} ${dimmed ? 'is-dimmed' : ''}`}
                style={{
                  left: `${node.x}%`,
                  top: `${node.y}%`,
                  width: `${node.size}px`,
                  height: `${node.size}px`,
                  ['--edge-scale' as string]: String(0.35 + node.ratio * 0.65),
                }}
                onPointerEnter={() => setHoveredUid(key)}
                onPointerLeave={() => setHoveredUid((current) => (current === key ? null : current))}
                onPointerDown={(event) => {
                  event.stopPropagation();
                  setLockedUid((current) => (current === key ? null : key));
                }}
              >
                <span className="shadow-global-structure__avatar-frame">
                  {node.ratio >= 0.98 && index === 0 ? <span className="shadow-global-structure__crown">♛</span> : null}
                  {node.avatar_url ? <img src={node.avatar_url} alt="" /> : <UserRound size={Math.max(20, node.size * 0.42)} />}
                </span>
                <strong className="is-above">{node.nickname}</strong>
                <em className="is-above">{node.value} {graphTitle.includes('音乐') ? '首' : '条'}</em>
              </button>
            );
          })
        ) : (
          <div className="shadow-global-empty shadow-global-empty--network">暂无真实节点</div>
        )}
        {activeNode ? (
          <div
            className={`shadow-global-structure__tooltip ${activeNode.x < 50 ? 'is-left' : 'is-right'}`}
            style={{
              left: `${activeNode.x < 50 ? Math.max(12, activeNode.x - 3.2) : Math.min(88, activeNode.x + 3.2)}%`,
              top: `${Math.min(78, Math.max(18, activeNode.y))}%`,
            }}
          >
            <strong>{activeNode.nickname}</strong>
            <span>{graphTitle} {activeNode.value} {graphTitle.includes('音乐') ? '首' : '条'}</span>
            <span>占比 {(activeNode.share * 100).toFixed(1)}%</span>
            <span>关系类型：{activeNode.relationType}</span>
          </div>
        ) : null}
      </div>
    </section>
  );
}

function GlobalStructureSection({ data }: { data: MusicRelationData }) {
  const [activeGraph, setActiveGraph] = useState<'musicInput' | 'musicOutput' | 'chatInput' | 'chatOutput'>('musicInput');
  const structure = data.globalSocialStructure;
  const graphs = {
    musicInput: structure?.musicInputGraph,
    musicOutput: structure?.musicOutputGraph,
    chatInput: structure?.chatInputGraph,
    chatOutput: structure?.chatOutputGraph,
  };
  const graphOptions = [
    { id: 'musicInput' as const, label: '音乐输入' },
    { id: 'musicOutput' as const, label: '音乐输出' },
    { id: 'chatInput' as const, label: '聊天输入' },
    { id: 'chatOutput' as const, label: '聊天输出' },
  ];
  return (
    <section className="shadow-global-block shadow-global-structure">
      <div className="shadow-global-structure__topbar">
        <h3 className="shadow-global-title">音乐社交结构</h3>
        <div className="shadow-global-structure__switches">
          {graphOptions.map((option) => (
            <button
              key={option.id}
              type="button"
              className={`shadow-global-structure__switch ${activeGraph === option.id ? 'is-active' : ''}`}
              onClick={() => setActiveGraph(option.id)}
            >
              {option.label}
            </button>
          ))}
        </div>
      </div>
      <StructureGraph graph={graphs[activeGraph]} myAvatarUrl={data.globalHero?.myAvatarUrl} />
    </section>
  );
}

export function GlobalMusicSocialProfile({ data, exportPayload, exportMessage, exporting, onExport }: GlobalMusicSocialProfileProps) {
  const [activeSection, setActiveSection] = useState('hero');
  const [copyMessage, setCopyMessage] = useState('');
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const heroRef = useRef<HTMLDivElement | null>(null);
  const top3Ref = useRef<HTMLDivElement | null>(null);
  const structureRef = useRef<HTMLDivElement | null>(null);
  const riverRef = useRef<HTMLDivElement | null>(null);
  const worldRef = useRef<HTMLDivElement | null>(null);
  const exportRef = useRef<HTMLDivElement | null>(null);
  const viewModel = useMemo(() => buildGlobalViewModel(data), [data]);

  const sections = useMemo(
    () => [
      { id: 'hero', label: '全局恒星环', ref: heroRef },
      { id: 'top3', label: '关系 Top3', ref: top3Ref },
      { id: 'structure', label: '社交结构', ref: structureRef },
      { id: 'river', label: '时间长河', ref: riverRef },
      { id: 'world', label: '共同音乐世界', ref: worldRef },
      { id: 'export', label: '导出与操作', ref: exportRef },
    ],
    [],
  );

  useEffect(() => {
    const root = scrollRef.current;
    if (!root) return;
    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((entry) => entry.isIntersecting)
          .sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0];
        const id = visible?.target.getAttribute('data-section-id');
        if (id) setActiveSection(id);
      },
      { root, threshold: [0.3, 0.45, 0.6], rootMargin: '-12% 0px -12% 0px' },
    );
    sections.forEach((section) => {
      if (section.ref.current) observer.observe(section.ref.current);
    });
    return () => observer.disconnect();
  }, [sections]);

  const scrollToSection = (id: string) => {
    const root = scrollRef.current;
    const target = sections.find((section) => section.id === id)?.ref.current;
    if (!root || !target) return;
    const maxScroll = Math.max(0, root.scrollHeight - root.clientHeight);
    root.scrollTo({ top: Math.min(Math.max(0, target.offsetTop - 8), maxScroll), behavior: 'auto' });
  };

  const handleCopyPrompt = async () => {
    try {
      const payload = await onExport();
      if (!payload?.prompt_text) {
        setCopyMessage('请先生成整体音乐社交分析。');
        return;
      }
      await navigator.clipboard.writeText(payload.prompt_text);
      setCopyMessage('整体音乐社交 AI Prompt 已复制。');
    } catch {
      setCopyMessage('复制失败，请重试。');
    }
  };

  return (
    <div ref={scrollRef} className="shadow-archive-scroll flex-1 min-h-0 overflow-y-auto pr-2 scrollbar-none">
      <div className="shadow-archive-nav" aria-label="我的音乐社交内容导航">
        {sections.map((section) => (
          <button
            key={section.id}
            type="button"
            className={`shadow-archive-nav__item ${activeSection === section.id ? 'is-active' : ''}`}
            onClick={() => scrollToSection(section.id)}
            aria-label={section.label}
          >
            <span className="shadow-archive-nav__label">{section.label}</span>
            <span className="shadow-archive-nav__dot" />
          </button>
        ))}
      </div>
      <div className="shadow-archive-stack shadow-global-stack min-h-full">
        <div ref={heroRef} data-section-id="hero" className="shadow-archive-section shadow-archive-section--hero">
          <GlobalOrbitHero data={data} />
        </div>
        <div ref={top3Ref} data-section-id="top3" className="shadow-archive-section shadow-global-section">
          <GlobalTop3Section data={data} />
        </div>
        <div ref={structureRef} data-section-id="structure" className="shadow-archive-section shadow-global-section">
          <GlobalStructureSection data={data} />
        </div>
        <div ref={riverRef} data-section-id="river" className="shadow-archive-section shadow-archive-section--river">
          <SonicTimelineRiver data={data} viewModel={viewModel} enableHourMode />
        </div>
        <div ref={worldRef} data-section-id="world" className="shadow-archive-section shadow-archive-section--world">
          <SharedSoundWorld data={data} viewModel={viewModel} />
        </div>
        <section ref={exportRef} data-section-id="export" className="shadow-export-dock shadow-archive-section shadow-archive-section--export">
          <div className="shadow-export-dock__copy">
            <h3 className="shadow-export-dock__title">导出与操作</h3>
            <p>复制整体音乐社交 AI Prompt 后直接贴到外部模型。</p>
          </div>
          <div className="shadow-export-dock__actions">
            <button type="button" className="shadow-export-dock__button is-secondary" onClick={() => void handleCopyPrompt()} disabled={exporting}>
              <Copy size={15} />
              {exportPayload ? '复制 AI Prompt' : exporting ? '生成中...' : '生成并复制 AI Prompt'}
            </button>
          </div>
          <div className="shadow-export-dock__tips">
            <span>1. 点击复制 AI Prompt。</span>
            <span>2. 粘贴到外部 AI。</span>
            <span>3. 直接 AI 进行分析。</span>
          </div>
          {exportMessage ? <div className="shadow-export-dock__status">{exportMessage}</div> : null}
          {copyMessage ? <div className="shadow-export-dock__status is-copy">{copyMessage}</div> : null}
        </section>
      </div>
    </div>
  );
}
