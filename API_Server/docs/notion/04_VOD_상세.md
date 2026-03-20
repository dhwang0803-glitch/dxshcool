# GET /vod/{asset_id} — VOD 상세

## 기능 개요

개별 VOD의 상세 메타데이터를 반환한다. FOD 무료 콘텐츠 여부(`is_free`)와 연도(`release_year`)를 포함.

## 기본 기능

**요청**:
```
GET /vod/{asset_id}
```
- `asset_id`: `full_asset_id` (예: `cjc|M1234567LSGH00000001`)

**처리 로직**:
1. `full_asset_id` 기준 PK 조회 (Index Scan, < 10ms)
2. `release_date` -> `release_year` (연도 int만 반환)
3. `asset_prod == 'FOD'` -> `is_free: true` (무료 콘텐츠)

**응답**:
```json
{
  "asset_id": "cjc|M1234567LSGH00000001",
  "title": "기생충",
  "genre": "드라마",
  "category": "영화",
  "director": "봉준호",
  "cast_lead": "송강호, 이선균",
  "cast_guest": null,
  "summary": "반지하에 사는 기택 가족은...",
  "rating": "15",
  "release_year": 2019,
  "poster_url": "/posters/parasite.jpg",
  "is_free": false
}
```

## 예외사항

| 에러 코드 | HTTP | 조건 | 메시지 |
|-----------|------|------|--------|
| `VOD_NOT_FOUND` | 404 | asset_id가 vod 테이블에 없음 | 해당 콘텐츠를 찾을 수 없습니다 |

## 제약사항

- 인증 불필요 (공개 엔드포인트)
- `full_asset_id`는 내부 ID — Frontend에서는 `series_nm` + `asset_nm`으로 접근
- `release_date` -> `release_year` 변환: `date.year` 추출 (연도만 반환)
- `is_free` 판단 기준: `asset_prod = 'FOD'` (Free On Demand)

## 업스트림 의존성

| 테이블 | 컬럼 | 타입 | 용도 |
|--------|------|------|------|
| `public.vod` | `full_asset_id` | VARCHAR(64) | PK 조회 |
| `public.vod` | `asset_nm`, `genre`, `ct_cl`, `director`, `cast_lead`, `cast_guest`, `smry`, `rating`, `release_date`, `poster_url`, `asset_prod` | 각종 | 상세 응답 필드 |

## 다운스트림 의존성

없음 (읽기 전용)
