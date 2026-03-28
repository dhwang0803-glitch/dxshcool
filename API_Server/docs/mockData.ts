export type VOD = {
  series_id: string
  asset_nm: string
  poster_url: string
  genre: string
  ct_cl: string
  rating: string
  release_year: number
  disp_rtm?: number
  director?: string
  cast_lead?: string
  smry?: string
  score?: number
  youtube_id?: string
}

// 공개 트레일러 YouTube ID (실제 예고편)
const YOUTUBE_IDS = [
  'sGbxmsDFVnE', // 기생충
  'rrLVB6sOqKo', // 범죄도시4
  'KXGVe4MHUNU', // 눈물의 여왕
  'PJtKTHHHOts', // 귀멸의 칼날
  'KVu3gS7iJu4', // 진격의 거인
  '5YQoqL_9-FQ', // 도깨비
  'D4CNuHOpGHY', // 오징어 게임
  'ioNng23DkIM', // 파묘
  'YMm5PNqQNrQ', // 선재 업고 튀어
  'aBP5yNpJpVo', // 이상한 변호사 우영우
]

export type Episode = {
  episode_id: string
  asset_nm: string
  poster_url: string
}

export type WatchingItem = {
  series_id: string
  asset_nm: string
  poster_url: string
  strt_dt: string
  completion_rate: number
}

export type Pattern = {
  pattern_rank: number
  pattern_reason: string
  vod_list: VOD[]
}

const POSTER_COLORS = [
  'from-red-800 to-red-950',
  'from-blue-800 to-blue-950',
  'from-green-800 to-green-950',
  'from-purple-800 to-purple-950',
  'from-yellow-700 to-yellow-900',
  'from-pink-800 to-pink-950',
  'from-indigo-800 to-indigo-950',
  'from-teal-800 to-teal-950',
  'from-orange-800 to-orange-950',
  'from-cyan-800 to-cyan-950',
]

const makeVOD = (id: string, name: string, genre: string, ct_cl: string, colorIdx: number, extra?: Partial<VOD>): VOD => ({
  youtube_id: YOUTUBE_IDS[colorIdx % YOUTUBE_IDS.length],
  series_id: id,
  asset_nm: name,
  poster_url: POSTER_COLORS[colorIdx % POSTER_COLORS.length],
  genre,
  ct_cl,
  rating: ['전체관람가', '12세 이상', '15세 이상', '청소년 관람불가'][colorIdx % 4],
  release_year: 2020 + (colorIdx % 5),
  disp_rtm: 90 + colorIdx * 7,
  director: ['봉준호', '박찬욱', '류승완', '김지운', '이준익'][colorIdx % 5],
  cast_lead: ['송강호', '최민식', '하정우', '이병헌', '전지현'][colorIdx % 5],
  smry: `${name}의 줄거리입니다. 흥미진진한 이야기가 펼쳐집니다.`,
  score: Math.round((0.95 - colorIdx * 0.03) * 100) / 100,
  ...extra,
})

export const heroBannerVODs: VOD[] = [
  makeVOD('h1', '파묘', '공포/스릴러', '영화', 0),
  makeVOD('h2', '범죄도시 4', '액션', '영화', 1),
  makeVOD('h3', '눈물의 여왕', '로맨스', 'TV드라마', 2),
  makeVOD('h4', '선재 업고 튀어', '로맨스', 'TV드라마', 3),
  makeVOD('h5', '도깨비', '판타지', 'TV드라마', 4),
]

export const popularMovies: VOD[] = Array.from({ length: 20 }, (_, i) =>
  makeVOD(`m${i + 1}`, ['파묘', '범죄도시 4', '외계+인', '밀수', '비공식작전', '서울의 봄', '콘크리트 유토피아', '귀공자', '잠', '탈주', '베테랑 2', '하이재킹', '보통의 가족', '청설', '공조 2', '모가디슈', '모범택시', '발신제한', '킹메이커', '올빼미'][i], '액션/드라마', '영화', i)
)

export const popularDramas: VOD[] = Array.from({ length: 20 }, (_, i) =>
  makeVOD(`d${i + 1}`, ['눈물의 여왕', '선재 업고 튀어', '이상한 변호사 우영우', '킹더랜드', '무인도의 디바', '마이데몬', '닥터슬럼프', '졸업', '엄마친구아들', '정년이', '도깨비', '미스터 션샤인', '사랑의 불시착', '갯마을 차차차', '스물다섯 스물하나', '지금 우리 학교는', '오징어 게임', '빈센조', '펜트하우스', '모범택시'][i], '로맨스/드라마', 'TV드라마', i)
)

