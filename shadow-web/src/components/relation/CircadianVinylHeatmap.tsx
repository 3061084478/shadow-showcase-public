import { useMemo, useRef, useState } from 'react';
import type { PointerEvent as ReactPointerEvent } from 'react';
import type { MusicRelationData } from '../../types';
import type { SingleFriendProfileViewModel } from './relationViewModel';

type CircadianVinylHeatmapProps = {
  data: MusicRelationData;
  viewModel: SingleFriendProfileViewModel;
};

type VinylMode = '消息' | '歌曲';

type HourSegment = {
  hour: number;
  value: number;
  ratio: number;
  start: number;
  end: number;
  path: string;
  innerRadius: number;
  outerRadius: number;
};

const CENTER = 380;

function polar(cx: number, cy: number, radius: number, angle: number) {
  return {
    x: cx + Math.cos(angle) * radius,
    y: cy + Math.sin(angle) * radius,
  };
}

function arcSector(cx: number, cy: number, inner: number, outer: number, start: number, end: number) {
  const p1 = polar(cx, cy, inner, start);
  const p2 = polar(cx, cy, inner, end);
  const p3 = polar(cx, cy, outer, end);
  const p4 = polar(cx, cy, outer, start);
  const largeArc = end - start > Math.PI ? 1 : 0;
  return `M ${p1.x} ${p1.y} A ${inner} ${inner} 0 ${largeArc} 1 ${p2.x} ${p2.y} L ${p3.x} ${p3.y} A ${outer} ${outer} 0 ${largeArc} 0 ${p4.x} ${p4.y} Z`;
}

function findHourWindow(values: number[]) {
  if (!values.length) {
    return null;
  }
  let bestHour = 0;
  let bestValue = values[0] ?? 0;
  let lowHour = 0;
  let lowValue = values[0] ?? 0;
  values.forEach((value, hour) => {
    if (value > bestValue) {
      bestValue = value;
      bestHour = hour;
    }
    if (value < lowValue) {
      lowValue = value;
      lowHour = hour;
    }
  });
  return {
    peakHour: bestHour,
    peakValue: bestValue,
    lowHour,
    lowValue,
  };
}

function findPositiveHourWindow(values: number[]) {
  const positive = values
    .map((value, hour) => ({ value, hour }))
    .filter((item) => item.value > 0);
  if (!positive.length) return null;
  const peak = positive.reduce((best, item) => (item.value > best.value ? item : best), positive[0]);
  const low = positive.reduce((best, item) => (item.value < best.value ? item : best), positive[0]);
  return {
    peakHour: peak.hour,
    peakValue: peak.value,
    lowHour: low.hour,
    lowValue: low.value,
  };
}

function buildSummaryLines(summary: ReturnType<typeof findHourWindow>, mode: VinylMode) {
  if (!summary || summary.peakValue <= 0) {
    return ['活跃高点：暂无', '低频时段：暂无'];
  }
  return [
    `活跃高点：${String(summary.peakHour).padStart(2, '0')}:00 · ${mode} ${summary.peakValue}`,
    `低频时段：${String(summary.lowHour).padStart(2, '0')}:00 · ${mode} ${summary.lowValue}`,
  ];
}

function getTimeRangeLabel(hour: number) {
  if (hour >= 0 && hour <= 4) return '极暗';
  if (hour >= 5 && hour <= 10) return '白昼';
  if (hour >= 11 && hour <= 17) return '午间';
  return '夜间';
}

function getIntensityLabel(value: number, maxValue: number) {
  if (maxValue <= 0 || value <= 0) return '无声';
  const ratio = value / maxValue;
  if (ratio >= 0.75) return '高频';
  if (ratio >= 0.4) return '回响';
  if (ratio >= 0.15) return '余温';
  return '低频';
}

function getHourLabel(hour: number, value: number, maxValue: number) {
  return `${getTimeRangeLabel(hour)}${getIntensityLabel(value, maxValue)}`;
}

