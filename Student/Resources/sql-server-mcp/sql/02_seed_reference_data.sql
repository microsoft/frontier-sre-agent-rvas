/*
    Purpose:
      Seed stable reference data and the DBA SRE scenario catalog.
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
    THROW 50010, 'Run 01_schema.sql before this script.', 1;
END;

IF EXISTS (SELECT 1 FROM ref.Region)
BEGIN
    THROW 50011, 'Reference data already exists. This script is intended to run once.', 1;
END;

BEGIN TRANSACTION;

INSERT ref.Region (RegionCode, RegionName, CurrencyCode)
VALUES
    ('AU', N'Australia', 'AUD'),
    ('DE', N'Germany', 'EUR'),
    ('FR', N'France', 'EUR'),
    ('GB', N'United Kingdom', 'GBP'),
    ('GR', N'Greece', 'EUR'),
    ('JP', N'Japan', 'JPY'),
    ('NL', N'Netherlands', 'EUR'),
    ('US', N'United States', 'USD');

INSERT ref.OrderStatus (OrderStatusCode, StatusName, IsTerminal, SortOrder)
VALUES
    ('NEW', N'New', 0, 10),
    ('PAID', N'Paid', 0, 20),
    ('PACKED', N'Packed', 0, 30),
    ('SHIPPED', N'Shipped', 0, 40),
    ('COMPLETED', N'Completed', 1, 50),
    ('CANCELLED', N'Cancelled', 1, 60),
    ('RETURNED', N'Returned', 1, 70);

INSERT catalog.ProductCategory
(
    ProductCategoryId,
    ParentProductCategoryId,
    CategoryName
)
VALUES
    (1, NULL, N'Computing'),
    (2, NULL, N'Office'),
    (3, NULL, N'Home'),
    (4, NULL, N'Audio and Video'),
    (5, 1, N'Laptops'),
    (6, 1, N'Components'),
    (7, 2, N'Office Supplies'),
    (8, 3, N'Home Automation'),
    (9, 4, N'Headphones'),
    (10, 4, N'Displays');

INSERT inventory.Warehouse
(
    WarehouseId,
    WarehouseCode,
    WarehouseName,
    RegionCode
)
VALUES
    (1, 'WH-US-EAST', N'US East Distribution Center', 'US'),
    (2, 'WH-EU-CENTRAL', N'EU Central Distribution Center', 'DE'),
    (3, 'WH-UK-SOUTH', N'UK South Distribution Center', 'GB'),
    (4, 'WH-AP-SOUTH', N'Asia Pacific Distribution Center', 'AU');

INSERT lab.Scenario
(
    ScenarioCode,
    ScenarioTitle,
    ScenarioCategory,
    Objective,
    WorkloadScript,
    ExpectedSignal
)
VALUES
(
    'BASELINE_CAPTURE',
    N'Capture a representative workload baseline',
    'BASELINE',
    N'Populate Query Store and dynamic management views with a repeatable mix of point lookups, range queries, joins, and aggregates.',
    'workloads/01_capture_baseline.sql',
    N'Query Store contains executions with varied CPU, duration, logical reads, and execution counts.'
),
(
    'MISSING_PRODUCT_INDEX',
    N'Detect an unindexed product sales path',
    'INDEXING',
    N'Identify the missing access path from SalesOrderLine.ProductId into order history.',
    'workloads/02_missing_index.sql',
    N'A scan of sales.SalesOrderLine, elevated logical reads, and a missing-index recommendation for ProductId.'
),
(
    'PARAMETER_SENSITIVITY',
    N'Diagnose a skew-sensitive customer history query',
    'PLAN_QUALITY',
    N'Compare one high-volume customer with normal customers through a single cached stored procedure.',
    'workloads/03_parameter_sensitivity.sql',
    N'Runtime and cardinality differences between CustomerId 1 and ordinary customer identifiers.'
),
(
    'SARGABILITY',
    N'Find predicates that prevent index seeks',
    'QUERY_TUNING',
    N'Demonstrate a function on OrderDateUtc and an implicit conversion on ExternalReference.',
    'workloads/04_sargability.sql',
    N'Index scans or residual predicates despite selective search values and existing indexes.'
),
(
    'BLOCKING',
    N'Analyze a blocked writer',
    'CONCURRENCY',
    N'Create a reversible update lock conflict against one inventory row.',
    'workloads/05_blocking_session_a.sql and workloads/06_blocking_session_b.sql',
    N'A waiting request with blocking_session_id, lock waits, and matching transaction context.'
),
(
    'DATA_GROWTH',
    N'Assess table and index growth',
    'CAPACITY',
    N'Use configurable scale factors to compare row counts, allocated space, and index footprint.',
    NULL,
    N'Increasing allocation and row-count trends concentrated in order lines and stock movements.'
);

COMMIT TRANSACTION;
GO
