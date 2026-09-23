/*
    Purpose:
      Create views and stored procedures used by the sample workload.

    Several procedures intentionally contain tuning opportunities. They are
    teaching surfaces for the future DBA SRE agent, not production examples.
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

IF NOT EXISTS (SELECT 1 FROM lab.BuildInfo WHERE DataGeneratedAtUtc IS NOT NULL)
BEGIN
    THROW 50030, 'Run 03_generate_sample_data.sql before this script.', 1;
END;
GO

CREATE OR ALTER VIEW sales.vw_OrderSummary
AS
    SELECT
        o.SalesOrderId,
        o.OrderNumber,
        o.OrderDateUtc,
        o.OrderStatusCode,
        o.SalesChannel,
        o.CustomerId,
        c.ExternalReference AS CustomerReference,
        c.EmailAddress,
        c.RegionCode AS CustomerRegionCode,
        o.ShipToRegionCode,
        COUNT_BIG(l.SalesOrderLineId) AS LineCount,
        SUM(CONVERT(bigint, l.Quantity)) AS UnitCount,
        o.SubtotalAmount,
        o.TaxAmount,
        o.ShippingAmount,
        o.TotalAmount
    FROM sales.SalesOrder o
    INNER JOIN sales.Customer c
        ON c.CustomerId = o.CustomerId
    INNER JOIN sales.SalesOrderLine l
        ON l.SalesOrderId = o.SalesOrderId
    GROUP BY
        o.SalesOrderId,
        o.OrderNumber,
        o.OrderDateUtc,
        o.OrderStatusCode,
        o.SalesChannel,
        o.CustomerId,
        c.ExternalReference,
        c.EmailAddress,
        c.RegionCode,
        o.ShipToRegionCode,
        o.SubtotalAmount,
        o.TaxAmount,
        o.ShippingAmount,
        o.TotalAmount;
GO

CREATE OR ALTER VIEW inventory.vw_InventoryRisk
AS
    SELECT
        b.WarehouseId,
        w.WarehouseCode,
        w.WarehouseName,
        b.ProductId,
        p.Sku,
        p.ProductName,
        b.QuantityOnHand,
        b.QuantityReserved,
        b.QuantityOnHand - b.QuantityReserved AS QuantityAvailable,
        b.ReorderPoint,
        b.BinLocation,
        b.LastCountedAtUtc,
        CASE
            WHEN b.QuantityOnHand - b.QuantityReserved <= 0 THEN 'OUT_OF_STOCK'
            WHEN b.QuantityOnHand - b.QuantityReserved <= b.ReorderPoint THEN 'REORDER'
            ELSE 'HEALTHY'
        END AS InventoryRisk
    FROM inventory.InventoryBalance b
    INNER JOIN inventory.Warehouse w
        ON w.WarehouseId = b.WarehouseId
    INNER JOIN catalog.Product p
        ON p.ProductId = b.ProductId;
GO

CREATE OR ALTER VIEW support.vw_OpenTicketBacklog
AS
    SELECT
        t.SupportTicketId,
        t.CreatedAtUtc,
        DATEDIFF(HOUR, t.CreatedAtUtc, SYSUTCDATETIME()) AS AgeHours,
        t.PriorityCode,
        t.TicketStatus,
        t.TicketCategory,
        t.AssignedTeam,
        t.CustomerId,
        c.ExternalReference AS CustomerReference,
        t.SalesOrderId,
        t.Subject
    FROM support.SupportTicket t
    INNER JOIN sales.Customer c
        ON c.CustomerId = t.CustomerId
    WHERE t.TicketStatus IN ('OPEN', 'PENDING');
GO

CREATE OR ALTER PROCEDURE sales.usp_GetCustomerOrderHistory
    @CustomerId int,
    @FromDate datetime2(3) = NULL
AS
BEGIN
    SET NOCOUNT ON;

    SELECT
        o.SalesOrderId,
        o.OrderNumber,
        o.OrderDateUtc,
        o.OrderStatusCode,
        o.SalesChannel,
        o.SubtotalAmount,
        o.TaxAmount,
        o.ShippingAmount,
        o.TotalAmount,
        p.PaymentStatus,
        p.PaymentMethod
    FROM sales.SalesOrder o
    LEFT JOIN sales.Payment p
        ON p.SalesOrderId = o.SalesOrderId
    WHERE o.CustomerId = @CustomerId
      AND (@FromDate IS NULL OR o.OrderDateUtc >= @FromDate)
    ORDER BY o.OrderDateUtc DESC;
END;
GO

CREATE OR ALTER PROCEDURE sales.usp_SearchOrdersByCalendarDate
    @OrderDate date
AS
BEGIN
    SET NOCOUNT ON;

    /*
        Intentional scenario: converting the indexed column makes the predicate
        non-SARGable. A future tuning workflow should propose a range predicate.
    */
    SELECT
        o.SalesOrderId,
        o.OrderNumber,
        o.CustomerId,
        o.OrderDateUtc,
        o.OrderStatusCode,
        o.TotalAmount
    FROM sales.SalesOrder o
    WHERE CONVERT(date, o.OrderDateUtc) = @OrderDate
    ORDER BY o.OrderDateUtc;
END;
GO

CREATE OR ALTER PROCEDURE sales.usp_FindCustomerByExternalReference
    @ExternalReference nvarchar(30)
AS
BEGIN
    SET NOCOUNT ON;

    /*
        Intentional scenario: the parameter is nvarchar while the indexed
        ExternalReference column is varchar, allowing an implicit conversion.
    */
    SELECT
        c.CustomerId,
        c.ExternalReference,
        c.EmailAddress,
        c.FirstName,
        c.LastName,
        c.RegionCode,
        c.CustomerStatus,
        c.SignupDate
    FROM sales.Customer c
    WHERE c.ExternalReference = @ExternalReference;
END;
GO

CREATE OR ALTER PROCEDURE sales.usp_GetProductSalesSummary
    @ProductId int,
    @FromDate datetime2(3),
    @ToDate datetime2(3)
AS
BEGIN
    SET NOCOUNT ON;

    /*
        Intentional scenario: SalesOrderLine has no index led by ProductId.
        The workload script repeats this query to produce observable evidence.
    */
    SELECT
        l.ProductId,
        COUNT_BIG(DISTINCT o.SalesOrderId) AS OrderCount,
        SUM(CONVERT(bigint, l.Quantity)) AS UnitCount,
        SUM(l.LineTotal) AS Revenue
    FROM sales.SalesOrderLine l
    INNER JOIN sales.SalesOrder o
        ON o.SalesOrderId = l.SalesOrderId
    WHERE l.ProductId = @ProductId
      AND o.OrderDateUtc >= @FromDate
      AND o.OrderDateUtc < @ToDate
    GROUP BY l.ProductId;
END;
GO

CREATE OR ALTER PROCEDURE support.usp_SearchTicketText
    @SearchText nvarchar(100)
AS
BEGIN
    SET NOCOUNT ON;

    /*
        Intentional scenario: leading-wildcard searches against large text
        columns become expensive as ticket volume grows.
    */
    SELECT
        t.SupportTicketId,
        t.CreatedAtUtc,
        t.PriorityCode,
        t.TicketStatus,
        t.TicketCategory,
        t.CustomerId,
        t.Subject
    FROM support.SupportTicket t
    WHERE t.Subject LIKE N'%' + @SearchText + N'%'
       OR t.Description LIKE N'%' + @SearchText + N'%'
    ORDER BY t.CreatedAtUtc DESC;
END;
GO
