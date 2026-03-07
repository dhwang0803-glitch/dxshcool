-- Phase 3 Retest: work_mem=256MB
SET work_mem = '256MB';
SET statement_timeout = '120s';

\echo '--- P01 retest (work_mem=256MB) ---'
EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT)
SELECT wh.watch_history_id, wh.vod_id_fk, v.asset_nm, v.genre,
       wh.strt_dt, wh.use_tms, wh.completion_rate, wh.satisfaction
FROM watch_history wh
JOIN vod v ON wh.vod_id_fk = v.full_asset_id
WHERE wh.user_id_fk = 'c895f6cd9f2027aedf31c3236aa9e9b05613b87b0fb5fd5f856d4003c9c9f072'
ORDER BY wh.strt_dt DESC;

\echo '--- P04 retest (work_mem=256MB) ---'
EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT)
SELECT v.full_asset_id, v.asset_nm, v.genre, v.ct_cl,
       AVG(wh.satisfaction) AS avg_satisfaction,
       COUNT(wh.watch_history_id) AS view_count
FROM vod v
JOIN watch_history wh ON v.full_asset_id = wh.vod_id_fk
WHERE wh.satisfaction > 0
GROUP BY v.full_asset_id, v.asset_nm, v.genre, v.ct_cl
HAVING COUNT(wh.watch_history_id) >= 10
ORDER BY avg_satisfaction DESC
LIMIT 100;

\echo '--- P02 retest: median-view VOD ---'
EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT)
SELECT vod_id_fk,
       COUNT(*) AS total_views,
       COUNT(DISTINCT user_id_fk) AS unique_viewers,
       AVG(completion_rate) AS avg_completion,
       AVG(satisfaction) AS avg_satisfaction,
       MAX(strt_dt) AS last_viewed
FROM watch_history
WHERE vod_id_fk = 'cjc|M4996864LFOL10619201'
GROUP BY vod_id_fk;

-- index usage stats
SELECT indexrelname AS indexname, idx_scan AS scans, idx_tup_read AS tuples_read
FROM pg_stat_user_indexes
WHERE tablename IN ('user', 'vod', 'watch_history') AND idx_scan > 0
ORDER BY idx_scan DESC;
