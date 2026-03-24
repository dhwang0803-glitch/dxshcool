-- =============================================================
-- Migration: add rag_confidence to vod table
-- Date: 2026-03-08
-- Branch: RAG
-- Purpose: RAG 파이프라인 결과 신뢰도 점수 저장
--          소스별 가중치 합산 (0.0~1.0)
--
-- 적용 이력: RAG 브랜치 개발 중 직접 DB 적용됨 (마이그레이션 파일 사후 추가)
-- 현재 상태: 이미 DB에 적용 완료 (IF NOT EXISTS로 재실행 안전)
-- =============================================================

BEGIN;

ALTER TABLE vod
    ADD COLUMN IF NOT EXISTS rag_confidence REAL;

COMMENT ON COLUMN vod.rag_confidence IS
    'RAG 결과 신뢰도 (0.0~1.0). 소스별 가중치 합산 점수.';

COMMIT;
