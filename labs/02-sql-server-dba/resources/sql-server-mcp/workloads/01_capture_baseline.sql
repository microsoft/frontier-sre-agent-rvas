/*
    Scenario: BASELINE_CAPTURE

    Run this script several times to populate Query Store with a representative
    mix of point lookups, range scans, joins, and aggregates.
*/

SET ANSI_NULLS ON;
SET QUOTED_IDENTIFIER ON;
SET ANSI_PADDING ON;
SET ANSI_WARNINGS ON;
SET ARITHABORT ON;
SET CONCAT_NULL_YIELDS_NULL ON;
SET NUMERIC_ROUNDABORT OFF;
SET NOCOUNT ON;

IF OBJECT_ID(N'sales.usp_GetCustomerOrderHistory', N'P') IS NULL
BEGIN
    THROW 50100, 'Run the installation scripts through 04_programmability.sql first.', 1;
END;

DECLARE @Iteration int = 1;
DECLARE @CustomerId int;
DECLARE @OrderDate date;
DECLARE @ProductId int;

WHILE @Iteration <= 30
BEGIN
    SET @CustomerId = 2 + ((@Iteration * 997) % 4998);
    SET @OrderDate = DATEADD(DAY, -(@Iteration % 30), CONVERT(date, '2026-09-01'));
    SET @ProductId = 2 + ((@Iteration * 37) % 498);

    EXEC sales.usp_GetCustomerOrderHistory
        @CustomerId = @CustomerId,
        @FromDate = '2025-09-01';

    EXEC sales.usp_SearchOrdersByCalendarDate
        @OrderDate = @OrderDate;

    EXEC sales.usp_FindCustomerByExternalReference
        @ExternalReference = N'CUST-000000100';

    EXEC sales.usp_GetProductSalesSummary
        @ProductId = @ProductId,
        @FromDate = '2025-09-01',
        @ToDate = '2026-09-02';

    SET @Iteration += 1;
END;
GO
