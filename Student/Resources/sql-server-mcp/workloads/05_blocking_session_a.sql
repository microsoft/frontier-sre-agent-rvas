/*
    Scenario: BLOCKING, session A

    Run this script in one query window. During the WAITFOR period, run
    06_blocking_session_b.sql in a second window. The transaction always rolls
    back, so the sample data remains unchanged.
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

BEGIN TRANSACTION;

UPDATE inventory.InventoryBalance
SET QuantityOnHand = QuantityOnHand
WHERE WarehouseId = 1
  AND ProductId = 1;

SELECT
    @@SPID AS LockHolderSessionId,
    N'Run workloads/06_blocking_session_b.sql in another session now.' AS NextAction;

WAITFOR DELAY '00:01:00';

ROLLBACK TRANSACTION;

SELECT N'Session A rolled back and released its lock.' AS BlockingScenarioResult;
GO
