import { useEffect, useMemo, useState } from 'react';
import { motion } from 'motion/react';
import { Activity } from 'lucide-react';
import { PageWrapper } from '../components/PageWrapper';
import { GlobalMusicSocialProfile } from '../components/relation/GlobalMusicSocialProfile';
import { SingleFriendMusicProfile } from '../components/relation/SingleFriendMusicProfile';
import type {
  FriendListItemLite,
  MusicRelationData,
  RelationExportPayload,
} from '../types';
import { syncFriendRecent } from '../services/friends';
import { exportFriendRelation, exportSelfRelation, fetchFriendRelation, fetchSelfRelation } from '../services/relation';

type MusicRelationshipPageProps = {
  friend?: FriendListItemLite;
  friends?: FriendListItemLite[];
  selectedFriendId?: string | null;
  onSelectFriend?: (uid: string) => void;
  onBack: () => void;
};

export function MusicRelationshipPage({ friend, friends = [], selectedFriendId, onSelectFriend, onBack }: MusicRelationshipPageProps) {
  const [reportMode, setReportMode] = useState<'Single' | 'Global'>('Single');
  const [singleData, setSingleData] = useState<MusicRelationData | null>(null);
  const [globalData, setGlobalData] = useState<MusicRelationData | null>(null);
  const [loading, setLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState('');
  const [exportMessage, setExportMessage] = useState('');
  const [exportPayload, setExportPayload] = useState<RelationExportPayload | null>(null);
  const [exporting, setExporting] = useState(false);
  const [refreshingArchive, setRefreshingArchive] = useState(false);

  const data = useMemo(() => (reportMode === 'Single' ? singleData : globalData), [globalData, reportMode, singleData]);
  const currentFriend = reportMode === 'Single' ? friend : undefined;

  const loadSingle = async () => {
    if (!friend) return;
    setLoading(true);
    setErrorMessage('');
    try {
      const payload = await fetchFriendRelation(friend.friend_uid);
      setSingleData(payload);
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : '加载单好友画像失败');
      setSingleData(null);
    } finally {
      setLoading(false);
    }
  };

  const loadGlobal = async () => {
    setLoading(true);
    setErrorMessage('');
    try {
      const payload = await fetchSelfRelation();
      setGlobalData(payload);
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : '加载全局画像失败');
      setGlobalData(null);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    setErrorMessage('');
    setExportMessage('');
    setExportPayload(null);
    if (reportMode === 'Single') {
      if (friend) {
        void loadSingle();
      } else {
        setSingleData(null);
      }
      return;
    }
    void loadGlobal();
  }, [friend, reportMode]);

  const handleExport = async (): Promise<RelationExportPayload | null> => {
    try {
      setExporting(true);
      setExportMessage('导出中...');
      const payload = reportMode === 'Single' && friend ? await exportFriendRelation(friend.friend_uid) : await exportSelfRelation();
      setExportPayload(payload);
      setExportMessage('');
      return payload;
    } catch (error) {
      setExportPayload(null);
      setExportMessage(error instanceof Error ? error.message : '导出失败');
      return null;
    } finally {
      setExporting(false);
    }
  };

  const refreshArchive = async () => {
    if (!friend || reportMode !== 'Single') return;
    try {
      setRefreshingArchive(true);
      await syncFriendRecent(friend.friend_uid, 3, 50);
      await loadSingle();
    } finally {
      setRefreshingArchive(false);
    }
  };

  const headerBottom = (
    <div className="shadow-page-tools">
      <div className="shadow-page-tabs">
        <button onClick={() => setReportMode('Single')} className={`relative pb-2 text-[12px] font-bold uppercase tracking-widest transition-all ${reportMode === 'Single' ? 'text-white' : 'text-white/20 hover:text-white/40'}`}>
          单好友画像
          {reportMode === 'Single' ? <motion.div layoutId="tab-underline" className="absolute bottom-0 left-0 right-0 h-[2px] bg-white shadow-[0_0_10px_white]" /> : null}
        </button>
        <button onClick={() => setReportMode('Global')} className={`relative pb-2 text-[12px] font-bold uppercase tracking-widest transition-all ${reportMode === 'Global' ? 'text-white' : 'text-white/20 hover:text-white/40'}`}>
          我的音乐社交
          {reportMode === 'Global' ? <motion.div layoutId="tab-underline" className="absolute bottom-0 left-0 right-0 h-[2px] bg-white shadow-[0_0_10px_white]" /> : null}
        </button>
      </div>
      <div className="shadow-page-actions" />
    </div>
  );

  return (
    <PageWrapper
      title="音乐关系"
      subtitle=""
      friend={currentFriend}
      friends={friends}
      selectedFriendId={selectedFriendId}
      onSelectFriend={onSelectFriend}
      hideFriendCard={reportMode === 'Global'}
      onBack={onBack}
      onRefreshArchive={currentFriend ? () => void refreshArchive() : null}
      refreshingArchive={refreshingArchive}
      headerBottom={headerBottom}
    >
      <div className="page-shell min-h-0">
        <div className="page-content-wrapper flex min-h-0 flex-1 flex-col">
          {errorMessage ? <div className="mb-5 shrink-0 rounded-2xl border border-red-400/10 bg-red-400/5 px-5 py-3 text-[11px] text-red-200/70">{errorMessage}</div> : null}

          {reportMode === 'Single' ? (
            !friend ? (
              <div className="empty-state-card h-full w-full">
                <Activity size={64} strokeWidth={1} />
                <h3 className="mt-4 text-white/20">尚未选择好友</h3>
                <p className="mt-2 text-[11px] uppercase tracking-widest text-white/10">请先选择好友以生成画像</p>
              </div>
            ) : loading && !data ? (
              <div className="empty-state-card h-full w-full">
                <Activity size={64} strokeWidth={1} />
                <h3 className="mt-4 text-white/20">正在生成画像</h3>
              </div>
            ) : data ? (
              <SingleFriendMusicProfile
                data={data}
                friend={friend}
                exportPayload={exportPayload}
                exportMessage={exportMessage}
                exporting={exporting}
                onExport={handleExport}
              />
            ) : (
              <div className="empty-state-card h-full w-full">
                <Activity size={64} strokeWidth={1} />
                <h3 className="mt-4 text-white/20">暂无可用画像数据</h3>
              </div>
            )
          ) : loading && !data ? (
            <div className="empty-state-card h-full w-full">
              <Activity size={64} strokeWidth={1} />
              <h3 className="mt-4 text-white/20">正在加载全局画像</h3>
            </div>
          ) : data ? (
            <GlobalMusicSocialProfile
              data={data}
              exportPayload={exportPayload}
              exportMessage={exportMessage}
              exporting={exporting}
              onExport={handleExport}
            />
          ) : (
            <div className="empty-state-card h-full w-full">
              <Activity size={64} strokeWidth={1} />
              <h3 className="mt-4 text-white/20">暂无全局画像数据</h3>
            </div>
          )}
        </div>
      </div>
    </PageWrapper>
  );
}
