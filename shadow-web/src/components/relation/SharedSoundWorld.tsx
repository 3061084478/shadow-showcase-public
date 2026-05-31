import { useMemo, useState } from 'react';
import type { GenreBalanceItem, MusicRelationData, TopArtistItem } from '../../types';
import type { SingleFriendProfileViewModel } from './relationViewModel';

type SharedSoundWorldProps = {
  data: MusicRelationData;
  viewModel: SingleFriendProfileViewModel;
};

function buildGenreItems(items: GenreBalanceItem[]) {
  return items.slice(0, 5).map((item) => ({
    name: item.genre,
    count: item.me + item.friend,
    me: item.me,
    friend: item.friend,
  }));
}

function buildArtistItems(items: TopArtistItem[]) {
  return items.slice(0, 5).map((item) => ({
    name: item.name,
    count: item.count,
    me: item.me ?? 0,
    friend: item.friend ?? 0,
  }));
}

export function SharedSoundWorld({ data }: SharedSoundWorldProps) {
  const [activeKey, setActiveKey] = useState<string | null>(null);
  const sharedGenreCount = data.overlapCount;
  const sharedArtistCount = Math.max(data.commonWorld.sharedArtistTotal, data.commonWorld.sharedArtists.length);

  const genreItems = useMemo(() => buildGenreItems(data.commonWorld.sharedGenres), [data.commonWorld.sharedGenres]);
  const artistItems = useMemo(() => buildArtistItems(data.commonWorld.sharedArtists), [data.commonWorld.sharedArtists]);

  return (
    <section className="shadow-world shadow-common-world">
      <div className="shadow-world__bridge" />
      <div className="shadow-world__head shadow-common-world__head">
        <h3 className="shadow-world__title">共同音乐世界</h3>
      </div>

        <div className="shadow-common-world__stage">
        <div className="shadow-common-world__columns">
          <section className="shadow-common-world__panel">
            <div className="shadow-common-world__list-block">
              <div className="shadow-common-world__section-head">
                <div className="shadow-common-world__section-copy">
                  <span className="shadow-common-world__section-kicker">共同流派数</span>
                  <strong>{sharedGenreCount}</strong>
                </div>
                <div className="shadow-common-world__label">共同流派 Top 5</div>
              </div>
              {genreItems.length > 0 ? (
                <div className="shadow-common-world__list">
                  {genreItems.map((item) => (
                    <button
                      type="button"
                      key={`genre-${item.name}`}
                      className={`shadow-common-world__list-row shadow-common-world__list-row--interactive ${activeKey === `genre-${item.name}` ? 'is-active' : ''}`}
                      onPointerEnter={() => setActiveKey(`genre-${item.name}`)}
                      onPointerLeave={() => setActiveKey(null)}
                      onFocus={() => setActiveKey(`genre-${item.name}`)}
                      onBlur={() => setActiveKey(null)}
                    >
                      <span className="shadow-common-world__chip shadow-common-world__chip--genre">{item.name}</span>
                      <span className="shadow-common-world__split">
                        <span className="shadow-common-world__split-me">我 {item.me} 次</span>
                        <span className="shadow-common-world__split-separator">·</span>
                        <span className="shadow-common-world__split-friend">好友 {item.friend} 次</span>
                      </span>
                      <span className="shadow-common-world__count">{item.count} 次</span>
                    </button>
                  ))}
                </div>
              ) : (
                <span className="shadow-common-world__empty">还没有形成共同流派</span>
              )}
            </div>
          </section>

          <section className="shadow-common-world__panel">
            <div className="shadow-common-world__list-block">
              <div className="shadow-common-world__section-head">
                <div className="shadow-common-world__section-copy">
                  <span className="shadow-common-world__section-kicker">共同歌手数</span>
                  <strong>{sharedArtistCount}</strong>
                </div>
                <div className="shadow-common-world__label">共同歌手 Top 5</div>
              </div>
              {artistItems.length > 0 ? (
                <div className="shadow-common-world__list">
                  {artistItems.map((item) => (
                    <button
                      type="button"
                      key={`artist-${item.name}`}
                      className={`shadow-common-world__list-row shadow-common-world__list-row--interactive ${activeKey === `artist-${item.name}` ? 'is-active' : ''}`}
                      onPointerEnter={() => setActiveKey(`artist-${item.name}`)}
                      onPointerLeave={() => setActiveKey(null)}
                      onFocus={() => setActiveKey(`artist-${item.name}`)}
                      onBlur={() => setActiveKey(null)}
                    >
                      <span className="shadow-common-world__chip shadow-common-world__chip--artist">{item.name}</span>
                      <span className="shadow-common-world__split">
                        <span className="shadow-common-world__split-me">我 {item.me} 次</span>
                        <span className="shadow-common-world__split-separator">·</span>
                        <span className="shadow-common-world__split-friend">好友 {item.friend} 次</span>
                      </span>
                      <span className="shadow-common-world__count">{item.count} 次</span>
                    </button>
                  ))}
                </div>
              ) : (
                <span className="shadow-common-world__empty">还没有形成共同歌手</span>
              )}
            </div>
          </section>
        </div>

      </div>
    </section>
  );
}
