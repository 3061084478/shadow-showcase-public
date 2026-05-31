export const HOTSPOT_POLYGONS = {
  chat: {
    name: '聊天记录',
    points: '30,105 744,20 780,348 662,343 651,467 76,532',
  },
  relation: {
    name: '音乐关系',
    points: '782,349 1011,367 984,647 637,621 651,465 662,343',
  },
  playlist: {
    name: '影子歌单',
    points: '1006,605 1587,508 1630,832 1076,917',
  },
} as const;

export const FEATURE_DECOR_CONFIG = {
  chat: {
    icon: { x: 87, y: 164, rotate: -7, scale: 1 },
    label: { x: 191, y: 478, rotate: -6, scale: 1 },
  },
  relation: {
    icon: { x: 716, y: 409, rotate: 5, scale: 1 },
    label: { x: 821, y: 606, rotate: 6, scale: 1 },
  },
  playlist: {
    icon: { x: 1079, y: 664, rotate: -10, scale: 1 },
    label: { x: 1177, y: 856, rotate: -9, scale: 1 },
  },
} as const;
