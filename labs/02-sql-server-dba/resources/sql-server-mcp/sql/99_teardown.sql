/*
    Purpose:
      Remove all sample objects created by this repository.

    WARNING:
      This script permanently deletes the sample data. It does not remove the
      sre_dba_observer role or its members because they are environment-specific
      security principals.
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
    THROW 50090, 'The DBA SRE sample database is not installed in this database.', 1;
END;

BEGIN TRANSACTION;

-- Remove the monitoring view created by repository versions before 2026-09-21.
DROP VIEW IF EXISTS lab.vw_TableSize;
DROP VIEW IF EXISTS support.vw_OpenTicketBacklog;
DROP VIEW IF EXISTS inventory.vw_InventoryRisk;
DROP VIEW IF EXISTS sales.vw_OrderSummary;

DROP PROCEDURE IF EXISTS support.usp_SearchTicketText;
DROP PROCEDURE IF EXISTS sales.usp_GetProductSalesSummary;
DROP PROCEDURE IF EXISTS sales.usp_FindCustomerByExternalReference;
DROP PROCEDURE IF EXISTS sales.usp_SearchOrdersByCalendarDate;
DROP PROCEDURE IF EXISTS sales.usp_GetCustomerOrderHistory;
DROP PROCEDURE IF EXISTS lab.usp_GenerateSampleData;

DROP TABLE IF EXISTS support.TicketEvent;
DROP TABLE IF EXISTS support.SupportTicket;
DROP TABLE IF EXISTS inventory.StockMovement;
DROP TABLE IF EXISTS inventory.InventoryBalance;
DROP TABLE IF EXISTS inventory.Warehouse;
DROP TABLE IF EXISTS sales.Payment;
DROP TABLE IF EXISTS sales.SalesOrderLine;
DROP TABLE IF EXISTS sales.SalesOrder;
DROP TABLE IF EXISTS sales.Customer;
DROP TABLE IF EXISTS catalog.Product;
DROP TABLE IF EXISTS catalog.ProductCategory;
DROP TABLE IF EXISTS ref.OrderStatus;
DROP TABLE IF EXISTS ref.Region;
DROP TABLE IF EXISTS lab.Scenario;
DROP TABLE IF EXISTS lab.BuildInfo;

DROP SEQUENCE IF EXISTS support.SeqTicketEventId;
DROP SEQUENCE IF EXISTS support.SeqTicketId;
DROP SEQUENCE IF EXISTS inventory.SeqStockMovementId;
DROP SEQUENCE IF EXISTS sales.SeqPaymentId;
DROP SEQUENCE IF EXISTS sales.SeqOrderLineId;
DROP SEQUENCE IF EXISTS sales.SeqOrderId;
DROP SEQUENCE IF EXISTS sales.SeqCustomerId;
DROP SEQUENCE IF EXISTS catalog.SeqProductId;

DROP SCHEMA support;
DROP SCHEMA inventory;
DROP SCHEMA sales;
DROP SCHEMA catalog;
DROP SCHEMA ref;
DROP SCHEMA lab;

COMMIT TRANSACTION;

SELECT
    N'Sample objects removed. Query Store settings, the sre_dba_observer role, and its members were retained.' AS TeardownResult;
GO
