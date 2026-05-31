import { useEffect, useMemo, useState } from 'react';
import { motion, useReducedMotion } from 'motion/react';
import { UserRound } from 'lucide-react';
import type { FriendListItemLite, MusicRelationData } from '../../types';
import type { OrbitItem, OrbitTrait, SingleFriendProfileViewModel } from './relationViewModel';

type FriendOrbitHeroProps = {
  data: MusicRelationData;
  friend?: FriendListItemLite;
  viewModel: SingleFriendProfileViewModel;
};

type NodeTone = 'blue' | 'pink' | 'violet' | 'green' | 'neutral';

type OrbitRenderNode = {
  id: string;
  label: string;
  value?: string;
  tooltip: string;
  tone: NodeTone;
  x: number;
  y: number;
  depth: number;
  scale: number;
  alpha: number;
  zIndex: number;
  visible: boolean;
};

type OrbitTrackProps = {
  className: string;
  items: OrbitItem[] | OrbitTrait[];
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
};

const TRACK_TILT = -12;

function normalizeAngle(angle: number) {
  const mod = angle % 360;
  return mod < 0 ? mod + 360 : mod;
}

function buildNodePosition(
  item: OrbitItem | OrbitTrait,
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
  const x = Math.cos(rad) * radiusX;
  const y = Math.sin(rad) * radiusY;
  const frontness = Math.max(0, depth);
  const visible = depth > 0.08;
  return {
    id: item.id,
    label: item.label,
    value: 'value' in item ? item.value : undefined,
    tooltip: item.tooltip,
    tone: item.tone as NodeTone,
    x,
    y,
    depth,
    scale: 0.78 + frontness * 0.38,
    alpha: visible ? 0.42 + frontness * 0.58 : 0,
    zIndex: Math.round((depth + 1) * 100),
    visible,
  };
}

function OrbitTrack({
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
}: OrbitTrackProps) {
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
        const hitboxClass = `shadow-orbit-track__hitbox shadow-orbit-track__hitbox--${trackType} ${selected ? 'is-selected' : ''} ${dimmed ? 'is-dimmed' : ''}`;
        const shellClass = `shadow-orbit-track__shell shadow-orbit-track__shell--${trackType} shadow-orbit-track__shell--${node.tone}`;
        const nodeClass = `shadow-orbit-track__node shadow-orbit-track__node--${trackType}`;
        const translate = `translate(${node.x}px, ${node.y}px) translate(-50%, -50%) scale(${selected ? node.scale * 1.08 : node.scale})`;
        const contentTransform = `rotate(${TRACK_TILT}deg)`;

        return (
          <div
            key={node.id}
            className={hitboxClass}
            style={{
              transform: translate,
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
            <div className={shellClass} style={{ transform: contentTransform }}>
              <div className={nodeClass}>
                {trackType === 'stat' ? (
                  <>
                    <span className="shadow-orbit-track__kicker">{node.label}</span>
                    <strong className="shadow-orbit-track__value">{node.value}</strong>
                  </>
                ) : (
                  <span className="shadow-orbit-track__tag">{node.label}</span>
                )}
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}

export function FriendOrbitHero({ data, friend, viewModel }: FriendOrbitHeroProps) {
  const reduceMotion = useReducedMotion();
  const [hoveredId, setHoveredId] = useState<string | null>(null);
  const [lockedId, setLockedId] = useState<string | null>(null);
  const [innerRotation, setInnerRotation] = useState(-18);
  const [outerRotation, setOuterRotation] = useState(12);

  const activeId = lockedId ?? hoveredId;
  const activeNode = [...viewModel.orbitStats, ...viewModel.orbitTraits].find((item) => item.id === activeId) ?? null;
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
    <section className="shadow-orbit-hero">
      <div className="shadow-orbit-hero__mist shadow-orbit-hero__mist--blue" />
      <div className="shadow-orbit-hero__mist shadow-orbit-hero__mist--pink" />
      <div className="shadow-orbit-hero__grain" />
      <div className="shadow-orbit-hero__head">
        <h2 className="shadow-orbit-hero__title">好友恒星环</h2>
      </div>

      <div
        className="shadow-orbit-hero__stage"
        onPointerDown={() => setLockedId(null)}
        onPointerLeave={() => {
          if (!lockedId) setHoveredId(null);
        }}
      >
        <div className="shadow-orbit-hero__support-ring" />
        <div className="shadow-orbit-hero__ring shadow-orbit-hero__ring--inner shadow-orbit-hero__ring--back" />
        <div className="shadow-orbit-hero__ring shadow-orbit-hero__ring--outer shadow-orbit-hero__ring--back" />

        <OrbitTrack
          className="shadow-orbit-track--inner"
          items={viewModel.orbitStats}
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

        <OrbitTrack
          className="shadow-orbit-track--outer"
          items={viewModel.orbitTraits}
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

        <div className="shadow-orbit-hero__core-occlusion">
          <div className="shadow-orbit-hero__core-glow" />
          <div className="shadow-orbit-hero__avatar-shell">
            <div className="shadow-orbit-hero__avatar">
              {friend?.avatar_url ? (
                <img src={friend.avatar_url} alt="" className="h-full w-full object-cover" />
              ) : (
                <div className="shadow-orbit-hero__avatar-fallback">
                  <UserRound size={48} strokeWidth={1.6} />
                </div>
              )}
            </div>
          </div>

          <div className="shadow-orbit-hero__copy">
            <div className="shadow-orbit-hero__name">{viewModel.friendName || 'WowStanLau'}</div>
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
