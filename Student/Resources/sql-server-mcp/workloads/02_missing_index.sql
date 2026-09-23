/*
    Scenario: MISSING_PRODUCT_INDEX

    The SalesOrderLine table intentionally has no index beginning with ProductId.
    Product 1 is deliberately overrepresented, while other products are selective.
*/

SET ANSI_NULLS ON;
SET QUOTED_IDENTIFIER ON;
SET ANSI_PADDING ON;
SET ANSI_WARNINGS ON;
SET ARITHABORT ON;
SET CONCAT_NULL_YIELDS_NULL ON;
SET NUMERIC_ROUNDABORT OFF;
SET NOCOUNT ON;
SET STATISTICS IO ON;
SET STATISTICS TIME ON;

DECLARE @Iteration int = 1;

WHILE @Iteration <= 10
BEGIN
    EXEC sales.usp_GetProductSalesSummary
        @ProductId = 317,
        @FromDate = '2025-09-01',
        @ToDate = '2026-09-02';

    SET @Iteration += 1;
END;

SET STATISTICS TIME OFF;
SET STATISTICS IO OFF;
GO
