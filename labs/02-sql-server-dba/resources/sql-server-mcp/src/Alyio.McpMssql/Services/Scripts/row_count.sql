-- get_row_count: approximate row count from partition metadata.
-- Reads sys.partitions rather than sys.dm_db_partition_stats: the catalog view
-- needs only metadata visibility, while the DMV needs VIEW DATABASE
-- PERFORMANCE STATE, which a db_datareader login does not have.
-- Joins sys.tables, so views yield no row and the caller reports null.
SELECT SUM(p.rows) AS row_count
FROM sys.partitions p
INNER JOIN sys.tables t
    ON t.object_id = p.object_id
INNER JOIN sys.schemas s
    ON s.schema_id = t.schema_id
WHERE t.name = @table
    AND (@schema IS NULL OR s.name = @schema)
    AND p.index_id IN (0, 1);
