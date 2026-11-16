/*
    Scenario: SARGABILITY

    The first procedure applies a conversion to an indexed datetime column.
    The second compares an nvarchar parameter with an indexed varchar column.
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

EXEC sales.usp_SearchOrdersByCalendarDate
    @OrderDate = '2026-08-15';

EXEC sales.usp_FindCustomerByExternalReference
    @ExternalReference = N'CUST-000000100';

SET STATISTICS TIME OFF;
SET STATISTICS IO OFF;
GO
