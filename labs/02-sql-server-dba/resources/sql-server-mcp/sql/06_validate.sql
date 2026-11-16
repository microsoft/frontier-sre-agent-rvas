/*
    Purpose:
      Verify installation completeness, expected scale, trusted relationships,
      Query Store state, and observer-role permissions.
*/

SET ANSI_NULLS ON;
SET QUOTED_IDENTIFIER ON;
SET ANSI_PADDING ON;
SET ANSI_WARNINGS ON;
SET ARITHABORT ON;
SET CONCAT_NULL_YIELDS_NULL ON;
SET NUMERIC_ROUNDABORT OFF;
SET NOCOUNT ON;
SET XACT_ABORT ON;

IF OBJECT_ID(N'lab.BuildInfo', N'U') IS NULL
BEGIN
    THROW 50050, 'The DBA SRE sample database is not installed.', 1;
END;

DECLARE @ScaleFactor int;
DECLARE @ExpectedProductCount bigint;
DECLARE @ExpectedCustomerCount bigint;
DECLARE @ExpectedOrderCount bigint;
DECLARE @ExpectedOrderLineCount bigint;
DECLARE @ExpectedStockMovementCount bigint;
DECLARE @ExpectedTicketCount bigint;
DECLARE @ExpectedTicketEventCount bigint;

SELECT @ScaleFactor = ScaleFactor
FROM lab.BuildInfo
WHERE BuildInfoId = 1;

IF @ScaleFactor IS NULL
BEGIN
    THROW 50051, 'Generated data is missing. Run 03_generate_sample_data.sql.', 1;
END;

SET @ExpectedProductCount = 500 * @ScaleFactor;
SET @ExpectedCustomerCount = 5000 * @ScaleFactor;
SET @ExpectedOrderCount = 50000 * @ScaleFactor;
SET @ExpectedOrderLineCount = 150000 * @ScaleFactor;
SET @ExpectedStockMovementCount = 100000 * @ScaleFactor;
SET @ExpectedTicketCount = 5000 * @ScaleFactor;
SET @ExpectedTicketEventCount = 15000 * @ScaleFactor;

CREATE TABLE #RowCountValidation
(
    ObjectName nvarchar(261) NOT NULL,
    ExpectedRows bigint NOT NULL,
    ActualRows bigint NOT NULL
);

INSERT #RowCountValidation (ObjectName, ExpectedRows, ActualRows)
SELECT N'catalog.Product', @ExpectedProductCount, COUNT_BIG(*) FROM catalog.Product
UNION ALL
SELECT N'sales.Customer', @ExpectedCustomerCount, COUNT_BIG(*) FROM sales.Customer
UNION ALL
SELECT N'sales.SalesOrder', @ExpectedOrderCount, COUNT_BIG(*) FROM sales.SalesOrder
UNION ALL
SELECT N'sales.SalesOrderLine', @ExpectedOrderLineCount, COUNT_BIG(*) FROM sales.SalesOrderLine
UNION ALL
SELECT N'inventory.StockMovement', @ExpectedStockMovementCount, COUNT_BIG(*) FROM inventory.StockMovement
UNION ALL
SELECT N'support.SupportTicket', @ExpectedTicketCount, COUNT_BIG(*) FROM support.SupportTicket
UNION ALL
SELECT N'support.TicketEvent', @ExpectedTicketEventCount, COUNT_BIG(*) FROM support.TicketEvent;

SELECT
    ObjectName,
    ExpectedRows,
    ActualRows,
    CASE WHEN ExpectedRows = ActualRows THEN 'PASS' ELSE 'FAIL' END AS ValidationStatus
FROM #RowCountValidation
ORDER BY ObjectName;

IF EXISTS
(
    SELECT 1
    FROM #RowCountValidation
    WHERE ExpectedRows <> ActualRows
)
BEGIN
    THROW 50052, 'One or more generated tables have an unexpected row count.', 1;
END;

IF EXISTS
(
    SELECT 1
    FROM sys.foreign_keys
    WHERE is_disabled = 1
       OR is_not_trusted = 1
)
BEGIN
    SELECT
        OBJECT_SCHEMA_NAME(parent_object_id) AS SchemaName,
        OBJECT_NAME(parent_object_id) AS TableName,
        name AS ForeignKeyName,
        is_disabled AS IsDisabled,
        is_not_trusted AS IsNotTrusted
    FROM sys.foreign_keys
    WHERE is_disabled = 1
       OR is_not_trusted = 1;

    THROW 50053, 'One or more foreign keys are disabled or not trusted.', 1;
END;

IF NOT EXISTS
(
    SELECT 1
    FROM sys.database_query_store_options
    WHERE actual_state_desc = N'READ_WRITE'
)
BEGIN
    THROW 50054, 'Query Store is not in READ_WRITE state.', 1;
END;

IF DATABASE_PRINCIPAL_ID(N'sre_dba_observer') IS NULL
BEGIN
    THROW 50055, 'The sre_dba_observer role is missing. Run 05_observer_role.sql.', 1;
END;

IF NOT EXISTS
(
    SELECT 1
    FROM sys.database_permissions permissionState
    WHERE permissionState.grantee_principal_id =
        DATABASE_PRINCIPAL_ID(N'sre_dba_observer')
      AND permissionState.class = 0
      AND permissionState.permission_name = N'SHOWPLAN'
      AND permissionState.state IN ('G', 'W')
)
BEGIN
    THROW 50056, 'The sre_dba_observer role lacks SHOWPLAN. Rerun 05_observer_role.sql.', 1;
END;

SELECT
    b.SchemaVersion,
    b.InstalledAtUtc,
    b.DataGeneratedAtUtc,
    b.SeedAsOfDate,
    b.ScaleFactor,
    q.actual_state_desc AS QueryStoreState,
    q.current_storage_size_mb AS QueryStoreSizeMb,
    q.max_storage_size_mb AS QueryStoreMaxSizeMb
FROM lab.BuildInfo b
CROSS JOIN sys.database_query_store_options q
WHERE b.BuildInfoId = 1;

SELECT
    s.name AS SchemaName,
    t.name AS TableName,
    SUM(p.row_count) AS [RowCount],
    CONVERT(decimal(19, 2), SUM(p.reserved_page_count) * 8.0 / 1024.0) AS ReservedSizeMb,
    CONVERT(decimal(19, 2), SUM(p.used_page_count) * 8.0 / 1024.0) AS UsedSizeMb
FROM sys.dm_db_partition_stats p
INNER JOIN sys.tables t
    ON t.object_id = p.object_id
INNER JOIN sys.schemas s
    ON s.schema_id = t.schema_id
WHERE p.index_id IN (0, 1)
  AND s.name IN ('catalog', 'sales', 'inventory', 'support', 'ref', 'lab')
GROUP BY
    s.name,
    t.name
ORDER BY
    ReservedSizeMb DESC,
    SchemaName,
    TableName;

SELECT
    ScenarioCode,
    ScenarioTitle,
    ScenarioCategory,
    WorkloadScript,
    IsEnabled
FROM lab.Scenario
ORDER BY ScenarioCategory, ScenarioCode;

SELECT N'PASS' AS InstallationValidation;
GO