function getHourTone(hour: number) {
  if (hour <= 4) return { fill: 'rgba(125, 112, 255, 0.3)', stroke: '#8f82ff' };
  if (hour <= 10) return { fill: 'rgba(94, 210, 255, 0.28)', stroke: '#74e1ff' };
  if (hour <= 17) return { fill: 'rgba(86, 233, 212, 0.28)', stroke: '#69efd7' };
  if (hour <= 21) return { fill: 'rgba(255, 132, 223, 0.28)', stroke: '#ff95ea' };
  return { fill: 'rgba(190, 122, 255, 0.28)', stroke: '#c191ff' };
}

function normalizeAngle(angle: number) {
  const full = Math.PI * 2;
  let result = angle % full;
  if (result < 0) result += full;
  return result;
}

function buildSegments(values: number[]) {
  const max = Math.max(...values, 1);
  return values.map<HourSegment>((value, hour) => {
    const ratio = value / max;
    const start = (hour / 24) * Math.PI * 2 - Math.PI / 2;
    const end = ((hour + 1) / 24) * Math.PI * 2 - Math.PI / 2;
    const innerRadius = 214;
    const outerRadius = 244 + ratio * 44;
    return {
      hour,
      value,
      ratio,
      start,
      end,
      path: arcSector(CENTER, CENTER, innerRadius, outerRadius, start + 0.02, end - 0.02),
      innerRadius,
      outerRadius,
    };
  });
}

function normalizeHourSeries(items: MusicRelationData['heatmapHours']) {
  const map = new Map(items.map((item) => [item.hour, item.count]));
  return Array.from({ length: 24 }, (_, hour) => map.get(hour) ?? 0);
}

function resolveHoveredHour(
  event: ReactPointerEvent<SVGSVGElement>,
  rect: DOMRect,
  segments: HourSegment[],
) {
  const x = ((event.clientX - rect.left) / rect.width) * 760;
  const y = ((event.clientY - rect.top) / rect.height) * 760;
  const dx = x - CENTER;
  const dy = y - CENTER;
  const radius = Math.sqrt(dx * dx + dy * dy);
  const angle = normalizeAngle(Math.atan2(dy, dx));

  return segments.find((segment) => {
    const start = normalizeAngle(segment.start);
    const end = normalizeAngle(segment.end);
    const inRadius = radius >= segment.innerRadius - 12 && radius <= 304;
    const inAngle = start <= end ? angle >= start && angle <= end : angle >= start || angle <= end;
    return inRadius && inAngle;
  })?.hour ?? null;
}

