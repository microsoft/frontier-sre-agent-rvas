/*
    Scenario: PARAMETER_SENSITIVITY

    Customer 1 owns roughly 20 percent of all orders. Most other customers own
    only a small number. Execute this script in the listed order, then reverse
    the order in a later run to compare cached-plan behavior.
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

EXEC sales.usp_GetCustomerOrderHistory
    @CustomerId = 200,
    @FromDate = '2024-09-01';

EXEC sales.usp_GetCustomerOrderHistory
    @CustomerId = 1,
    @FromDate = '2024-09-01';

SET STATISTICS TIME OFF;
SET STATISTICS IO OFF;
GO
