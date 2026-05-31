import { useEffect, useMemo, useRef, useState } from 'react';
import { Copy } from 'lucide-react';
import './relationImmersive.css';
import type { FriendListItemLite, MusicRelationData, RelationExportPayload } from '../../types';
import { CircadianVinylHeatmap } from './CircadianVinylHeatmap';
import { FriendOrbitHero } from './FriendOrbitHero';
import { SharedSoundWorld } from './SharedSoundWorld';
import { SonicTimelineRiver } from './SonicTimelineRiver';
import { buildSingleFriendProfileViewModel } from './relationViewModel';

type SingleFriendMusicProfileProps = {
  data: MusicRelationData;
  friend?: FriendListItemLite;
  exportPayload: RelationExportPayload | null;
  exportMessage: string;
  exporting: boolean;
  onExport: () => Promise<RelationExportPayload | null>;
};

export function SingleFriendMusicProfile({
  data,
  friend,
  exportPayload,
  exportMessage,
  exporting,
  onExport,
}: SingleFriendMusicProfileProps) {
  const viewModel = buildSingleFriendProfileViewModel(data, friend);
  const [copyMessage, setCopyMessage] = useState('');
  const [activeSection, setActiveSection] = useState('hero');
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const heroRef = useRef<HTMLDivElement | null>(null);
  const riverRef = useRef<HTMLDivElement | null>(null);
  const vinylRef = useRef<HTMLDivElement | null>(null);
  const worldRef = useRef<HTMLDivElement | null>(null);
  const exportRef = useRef<HTMLDivElement | null>(null);

  const sections = useMemo(
    () => [
      { id: 'hero', label: '好友恒星环', ref: heroRef },
      { id: 'river', label: '音乐长河', ref: riverRef },
      { id: 'vinyl', label: '24 小时唱片', ref: vinylRef },
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
        if (!visible) return;
        const id = visible.target.getAttribute('data-section-id');
        if (id) setActiveSection(id);
      },
      {
        root,
        threshold: [0.3, 0.45, 0.6],
        rootMargin: '-12% 0px -12% 0px',
      },
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
    const top = Math.max(0, target.offsetTop - 8);
    const maxScroll = Math.max(0, root.scrollHeight - root.clientHeight);
    root.scrollTo({ top: Math.min(top, maxScroll), behavior: 'smooth' });
  };

  const handleCopyPrompt = async () => {
    try {
      const payload = await onExport();
      const promptText = payload?.prompt_text;
      if (!promptText) {
        setCopyMessage('请先生成 AI Prompt。');
        return;
      }
      await navigator.clipboard.writeText(promptText);
      setCopyMessage('AI Prompt 已复制。');
    } catch {
      setCopyMessage('复制失败，请重试。');
    }
  };

  return (
    <div ref={scrollRef} className="shadow-archive-scroll flex-1 min-h-0 overflow-y-auto pr-2 scrollbar-none">
      <div className="shadow-archive-nav" aria-label="单好友内容导航">
        {sections.map((section) => {
          const active = activeSection === section.id;
          return (
            <button
              key={section.id}
              type="button"
              className={`shadow-archive-nav__item ${active ? 'is-active' : ''}`}
              onClick={() => scrollToSection(section.id)}
              aria-label={section.label}
            >
              <span className="shadow-archive-nav__label">{section.label}</span>
              <span className="shadow-archive-nav__dot" />
            </button>
          );
        })}
      </div>
      <div className="shadow-archive-stack min-h-full">
        <div ref={heroRef} data-section-id="hero" className="shadow-archive-section shadow-archive-section--hero">
          <FriendOrbitHero data={data} friend={friend} viewModel={viewModel} />
        </div>
        <div ref={riverRef} data-section-id="river" className="shadow-archive-section shadow-archive-section--river">
          <SonicTimelineRiver data={data} viewModel={viewModel} />
        </div>
        <div ref={vinylRef} data-section-id="vinyl" className="shadow-archive-section shadow-archive-section--vinyl">
          <CircadianVinylHeatmap data={data} viewModel={viewModel} />
        </div>
        <div ref={worldRef} data-section-id="world" className="shadow-archive-section shadow-archive-section--world">
          <SharedSoundWorld data={data} viewModel={viewModel} />
        </div>
        <section ref={exportRef} data-section-id="export" className="shadow-export-dock shadow-archive-section shadow-archive-section--export">
          <div className="shadow-export-dock__copy">
            <h3 className="shadow-export-dock__title">导出与操作</h3>
            <p>复制 AI Prompt 后直接贴到外部模型里分析。</p>
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