export function CircadianVinylHeatmap({ data, viewModel }: CircadianVinylHeatmapProps) {
  const [mode, setMode] = useState<VinylMode>('消息');
  const [hoveredHour, setHoveredHour] = useState<number | null>(null);
  const svgRef = useRef<SVGSVGElement | null>(null);

  const messageSeries = normalizeHourSeries(data.heatmapHours);
  const songSeries = normalizeHourSeries(data.songHeatmapHours);
  const values = mode === '消息' ? messageSeries : songSeries;
  const segments = useMemo(() => buildSegments(values), [values]);
  const hovered = hoveredHour === null ? null : segments.find((segment) => segment.hour === hoveredHour) ?? null;
  const summary = useMemo(() => findPositiveHourWindow(values), [values]);
  const maxValue = Math.max(...values, 0);
  const handlePointerMove = (event: ReactPointerEvent<SVGSVGElement>) => {
    const rect = svgRef.current?.getBoundingClientRect();
    if (!rect) return;
    setHoveredHour(resolveHoveredHour(event, rect, segments));
  };

  const centerLine = hovered
    ? {
        title: `${String(hovered.hour).padStart(2, '0')}:00`,
        label: getHourLabel(hovered.hour, hovered.value, maxValue),
        meta: `${mode}数量 · ${hovered.value}`,
      }
      : {
          title: '选择一个时段',
          label: '移动到外圈查看时段',
          meta: values.some((value) => value > 0) ? `${mode}模式` : `${mode}暂无时段数据`,
        };

  const notes = buildSummaryLines(summary, mode);

  return (
    <section className="shadow-vinyl">
      <div className="shadow-vinyl__bridge" />
      <div className="shadow-vinyl__head">
        <h3 className="shadow-vinyl__title">24 小时环形唱片机</h3>
      </div>

      <div className="shadow-vinyl__machine">
        <div className="shadow-vinyl__modebar">
          {(['消息', '歌曲'] as const).map((item) => (
            <button key={item} type="button" className={`shadow-vinyl__modekey ${mode === item ? 'is-active' : ''}`} onClick={() => setMode(item)}>
              {item}
            </button>
          ))}
        </div>

        <div className="shadow-vinyl__shell">
          <div className="shadow-vinyl__summary shadow-vinyl__summary--peak">
            <span>高频总结</span>
            <strong>{notes[0]}</strong>
          </div>

          <div className="shadow-vinyl__deck">
            <div className="shadow-vinyl__glow shadow-vinyl__glow--blue" />
            <div className="shadow-vinyl__glow shadow-vinyl__glow--pink" />

            <svg
              ref={svgRef}
              viewBox="0 0 760 760"
              className="shadow-vinyl__svg"
              aria-hidden
              onPointerMove={handlePointerMove}
              onPointerLeave={() => setHoveredHour(null)}
            >
              <defs>
                <radialGradient id="shadow-vinyl-body">
                  <stop offset="0%" stopColor="rgba(22, 24, 33, 0.88)" />
                  <stop offset="58%" stopColor="rgba(8, 9, 15, 0.98)" />
                  <stop offset="100%" stopColor="rgba(2, 3, 7, 1)" />
                </radialGradient>
                <radialGradient id="shadow-vinyl-center">
                  <stop offset="0%" stopColor="rgba(12, 17, 28, 0.96)" />
                  <stop offset="100%" stopColor="rgba(8, 9, 16, 0.98)" />
                </radialGradient>
              </defs>

              <circle cx={CENTER} cy={CENTER} r="292" fill="url(#shadow-vinyl-body)" />
              {Array.from({ length: 46 }, (_, index) => (
                <circle key={index} cx={CENTER} cy={CENTER} r={118 + index * 4.2} fill="none" stroke="rgba(255,255,255,0.03)" strokeWidth="1" />
              ))}

              {segments.map((segment) => (
                <path
                  key={`slot-${segment.hour}`}
                  d={arcSector(CENTER, CENTER, 214, 290, segment.start + 0.018, segment.end - 0.018)}
                  fill="rgba(255,255,255,0.018)"
                  stroke="rgba(255,255,255,0.045)"
                  strokeWidth="0.75"
                />
              ))}

              {segments.map((segment) => {
                const tone = getHourTone(segment.hour);
                const active = hovered?.hour === segment.hour;
                return (
                  <path
                    key={`active-${segment.hour}`}
                    d={segment.path}
                    fill={tone.fill}
                    stroke={active ? tone.stroke : 'rgba(255,255,255,0.08)'}
                    strokeWidth={active ? 2 : 0.8}
                    opacity={active ? 1 : 0.18 + segment.ratio * 0.24}
                    filter={active ? `drop-shadow(0 0 10px ${tone.stroke})` : undefined}
                  />
                );
              })}

              {segments.map((segment) => {
                const labelPoint = polar(CENTER, CENTER, 320, (segment.start + segment.end) / 2);
                return (
                  <text
                    key={`label-${segment.hour}`}
                    x={labelPoint.x}
                    y={labelPoint.y}
                    textAnchor="middle"
                    className={`shadow-vinyl__hour ${hovered?.hour === segment.hour ? 'is-active' : ''}`}
                  >
                    {String(segment.hour).padStart(2, '0')}
                  </text>
                );
              })}

              <circle cx={CENTER} cy={CENTER} r="108" fill="url(#shadow-vinyl-center)" stroke="rgba(255,255,255,0.08)" strokeWidth="1.3" />
              <circle cx={CENTER} cy={CENTER} r="58" fill="rgba(6,8,14,0.96)" stroke="rgba(255,255,255,0.06)" strokeWidth="1" />
            </svg>

            <div className="shadow-vinyl__center">
              <div className="shadow-vinyl__center-hour">{centerLine.title}</div>
              <div className="shadow-vinyl__center-label">{centerLine.label}</div>
              <div className="shadow-vinyl__center-mode">{centerLine.meta}</div>
            </div>
          </div>

          <div className="shadow-vinyl__summary shadow-vinyl__summary--low">
            <span>低频总结</span>
            <strong>{notes[1]}</strong>
          </div>
        </div>
      </div>
    </section>
  );
}
