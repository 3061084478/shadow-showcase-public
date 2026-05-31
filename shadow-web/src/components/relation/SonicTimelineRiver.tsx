import { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { motion, useReducedMotion } from 'motion/react';
import type { MusicRelationData } from '../../types';
import type { SingleFriendProfileViewModel } from './relationViewModel';

type SonicTimelineRiverProps = {
  data: MusicRelationData;
  viewModel: SingleFriendProfileViewModel;
  enableHourMode?: boolean;
};

type EventKind = 'origin' | 'burst' | 'fade' | 'peak' | 'rise' | 'steady';
type LineHover = { type: 'message' | 'song'; period: string; value: number; xPercent: number; yPercent: number } | null;
type RiverMode = 'month' | 'hour';
type MilestoneTarget = 'message' | 'song';
type RiverSourceItem = { period: string; messageCountRaw: number; distinctSongCount: number };
type LineMilestone = {
  id: string;
  period: string;
  title: string;
  description: string;
  kind: EventKind;
  target: MilestoneTarget;
};

function noteGlyph(kind: EventKind) {
  if (kind === 'burst') return '♫';
  if (kind === 'fade') return '♭';
  if (kind === 'peak') return '𝄞';
  if (kind === 'rise') return '♬';
  if (kind === 'steady') return '♪';
  return '♩';
}

function buildSoftLine(points: Array<{ x: number; y: number }>) {
  if (!points.length) return '';
  let path = `M ${points[0].x} ${points[0].y}`;
  for (let index = 0; index < points.length - 1; index += 1) {
    const current = points[index];
    const next = points[index + 1];
    const cx = (current.x + next.x) / 2;
    path += ` Q ${cx} ${current.y} ${next.x} ${next.y}`;
  }
  return path;
}

function buildHourSource(data: MusicRelationData) {
  const messageMap = new Map(data.heatmapHours.map((item) => [item.hour, item.count]));
  const songMap = new Map(data.songHeatmapHours.map((item) => [item.hour, item.count]));
  return Array.from({ length: 24 }, (_, hour) => ({
    period: `${String(hour).padStart(2, '0')}:00`,
    messageCountRaw: messageMap.get(hour) ?? 0,
    distinctSongCount: songMap.get(hour) ?? 0,
    hour,
  }));
}

function preferredKind(current: EventKind, next: EventKind) {
  const priority: Record<EventKind, number> = {
    peak: 5,
    burst: 4,
    rise: 3,
    fade: 2,
    steady: 1,
    origin: 0,
  };
  return priority[next] > priority[current] ? next : current;
}

function buildLineMilestones(points: RiverSourceItem[], label: '时段' | '月份', includeChangeMarkers: boolean) {
  const hasMessageData = points.some((item) => item.messageCountRaw > 0);
  const hasSongData = points.some((item) => item.distinctSongCount > 0);
  const markerMap = new Map<string, LineMilestone>();
  const previousLabel = label === '月份' ? '上个月' : '上一时段';
  const addMarker = (marker: LineMilestone) => {
    const key = `${marker.target}-${marker.period}`;
    const existing = markerMap.get(key);
    if (!existing) {
      markerMap.set(key, marker);
      return;
    }
    const titles = existing.title.split(' / ');
    if (!titles.includes(marker.title)) titles.push(marker.title);
    markerMap.set(key, {
      ...existing,
      id: `${existing.id}-${marker.id}`,
      title: titles.join(' / '),
      description: [existing.description, marker.description].filter(Boolean).join('\n'),
      kind: preferredKind(existing.kind, marker.kind),
    });
  };
  const addChangeMarkers = (
    target: MilestoneTarget,
    valueKey: 'messageCountRaw' | 'distinctSongCount',
    titlePrefix: '信息' | '歌曲',
    unit: '条' | '首',
  ) => {
    if (!includeChangeMarkers || points.length < 2) return;
    const changes = points.slice(1).map((item, index) => {
      const previous = points[index];
      return {
        item,
        delta: item[valueKey] - previous[valueKey],
      };
    });
    const burst = changes.reduce((best, item) => (item.delta > best.delta ? item : best), changes[0]);
    const drop = changes.reduce((best, item) => (item.delta < best.delta ? item : best), changes[0]);
    if (burst.delta > 0) {
      addMarker({
        id: `${target}-burst-${burst.item.period}`,
        period: burst.item.period,
        title: `${titlePrefix}爆发`,
        description: `${burst.item.period} 是${label}里的${titlePrefix}爆发点，较${previousLabel}增加 ${burst.delta} ${unit}。`,
        kind: 'burst',
        target,
      });
    }
    if (drop.delta < 0) {
      addMarker({
        id: `${target}-drop-${drop.item.period}`,
        period: drop.item.period,
        title: `${titlePrefix}下跌`,
        description: `${drop.item.period} 是${label}里的${titlePrefix}下跌点，较${previousLabel}减少 ${Math.abs(drop.delta)} ${unit}。`,
        kind: 'fade',
        target,
      });
    }
  };
  if (hasMessageData) {
    const peak = points.reduce((best, item) => (item.messageCountRaw > best.messageCountRaw ? item : best), points[0]);
    const positive = points.filter((item) => item.messageCountRaw > 0);
    const low = positive.reduce((best, item) => (item.messageCountRaw < best.messageCountRaw ? item : best), positive[0]);
    addMarker({
      id: `message-peak-${peak.period}`,
      period: peak.period,
      title: '信息高峰',
      description: `${peak.period} 是${label}里的信息高峰，信息 ${peak.messageCountRaw} 条。`,
      kind: 'peak',
      target: 'message',
    });
    if (low && low.period !== peak.period) {
      addMarker({
        id: `message-low-${low.period}`,
        period: low.period,
        title: '信息低频',
        description: `${low.period} 是有记录${label}里的信息低频点，信息 ${low.messageCountRaw} 条。`,
        kind: 'fade',
        target: 'message',
      });
    }
    addChangeMarkers('message', 'messageCountRaw', '信息', '条');
  }
  if (hasSongData) {
    const peak = points.reduce((best, item) => (item.distinctSongCount > best.distinctSongCount ? item : best), points[0]);
    const positive = points.filter((item) => item.distinctSongCount > 0);
    const low = positive.reduce((best, item) => (item.distinctSongCount < best.distinctSongCount ? item : best), positive[0]);
    addMarker({
      id: `song-peak-${peak.period}`,
      period: peak.period,
      title: '歌曲高峰',
      description: `${peak.period} 是${label}里的歌曲分享高峰，歌曲 ${peak.distinctSongCount} 首。`,
      kind: 'peak',
      target: 'song',
    });
    if (low && low.period !== peak.period) {
      addMarker({
        id: `song-low-${low.period}`,
        period: low.period,
        title: '歌曲低频',
        description: `${low.period} 是有记录${label}里的歌曲低频点，歌曲 ${low.distinctSongCount} 首。`,
        kind: 'fade',
        target: 'song',
      });
    }
    addChangeMarkers('song', 'distinctSongCount', '歌曲', '首');
  }
  return Array.from(markerMap.values());
}

function normalizeRatio(value: number, maxValue: number) {
  if (maxValue <= 0) return 0;
  return Math.max(0, Math.min(1, value / maxValue));
}

function resolveMilestoneY(
  target: MilestoneTarget,
  point: { messageY: number; songY: number },
  kind: EventKind,
) {
  const lift = kind === 'peak' || kind === 'burst' ? 32 : 28;
  if (target === 'message') return point.messageY - lift;
  if (target === 'song') return point.songY - lift;
  return point.messageY - lift;
}

export function SonicTimelineRiver({ data, enableHourMode = false }: SonicTimelineRiverProps) {
  const reduceMotion = useReducedMotion();
  const [riverMode, setRiverMode] = useState<RiverMode>('month');
  const [activeEventId, setActiveEventId] = useState<string | null>(null);
  const [lineHover, setLineHover] = useState<LineHover>(null);
  const canvasRef = useRef<HTMLDivElement | null>(null);
  const [canvasRect, setCanvasRect] = useState<DOMRect | null>(null);
  const monthSource = data.trendSeries;
  const hourSource = buildHourSource(data);
  const source = enableHourMode && riverMode === 'hour' ? hourSource : monthSource;
  const isHourMode = enableHourMode && riverMode === 'hour';
  const visiblePointCount = 12;
  const pointGap = 132;
  const sidePadding = 110;
  const baseWidth = sidePadding * 2 + (visiblePointCount - 1) * pointGap;
  const width = source.length > visiblePointCount ? sidePadding * 2 + (source.length - 1) * pointGap : baseWidth;
  const canvasWidth = source.length > visiblePointCount ? `${width}px` : '100%';
  const height = 440;

  const maxMessage = Math.max(...source.map((item) => item.messageCountRaw), 1);
  const maxSongs = Math.max(...source.map((item) => item.distinctSongCount), 1);

  const points = source.map((item, index) => {
    const gap = source.length > visiblePointCount ? pointGap : (width - sidePadding * 2) / Math.max(source.length - 1, 1);
    const x = source.length === 1 ? width / 2 : sidePadding + index * gap;
    const messageY = 182 - normalizeRatio(item.messageCountRaw, maxMessage) * 42 + (isHourMode ? 0 : Math.sin(index * 0.62) * 4);
    const songY = 298 + (1 - normalizeRatio(item.distinctSongCount, maxSongs)) * 50 + (isHourMode ? 0 : Math.cos(index * 0.88) * 4);
    return {
      period: item.period,
      x,
      xPercent: (x / width) * 100,
      messageY,
      messagePercent: (messageY / height) * 100,
      songY,
      songPercent: (songY / height) * 100,
      messageCount: item.messageCountRaw,
      songCount: item.distinctSongCount,
    };
  });

  useEffect(() => {
    const updateRect = () => {
      if (!canvasRef.current) return;
      setCanvasRect(canvasRef.current.getBoundingClientRect());
    };
    updateRect();
    window.addEventListener('resize', updateRect);
    window.addEventListener('scroll', updateRect, true);
    return () => {
      window.removeEventListener('resize', updateRect);
      window.removeEventListener('scroll', updateRect, true);
    };
  }, []);

  const messageLine = buildSoftLine(points.map((point) => ({ x: point.x, y: point.messageY })));
  const songLine = buildSoftLine(points.map((point) => ({ x: point.x, y: point.songY })));
  const messageGlow = buildSoftLine(points.map((point) => ({ x: point.x, y: point.messageY + 6 })));
  const songGlow = buildSoftLine(points.map((point) => ({ x: point.x, y: point.songY + 5 })));
  const milestoneSource = buildLineMilestones(source, isHourMode ? '时段' : '月份', !isHourMode);

  const milestones = milestoneSource
    .map((marker) => {
      const point = points.find((item) => item.period === marker.period);
      if (!point) return null;
      const markerTarget: MilestoneTarget = marker.target === 'message' ? 'message' : 'song';
      const y = resolveMilestoneY(markerTarget, point, marker.kind);
      return {
        ...marker,
        target: markerTarget,
        x: point.x,
        xPercent: point.xPercent,
        y,
        yPercent: (y / height) * 100,
      };
    })
    .filter(Boolean);

  const activeMilestone = activeEventId ? milestones.find((item) => item && item.id === activeEventId) ?? null : null;
  const activeMilestoneRect = activeMilestone && canvasRef.current ? canvasRef.current.getBoundingClientRect() : canvasRect;

  return (
    <section className="shadow-river">
      <div className="shadow-river__bridge shadow-river__bridge--top" />
      <div className="shadow-river__copy">
        <div className="shadow-river__copybar">
          <div>
            <h3 className="shadow-river__title">音乐长河</h3>
          </div>
        </div>
      </div>

      <div className={`shadow-river__stage shadow-river__stage--pulse ${enableHourMode ? 'shadow-river__stage--with-switch' : ''}`}>
        {enableHourMode ? (
          <div className="shadow-river__mode-switch shadow-river__mode-switch--dock">
            {([
              { id: 'month', label: '月份长河' },
              { id: 'hour', label: '时段长河' },
            ] as const).map((item) => (
              <button
                key={item.id}
                type="button"
                className={`shadow-river__mode-key ${riverMode === item.id ? 'is-active' : ''}`}
                onClick={() => {
                  setRiverMode(item.id);
                  setActiveEventId(null);
                  setLineHover(null);
                }}
              >
                {item.label}
              </button>
            ))}
          </div>
        ) : null}
        <div className="shadow-river__legend shadow-river__legend--dock">
          <span className="shadow-river__legend-item shadow-river__legend-item--blue">信息线</span>
          <span className="shadow-river__legend-item shadow-river__legend-item--pink">歌曲线</span>
        </div>
        <div className="shadow-river__mist shadow-river__mist--blue" />
        <div className="shadow-river__mist shadow-river__mist--pink" />

        <div className="shadow-river__scroll">
          {source.length === 0 ? (
            <div className="shadow-river__empty">当前还没有可绘制的时间长河数据</div>
          ) : (
          <div ref={canvasRef} className="shadow-river__canvas" style={{ width: canvasWidth }}>
            <svg viewBox={`0 0 ${width} ${height}`} className="shadow-river__svg shadow-river__svg--pulse" preserveAspectRatio="none" aria-hidden>
              <defs>
                <linearGradient id="shadow-river-line-blue" x1="0" x2="1">
                  <stop offset="0%" stopColor="rgba(122, 222, 255, 0.1)" />
                  <stop offset="24%" stopColor="rgba(122, 222, 255, 0.68)" />
                  <stop offset="100%" stopColor="rgba(79, 141, 255, 0.36)" />
                </linearGradient>
                <linearGradient id="shadow-river-line-pink" x1="0" x2="1">
                  <stop offset="0%" stopColor="rgba(255, 162, 238, 0.08)" />
                  <stop offset="30%" stopColor="rgba(255, 152, 233, 0.58)" />
                  <stop offset="100%" stopColor="rgba(176, 95, 255, 0.34)" />
                </linearGradient>
              </defs>

              <path d={messageGlow} fill="none" stroke="rgba(115, 214, 255, 0.11)" strokeWidth="10" strokeLinecap="round" />
              <path d={songGlow} fill="none" stroke="rgba(255, 150, 231, 0.09)" strokeWidth="8" strokeLinecap="round" />

              <motion.path
                d={messageLine}
                fill="none"
                stroke="url(#shadow-river-line-blue)"
                strokeWidth="4"
                strokeLinecap="round"
                initial={reduceMotion ? undefined : { pathLength: 0, opacity: 0.34 }}
                whileInView={reduceMotion ? undefined : { pathLength: 1, opacity: 1 }}
                viewport={{ once: true, amount: 0.22 }}
                transition={{ duration: 1.15, ease: [0.16, 1, 0.3, 1] }}
              />
              <motion.path
                d={songLine}
                fill="none"
                stroke="url(#shadow-river-line-pink)"
                strokeWidth="3.2"
                strokeLinecap="round"
                initial={reduceMotion ? undefined : { pathLength: 0, opacity: 0.3 }}
                whileInView={reduceMotion ? undefined : { pathLength: 1, opacity: 1 }}
                viewport={{ once: true, amount: 0.22 }}
                transition={{ duration: 1.18, delay: 0.05, ease: [0.16, 1, 0.3, 1] }}
              />

              {points.map((point) => (
                <g key={point.period}>
                  <line x1={point.x} x2={point.x} y1="348" y2="370" stroke="rgba(255,255,255,0.06)" strokeWidth="1" />
                  <text x={point.x} y="398" textAnchor="middle" className="shadow-river__month">
                    {point.period}
                  </text>
                </g>
              ))}
            </svg>

            <div className="shadow-river__line-hover-layer">
          {points.map((point) => (
            <div key={`msg-${point.period}`} className="shadow-river__dot-wrap" style={{ left: `${point.xPercent}%`, top: `${point.messagePercent}%` }}>
              <button
                type="button"
                className={`shadow-river__dot shadow-river__dot--message ${lineHover?.type === 'message' && lineHover.period === point.period ? 'is-active' : ''}`}
                onPointerEnter={() => setLineHover({ type: 'message', period: point.period, value: point.messageCount, xPercent: point.xPercent, yPercent: point.messagePercent })}
                onPointerLeave={() => setLineHover((current) => (current?.type === 'message' && current.period === point.period ? null : current))}
              />
            </div>
          ))}
          {points.map((point) => (
            <div key={`song-${point.period}`} className="shadow-river__dot-wrap" style={{ left: `${point.xPercent}%`, top: `${point.songPercent}%` }}>
              <button
                type="button"
                className={`shadow-river__dot shadow-river__dot--song ${lineHover?.type === 'song' && lineHover.period === point.period ? 'is-active' : ''}`}
                onPointerEnter={() => setLineHover({ type: 'song', period: point.period, value: point.songCount, xPercent: point.xPercent, yPercent: point.songPercent })}
                onPointerLeave={() => setLineHover((current) => (current?.type === 'song' && current.period === point.period ? null : current))}
              />
            </div>
          ))}
            </div>

            <div className="shadow-river__events shadow-river__events--pulse">
          {milestones.map((milestone) => {
            if (!milestone) return null;
            const active = activeEventId === milestone.id;
            return (
              <button
                key={milestone.id}
                type="button"
                className={`shadow-river__event shadow-river__event--${milestone.kind} shadow-river__event--target-${milestone.target ?? 'middle'} ${active ? 'is-active' : ''}`}
                style={{ left: `${milestone.xPercent}%`, top: `${milestone.yPercent}%` }}
                onPointerEnter={() => setActiveEventId(milestone.id)}
                onPointerLeave={() => setActiveEventId((current) => (current === milestone.id ? null : current))}
                onFocus={() => setActiveEventId(milestone.id)}
                onBlur={() => setActiveEventId(null)}
              >
                <span className="shadow-river__event-glyph shadow-river__event-glyph--plain">{noteGlyph(milestone.kind)}</span>
              </button>
            );
          })}
            </div>
            {lineHover ? (
              <div
                className="shadow-river__value-tag"
                style={{ left: `calc(${lineHover.xPercent}% + 14px)`, top: `calc(${lineHover.yPercent}% - 18px)` }}
              >
                <strong>{lineHover.period}</strong>
                <span>{lineHover.type === 'message' ? `信息 ${lineHover.value}` : `歌曲 ${lineHover.value}`}</span>
              </div>
            ) : null}
          </div>
          )}
        </div>

        {activeMilestone
          && activeMilestoneRect
          ? createPortal(
              <div
                className="shadow-river__tag shadow-river__tag--portal"
                style={{
                  left: `${Math.min(window.innerWidth - 320, activeMilestoneRect.left + (activeMilestone.xPercent / 100) * activeMilestoneRect.width + 20)}px`,
                  top: `${Math.max(18, activeMilestoneRect.top + (activeMilestone.yPercent / 100) * activeMilestoneRect.height - 18)}px`,
                }}
              >
                <div className="shadow-river__tag-title">{activeMilestone.period}｜{activeMilestone.title}</div>
                <div className="shadow-river__tag-line">{activeMilestone.description}</div>
              </div>,
              document.body,
            )
          : null}
      </div>
    </section>
  );
}
