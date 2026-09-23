/*
    Scenario: BLOCKING, session B

    Start this script while 05_blocking_session_a.sql is waiting. The update
    should wait behind session A and complete after session A rolls back. This
    transaction also rolls back.
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
SET LOCK_TIMEOUT 90000;

BEGIN TRANSACTION;

UPDATE inventory.InventoryBalance
SET QuantityReserved = QuantityReserved
WHERE WarehouseId = 1
  AND ProductId = 1;

ROLLBACK TRANSACTION;

SELECT N'Session B acquired the lock after the blocking session released it, then rolled back.' AS BlockingScenarioResult;
GO