export const popularVariety: VOD[] = Array.from({ length: 20 }, (_, i) =>
  makeVOD(`v${i + 1}`, ['1박2일', '런닝맨', '무한도전', '나 혼자 산다', '놀면 뭐하니', '유퀴즈', '아는 형님', '신서유기', '지구오락실', '강철부대', '스트릿 우먼 파이터', '쇼미더머니', '미스트롯', '미스터트롯', '복면가왕', '불후의명곡', '음악중심', '인기가요', '쇼챔피언', '더시즌즈'][i], '예능', 'TV 연예/오락', i)
)

export const popularAnime: VOD[] = Array.from({ length: 20 }, (_, i) =>
  makeVOD(`a${i + 1}`, ['귀멸의 칼날', '진격의 거인', '주술회전', '나의 히어로 아카데미아', '원피스', '나루토', '드래곤볼', '헌터X헌터', '강철의 연금술사', '원펀맨', '도쿄 구울', '블리치', '소드 아트 온라인', '덴마', '노 게임 노 라이프', '페어리 테일', '마기', '테일즈 오브', '시원찮은 그녀', '오버로드'][i], '판타지/액션', 'TV애니메이션', i)
)

export const personalizedVODs: VOD[] = Array.from({ length: 10 }, (_, i) =>
  makeVOD(`p${i + 1}`, ['기생충', '올드보이', '아저씨', '신세계', '좋은 놈 나쁜 놈 이상한 놈', '타짜', '극한직업', '써니', '수상한 그녀', '건축학개론'][i], '드라마/스릴러', '영화', i + 2)
)

export const watchingItems: WatchingItem[] = [
  { series_id: 'd1', asset_nm: '눈물의 여왕', poster_url: POSTER_COLORS[0], strt_dt: '2026-03-18', completion_rate: 65 },
  { series_id: 'm1', asset_nm: '파묘', poster_url: POSTER_COLORS[1], strt_dt: '2026-03-17', completion_rate: 30 },
  { series_id: 'd2', asset_nm: '선재 업고 튀어', poster_url: POSTER_COLORS[2], strt_dt: '2026-03-16', completion_rate: 90 },
  { series_id: 'a1', asset_nm: '귀멸의 칼날', poster_url: POSTER_COLORS[3], strt_dt: '2026-03-15', completion_rate: 15 },
  { series_id: 'v1', asset_nm: '1박2일', poster_url: POSTER_COLORS[4], strt_dt: '2026-03-14', completion_rate: 50 },
  { series_id: 'm2', asset_nm: '범죄도시 4', poster_url: POSTER_COLORS[5], strt_dt: '2026-03-13', completion_rate: 80 },
  { series_id: 'd3', asset_nm: '이상한 변호사 우영우', poster_url: POSTER_COLORS[6], strt_dt: '2026-03-12', completion_rate: 45 },
  { series_id: 'a2', asset_nm: '진격의 거인', poster_url: POSTER_COLORS[7], strt_dt: '2026-03-11', completion_rate: 70 },
  { series_id: 'v2', asset_nm: '런닝맨', poster_url: POSTER_COLORS[8], strt_dt: '2026-03-10', completion_rate: 20 },
  { series_id: 'm3', asset_nm: '외계+인', poster_url: POSTER_COLORS[9], strt_dt: '2026-03-09', completion_rate: 55 },
]

export const smartRecommendPatterns: Pattern[] = [
  {
    pattern_rank: 1,
    pattern_reason: '봉준호 감독 작품을 즐겨 보셨어요',
    vod_list: Array.from({ length: 10 }, (_, i) => makeVOD(`sr1_${i}`, ['기생충', '괴물', '설국열차', '마더', '살인의 추억', '플란다스의 개', '인플루언자', '지리멸렬', '옥자', '미키 17'][i], '드라마', '영화', i)),
  },
  {
    pattern_rank: 2,
    pattern_reason: '액션 장르를 자주 시청하셨네요',
    vod_list: Array.from({ length: 10 }, (_, i) => makeVOD(`sr2_${i}`, ['범죄도시 4', '아저씨', '베테랑', '공조', '모가디슈', '밀수', '외계+인', '비공식작전', '탈주', '하이재킹'][i], '액션', '영화', i + 1)),
  },
  {
    pattern_rank: 3,
    pattern_reason: '로맨스 드라마 시청 비율이 높아요',
    vod_list: Array.from({ length: 10 }, (_, i) => makeVOD(`sr3_${i}`, ['눈물의 여왕', '선재 업고 튀어', '도깨비', '사랑의 불시착', '갯마을 차차차', '킹더랜드', '마이데몬', '닥터슬럼프', '졸업', '엄마친구아들'][i], '로맨스', 'TV드라마', i + 2)),
  },
  {
    pattern_rank: 4,
    pattern_reason: '최민식 배우 출연작을 자주 보셨어요',
    vod_list: Array.from({ length: 10 }, (_, i) => makeVOD(`sr4_${i}`, ['올드보이', '파이란', '악마를 보았다', '신세계', '루시', '해안선', '취화선', '밀양', '이끼', '대호'][i], '드라마/스릴러', '영화', i + 3)),
  },
  {
    pattern_rank: 5,
    pattern_reason: '판타지 애니메이션을 즐겨 보시네요',
    vod_list: Array.from({ length: 10 }, (_, i) => makeVOD(`sr5_${i}`, ['귀멸의 칼날', '진격의 거인', '주술회전', '원피스', '나루토', '헌터X헌터', '강철의 연금술사', '원펀맨', '도쿄 구울', '블리치'][i], '판타지', 'TV애니메이션', i + 4)),
  },
]

export const getVODById = (id: string): VOD => {
  const all = [...heroBannerVODs, ...popularMovies, ...popularDramas, ...popularVariety, ...popularAnime, ...personalizedVODs,
    ...smartRecommendPatterns.flatMap(p => p.vod_list)]
  return all.find(v => v.series_id === id) ?? makeVOD(id, '알 수 없는 콘텐츠', '드라마', '영화', 0)
}

export const getEpisodes = (series_id: string): Episode[] =>
  Array.from({ length: 8 }, (_, i) => ({
    episode_id: `${series_id}_ep${i + 1}`,
    asset_nm: `${getVODById(series_id).asset_nm} ${i + 1}화`,
    poster_url: POSTER_COLORS[i % POSTER_COLORS.length],
  }))

export const getSimilarVODs = (series_id: string): VOD[] =>
  Array.from({ length: 10 }, (_, i) => makeVOD(`sim_${series_id}_${i}`,
    popularMovies[i]?.asset_nm ?? `유사 콘텐츠 ${i + 1}`, '드라마', '영화', i + 1))

// series_id → 찜한 날짜 (최신순 정렬용)
export const wishlistIds = new Map<string, string>([['m2', '2026-03-14'], ['d1', '2026-03-15']])
// 시청 내역에 있는 콘텐츠는 이미 구매한 것으로 간주
export const purchasedIds = new Set<string>(watchingItems.map(w => w.series_id))

// 테스터 계정 포인트
export const userAccount = { points: 100000 }

// 에피소드별 시청 진행 기록 (episode_id → 마지막 시청 정보)
export type EpisodeProgress = {
  completion_rate: number  // 0~100
  watched_at: string       // ISO 문자열 (최신순 정렬 기준)
}
export const episodeProgress = new Map<string, EpisodeProgress>([
  ['d1_ep3',  { completion_rate: 65, watched_at: '2026-03-18T20:30:00' }],
  ['m1_ep1',  { completion_rate: 30, watched_at: '2026-03-17T15:00:00' }],
  ['d2_ep7',  { completion_rate: 90, watched_at: '2026-03-16T22:00:00' }],
  ['a1_ep1',  { completion_rate: 15, watched_at: '2026-03-15T19:00:00' }],
  ['v1_ep3',  { completion_rate: 50, watched_at: '2026-03-14T21:00:00' }],
  ['m2_ep5',  { completion_rate: 80, watched_at: '2026-03-13T18:00:00' }],
  ['d3_ep4',  { completion_rate: 45, watched_at: '2026-03-12T20:00:00' }],
  ['a2_ep5',  { completion_rate: 70, watched_at: '2026-03-11T21:00:00' }],
  ['v2_ep2',  { completion_rate: 20, watched_at: '2026-03-10T17:00:00' }],
  ['m3_ep4',  { completion_rate: 55, watched_at: '2026-03-09T19:00:00' }],
])

// 해당 시리즈에서 가장 최근에 시청한 에피소드 반환 (없으면 null)
export const getLastWatchedEpisode = (series_id: string): { episode_id: string; completion_rate: number } | null => {
  let latest: { episode_id: string; completion_rate: number; watched_at: string } | null = null
  for (const [episode_id, progress] of episodeProgress.entries()) {
    if (episode_id.startsWith(`${series_id}_ep`)) {
      if (!latest || progress.watched_at > latest.watched_at) {
        latest = { episode_id, ...progress }
      }
    }
  }
  return latest ? { episode_id: latest.episode_id, completion_rate: latest.completion_rate } : null
}

export type PointHistory = {
  type: 'use' | 'earn'
  amount: number
  description: string
  created_at: string
}
export const pointHistory: PointHistory[] = []
