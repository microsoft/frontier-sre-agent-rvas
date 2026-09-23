/*
    Purpose:
      Create deterministic transactional data with useful cardinality, time-based
      distribution, and deliberate skew.

    Default scale factor 1 creates approximately:
      500 products
      5,000 customers
      50,000 orders
      150,000 order lines
      100,000 stock movements
      5,000 support tickets
      15,000 ticket events

    Valid scale factors are 1 through 5. Scale 1 is recommended for the first
    installation and for lower Azure SQL Database service tiers.
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
    THROW 50020, 'Run 01_schema.sql and 02_seed_reference_data.sql before this script.', 1;
END;
GO

CREATE OR ALTER PROCEDURE lab.usp_GenerateSampleData
    @ScaleFactor tinyint = 1,
    @AsOfDate date = '2026-09-01'
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;

    IF @ScaleFactor NOT BETWEEN 1 AND 5
    BEGIN
        THROW 50021, 'ScaleFactor must be between 1 and 5.', 1;
    END;

    IF @AsOfDate IS NULL
    BEGIN
        THROW 50022, 'AsOfDate is required.', 1;
    END;

    IF NOT EXISTS (SELECT 1 FROM ref.Region)
       OR NOT EXISTS (SELECT 1 FROM ref.OrderStatus)
       OR NOT EXISTS (SELECT 1 FROM catalog.ProductCategory)
       OR NOT EXISTS (SELECT 1 FROM inventory.Warehouse)
    BEGIN
        THROW 50023, 'Reference data is missing. Run 02_seed_reference_data.sql first.', 1;
    END;

    IF EXISTS (SELECT 1 FROM catalog.Product)
       OR EXISTS (SELECT 1 FROM sales.Customer)
       OR EXISTS (SELECT 1 FROM sales.SalesOrder)
       OR EXISTS (SELECT 1 FROM inventory.StockMovement)
       OR EXISTS (SELECT 1 FROM support.SupportTicket)
    BEGIN
        THROW 50024, 'Generated data already exists. Run 99_teardown.sql to rebuild the lab.', 1;
    END;

    DECLARE @ProductCount int = 500 * @ScaleFactor;
    DECLARE @CustomerCount int = 5000 * @ScaleFactor;
    DECLARE @OrderCount int = 50000 * @ScaleFactor;
    DECLARE @StockMovementCount int = 100000 * @ScaleFactor;
    DECLARE @TicketCount int = 5000 * @ScaleFactor;

    BEGIN TRANSACTION;

    ;WITH
    E1(v) AS
    (
        SELECT v
        FROM (VALUES (0), (0), (0), (0), (0), (0), (0), (0), (0), (0)) d(v)
    ),
    E2(v) AS (SELECT 0 FROM E1 a CROSS JOIN E1 b),
    E3(v) AS (SELECT 0 FROM E2 a CROSS JOIN E1 b),
    E4(v) AS (SELECT 0 FROM E2 a CROSS JOIN E2 b),
    E7(v) AS (SELECT 0 FROM E4 a CROSS JOIN E3 b),
    N(n) AS
    (
        SELECT TOP (@ProductCount)
            CONVERT(int, ROW_NUMBER() OVER (ORDER BY (SELECT NULL)))
        FROM E7
    )
    INSERT catalog.Product
    (
        ProductId,
        Sku,
        ProductCategoryId,
        ProductName,
        UnitPrice,
        UnitCost,
        IsActive,
        CreatedAtUtc,
        AttributesJson
    )
    SELECT
        n,
        CONCAT('SKU-', RIGHT(CONCAT('0000000', n), 7)),
        CONVERT(smallint, ((n - 1) % 10) + 1),
        CONCAT(N'Sample Product ', n),
        price.UnitPrice,
        CONVERT(decimal(12, 2), ROUND(price.UnitPrice * 0.62, 2)),
        CASE WHEN n % 50 = 0 THEN 0 ELSE 1 END,
        DATEADD(DAY, -(n % 1095), CONVERT(datetime2(3), @AsOfDate)),
        CONCAT
        (
            N'{"brand":"Brand ',
            ((n - 1) % 25) + 1,
            N'","warrantyMonths":',
            CASE WHEN n % 3 = 0 THEN 36 WHEN n % 2 = 0 THEN 24 ELSE 12 END,
            N'}'
        )
    FROM N
    CROSS APPLY
    (
        VALUES (CONVERT(decimal(12, 2), 9.95 + ((n * 37) % 15000) / 10.0))
    ) price(UnitPrice);

    ;WITH
    E1(v) AS
    (
        SELECT v
        FROM (VALUES (0), (0), (0), (0), (0), (0), (0), (0), (0), (0)) d(v)
    ),
    E2(v) AS (SELECT 0 FROM E1 a CROSS JOIN E1 b),
    E3(v) AS (SELECT 0 FROM E2 a CROSS JOIN E1 b),
    E4(v) AS (SELECT 0 FROM E2 a CROSS JOIN E2 b),
    E7(v) AS (SELECT 0 FROM E4 a CROSS JOIN E3 b),
    N(n) AS
    (
        SELECT TOP (@CustomerCount)
            CONVERT(int, ROW_NUMBER() OVER (ORDER BY (SELECT NULL)))
        FROM E7
    )
    INSERT sales.Customer
    (
        CustomerId,
        ExternalReference,
        EmailAddress,
        FirstName,
        LastName,
        RegionCode,
        CustomerStatus,
        SignupDate,
        LastLoginAtUtc,
        ProfileJson
    )
    SELECT
        n,
        CONCAT('CUST-', RIGHT(CONCAT('000000000', n), 9)),
        CONCAT(N'customer', RIGHT(CONCAT('000000000', n), 9), N'@example.test'),
        CONCAT(N'First', n % 500),
        CONCAT(N'Last', n % 1000),
        CASE n % 8
            WHEN 0 THEN 'AU'
            WHEN 1 THEN 'DE'
            WHEN 2 THEN 'FR'
            WHEN 3 THEN 'GB'
            WHEN 4 THEN 'GR'
            WHEN 5 THEN 'JP'
            WHEN 6 THEN 'NL'
            ELSE 'US'
        END,
        CASE WHEN n % 100 = 0 THEN 'CLOSED' WHEN n % 25 = 0 THEN 'SUSPENDED' ELSE 'ACTIVE' END,
        DATEADD(DAY, -(n % 1825), @AsOfDate),
        DATEADD(MINUTE, -(n % 43200), CONVERT(datetime2(3), @AsOfDate)),
        CONCAT
        (
            N'{"segment":"',
            CASE WHEN n = 1 THEN N'VIP' WHEN n % 10 = 0 THEN N'BUSINESS' ELSE N'CONSUMER' END,
            N'","marketingOptIn":',
            CASE WHEN n % 3 = 0 THEN N'false' ELSE N'true' END,
            N'}'
        )
    FROM N;

    ;WITH
    E1(v) AS
    (
        SELECT v
        FROM (VALUES (0), (0), (0), (0), (0), (0), (0), (0), (0), (0)) d(v)
    ),
    E2(v) AS (SELECT 0 FROM E1 a CROSS JOIN E1 b),
    E3(v) AS (SELECT 0 FROM E2 a CROSS JOIN E1 b),
    E4(v) AS (SELECT 0 FROM E2 a CROSS JOIN E2 b),
    E7(v) AS (SELECT 0 FROM E4 a CROSS JOIN E3 b),
    N(n) AS
    (
        SELECT TOP (@OrderCount)
            CONVERT(bigint, ROW_NUMBER() OVER (ORDER BY (SELECT NULL)))
        FROM E7
    ),
    OrderSource AS
    (
        SELECT
            n,
            CASE
                WHEN n % 5 = 0 THEN 1
                ELSE CONVERT(int, ((n * 7919) % @CustomerCount) + 1)
            END AS CustomerId,
            CASE
                WHEN n % 100 < 2 THEN 'CANCELLED'
                WHEN n % 100 < 5 THEN 'RETURNED'
                WHEN n % 100 < 10 THEN 'NEW'
                WHEN n % 100 < 15 THEN 'PAID'
                WHEN n % 100 < 25 THEN 'PACKED'
                WHEN n % 100 < 40 THEN 'SHIPPED'
                ELSE 'COMPLETED'
            END AS OrderStatusCode,
            DATEADD
            (
                MINUTE,
                CONVERT(int, n % 1440),
                DATEADD
                (
                    DAY,
                    -CONVERT(int, CASE WHEN n % 4 = 0 THEN n % 30 ELSE n % 730 END),
                    CONVERT(datetime2(3), @AsOfDate)
                )
            ) AS OrderDateUtc
        FROM N
    )
    INSERT sales.SalesOrder
    (
        SalesOrderId,
        OrderNumber,
        CustomerId,
        OrderStatusCode,
        OrderDateUtc,
        ShipToRegionCode,
        SalesChannel,
        PromotionCode,
        SubtotalAmount,
        TaxAmount,
        ShippingAmount,
        TotalAmount,
        CustomerNotes
    )
    SELECT
        s.n,
        CONCAT('SO-', RIGHT(CONCAT('000000000000', s.n), 12)),
        s.CustomerId,
        s.OrderStatusCode,
        s.OrderDateUtc,
        c.RegionCode,
        CASE s.n % 4
            WHEN 0 THEN 'WEB'
            WHEN 1 THEN 'MOBILE'
            WHEN 2 THEN 'MARKETPLACE'
            ELSE 'CALL_CENTER'
        END,
        CASE WHEN s.n % 20 = 0 THEN CONCAT('PROMO-', RIGHT(CONCAT('00', s.n % 12), 2)) END,
        0,
        0,
        0,
        0,
        CASE WHEN s.n % 25 = 0 THEN CONCAT(N'Customer requested special handling for order ', s.n) END
    FROM OrderSource s
    INNER JOIN sales.Customer c
        ON c.CustomerId = s.CustomerId;

    ;WITH
    E1(v) AS
    (
        SELECT v
        FROM (VALUES (0), (0), (0), (0), (0), (0), (0), (0), (0), (0)) d(v)
    ),
    E2(v) AS (SELECT 0 FROM E1 a CROSS JOIN E1 b),
    E3(v) AS (SELECT 0 FROM E2 a CROSS JOIN E1 b),
    E4(v) AS (SELECT 0 FROM E2 a CROSS JOIN E2 b),
    E7(v) AS (SELECT 0 FROM E4 a CROSS JOIN E3 b),
    Candidate(n) AS
    (
        SELECT TOP (@OrderCount * 5)
            CONVERT(bigint, ROW_NUMBER() OVER (ORDER BY (SELECT NULL)))
        FROM E7
    ),
    LineSource AS
    (
        SELECT
            n AS CandidateId,
            ((n - 1) / 5) + 1 AS SalesOrderId,
            CONVERT(smallint, ((n - 1) % 5) + 1) AS LineNumber
        FROM Candidate
    )
    INSERT sales.SalesOrderLine
    (
        SalesOrderLineId,
        SalesOrderId,
        LineNumber,
        ProductId,
        Quantity,
        UnitPrice,
        DiscountAmount,
        TaxAmount
    )
    SELECT
        l.CandidateId,
        l.SalesOrderId,
        l.LineNumber,
        productKey.ProductId,
        amount.Quantity,
        p.UnitPrice,
        amount.DiscountAmount,
        CONVERT(decimal(12, 2), ROUND((amount.GrossAmount - amount.DiscountAmount) * 0.08, 2))
    FROM LineSource l
    CROSS APPLY
    (
        VALUES
        (
            CASE
                WHEN l.CandidateId % 10 < 3 THEN 1
                ELSE CONVERT(int, ((l.CandidateId * 1543) % @ProductCount) + 1)
            END
        )
    ) productKey(ProductId)
    INNER JOIN catalog.Product p
        ON p.ProductId = productKey.ProductId
    CROSS APPLY
    (
        VALUES
        (
            CONVERT(smallint, (l.CandidateId % 4) + 1),
            CONVERT(decimal(19, 4), ((l.CandidateId % 4) + 1) * p.UnitPrice)
        )
    ) gross(Quantity, GrossAmount)
    CROSS APPLY
    (
        VALUES
        (
            gross.Quantity,
            gross.GrossAmount,
            CONVERT
            (
                decimal(12, 2),
                CASE WHEN l.CandidateId % 10 = 0 THEN ROUND(gross.GrossAmount * 0.10, 2) ELSE 0 END
            )
        )
    ) amount(Quantity, GrossAmount, DiscountAmount)
    WHERE l.LineNumber <= (l.SalesOrderId % 5) + 1;

    UPDATE o
    SET
        SubtotalAmount = totals.SubtotalAmount,
        TaxAmount = totals.TaxAmount,
        ShippingAmount = shipping.ShippingAmount,
        TotalAmount = totals.SubtotalAmount + totals.TaxAmount + shipping.ShippingAmount
    FROM sales.SalesOrder o
    INNER JOIN
    (
        SELECT
            SalesOrderId,
            CONVERT
            (
                decimal(19, 4),
                SUM(CONVERT(decimal(19, 4), Quantity) * UnitPrice - DiscountAmount)
            ) AS SubtotalAmount,
            CONVERT(decimal(19, 4), SUM(TaxAmount)) AS TaxAmount
        FROM sales.SalesOrderLine
        GROUP BY SalesOrderId
    ) totals
        ON totals.SalesOrderId = o.SalesOrderId
    CROSS APPLY
    (
        VALUES
        (
            CONVERT
            (
                decimal(19, 4),
                CASE WHEN totals.SubtotalAmount >= 100 THEN 0 ELSE 7.95 END
            )
        )
    ) shipping(ShippingAmount);

    INSERT sales.Payment
    (
        PaymentId,
        SalesOrderId,
        PaymentMethod,
        PaymentStatus,
        Amount,
        ProcessedAtUtc,
        ProviderReference,
        FailureReason
    )
    SELECT
        o.SalesOrderId,
        o.SalesOrderId,
        CASE o.SalesOrderId % 4
            WHEN 0 THEN 'CARD'
            WHEN 1 THEN 'BANK_TRANSFER'
            WHEN 2 THEN 'WALLET'
            ELSE 'INVOICE'
        END,
        CASE
            WHEN o.OrderStatusCode IN ('CANCELLED', 'RETURNED') THEN 'REFUNDED'
            ELSE 'CAPTURED'
        END,
        o.TotalAmount,
        DATEADD(MINUTE, 15, o.OrderDateUtc),
        CONCAT('PAY-', RIGHT(CONCAT('000000000000', o.SalesOrderId), 12)),
        NULL
    FROM sales.SalesOrder o
    WHERE o.OrderStatusCode <> 'NEW';

    INSERT inventory.InventoryBalance
    (
        WarehouseId,
        ProductId,
        QuantityOnHand,
        QuantityReserved,
        ReorderPoint,
        BinLocation,
        LastCountedAtUtc
    )
    SELECT
        w.WarehouseId,
        p.ProductId,
        stock.QuantityOnHand,
        CONVERT(int, stock.QuantityOnHand * 0.15),
        20 + (p.ProductId % 50),
        CONCAT(CHAR(65 + (p.ProductId % 20)), '-', RIGHT(CONCAT('000', p.ProductId % 500), 3)),
        DATEADD(DAY, -(p.ProductId % 90), CONVERT(datetime2(3), @AsOfDate))
    FROM inventory.Warehouse w
    CROSS JOIN catalog.Product p
    CROSS APPLY
    (
        VALUES (CONVERT(int, 30 + ((w.WarehouseId * 97 + p.ProductId * 13) % 500)))
    ) stock(QuantityOnHand);

    ;WITH
    E1(v) AS
    (
        SELECT v
        FROM (VALUES (0), (0), (0), (0), (0), (0), (0), (0), (0), (0)) d(v)
    ),
    E2(v) AS (SELECT 0 FROM E1 a CROSS JOIN E1 b),
    E3(v) AS (SELECT 0 FROM E2 a CROSS JOIN E1 b),
    E4(v) AS (SELECT 0 FROM E2 a CROSS JOIN E2 b),
    E7(v) AS (SELECT 0 FROM E4 a CROSS JOIN E3 b),
    N(n) AS
    (
        SELECT TOP (@StockMovementCount)
            CONVERT(bigint, ROW_NUMBER() OVER (ORDER BY (SELECT NULL)))
        FROM E7
    )
    INSERT inventory.StockMovement
    (
        StockMovementId,
        WarehouseId,
        ProductId,
        MovementType,
        QuantityChange,
        OccurredAtUtc,
        ReferenceNumber,
        Reason
    )
    SELECT
        n,
        CONVERT(smallint, ((n - 1) % 4) + 1),
        CASE WHEN n % 8 = 0 THEN 1 ELSE CONVERT(int, ((n * 1543) % @ProductCount) + 1) END,
        movement.MovementType,
        CASE
            WHEN movement.MovementType IN ('SALE', 'TRANSFER_OUT') THEN -CONVERT(int, (n % 4) + 1)
            ELSE CONVERT(int, (n % 20) + 1)
        END,
        DATEADD
        (
            MINUTE,
            -CONVERT(int, n % 1051200),
            CONVERT(datetime2(3), @AsOfDate)
        ),
        CONCAT('MOV-', RIGHT(CONCAT('000000000000', n), 12)),
        CASE WHEN n % 25 = 0 THEN N'Cycle-count correction' END
    FROM N
    CROSS APPLY
    (
        VALUES
        (
            CASE n % 6
                WHEN 0 THEN 'RECEIPT'
                WHEN 1 THEN 'SALE'
                WHEN 2 THEN 'RETURN'
                WHEN 3 THEN 'ADJUSTMENT'
                WHEN 4 THEN 'TRANSFER_IN'
                ELSE 'TRANSFER_OUT'
            END
        )
    ) movement(MovementType);

    ;WITH
    E1(v) AS
    (
        SELECT v
        FROM (VALUES (0), (0), (0), (0), (0), (0), (0), (0), (0), (0)) d(v)
    ),
    E2(v) AS (SELECT 0 FROM E1 a CROSS JOIN E1 b),
    E3(v) AS (SELECT 0 FROM E2 a CROSS JOIN E1 b),
    E4(v) AS (SELECT 0 FROM E2 a CROSS JOIN E2 b),
    E7(v) AS (SELECT 0 FROM E4 a CROSS JOIN E3 b),
    N(n) AS
    (
        SELECT TOP (@TicketCount)
            CONVERT(bigint, ROW_NUMBER() OVER (ORDER BY (SELECT NULL)))
        FROM E7
    ),
    TicketSource AS
    (
        SELECT
            n,
            CASE WHEN n % 10 = 0 THEN 1 ELSE CONVERT(int, ((n * 3571) % @CustomerCount) + 1) END AS CustomerId,
            ((n * 7919) % @OrderCount) + 1 AS SalesOrderId,
            DATEADD
            (
                HOUR,
                -CONVERT(int, n % 17520),
                CONVERT(datetime2(3), @AsOfDate)
            ) AS CreatedAtUtc,
            CASE
                WHEN n % 100 < 25 THEN 'OPEN'
                WHEN n % 100 < 35 THEN 'PENDING'
                WHEN n % 100 < 55 THEN 'RESOLVED'
                ELSE 'CLOSED'
            END AS TicketStatus
        FROM N
    )
    INSERT support.SupportTicket
    (
        SupportTicketId,
        CustomerId,
        SalesOrderId,
        CreatedAtUtc,
        ClosedAtUtc,
        PriorityCode,
        TicketStatus,
        TicketCategory,
        AssignedTeam,
        Subject,
        Description,
        SatisfactionScore
    )
    SELECT
        n,
        CustomerId,
        CASE WHEN n % 8 = 0 THEN NULL ELSE SalesOrderId END,
        CreatedAtUtc,
        CASE
            WHEN TicketStatus IN ('RESOLVED', 'CLOSED') THEN DATEADD(HOUR, CONVERT(int, (n % 96) + 1), CreatedAtUtc)
        END,
        CASE
            WHEN n % 100 < 2 THEN 'P1'
            WHEN n % 100 < 12 THEN 'P2'
            WHEN n % 100 < 52 THEN 'P3'
            ELSE 'P4'
        END,
        TicketStatus,
        CASE n % 5
            WHEN 0 THEN 'DELIVERY'
            WHEN 1 THEN 'PAYMENT'
            WHEN 2 THEN 'PRODUCT'
            WHEN 3 THEN 'RETURN'
            ELSE 'ACCOUNT'
        END,
        CASE n % 4
            WHEN 0 THEN 'ORDER_SUPPORT'
            WHEN 1 THEN 'BILLING'
            WHEN 2 THEN 'TECHNICAL'
            ELSE 'CUSTOMER_CARE'
        END,
        CONCAT(N'Sample support request ', n),
        CONCAT
        (
            N'Customer reported a reproducible sample issue. Diagnostic correlation value: ',
            RIGHT(CONCAT('000000000000', n), 12),
            N'.'
        ),
        CASE WHEN TicketStatus IN ('RESOLVED', 'CLOSED') THEN CONVERT(tinyint, (n % 5) + 1) END
    FROM TicketSource;

    ;WITH
    E1(v) AS
    (
        SELECT v
        FROM (VALUES (0), (0), (0), (0), (0), (0), (0), (0), (0), (0)) d(v)
    ),
    E2(v) AS (SELECT 0 FROM E1 a CROSS JOIN E1 b),
    E3(v) AS (SELECT 0 FROM E2 a CROSS JOIN E1 b),
    E4(v) AS (SELECT 0 FROM E2 a CROSS JOIN E2 b),
    E7(v) AS (SELECT 0 FROM E4 a CROSS JOIN E3 b),
    N(n) AS
    (
        SELECT TOP (@TicketCount * 3)
            CONVERT(bigint, ROW_NUMBER() OVER (ORDER BY (SELECT NULL)))
        FROM E7
    ),
    EventSource AS
    (
        SELECT
            n,
            ((n - 1) / 3) + 1 AS SupportTicketId,
            CONVERT(tinyint, ((n - 1) % 3) + 1) AS EventSequence
        FROM N
    )
    INSERT support.TicketEvent
    (
        TicketEventId,
        SupportTicketId,
        EventAtUtc,
        EventType,
        ActorType,
        EventDetails
    )
    SELECT
        e.n,
        e.SupportTicketId,
        DATEADD(MINUTE, e.EventSequence * 30, t.CreatedAtUtc),
        CASE e.EventSequence WHEN 1 THEN 'CREATED' WHEN 2 THEN 'COMMENT' ELSE 'STATUS_CHANGE' END,
        CASE e.EventSequence WHEN 1 THEN 'CUSTOMER' WHEN 2 THEN 'AGENT' ELSE 'SYSTEM' END,
        CASE e.EventSequence
            WHEN 1 THEN N'Ticket created through the customer portal.'
            WHEN 2 THEN N'Agent reviewed the request and added diagnostic context.'
            ELSE CONCAT(N'Ticket status recorded as ', t.TicketStatus, N'.')
        END
    FROM EventSource e
    INNER JOIN support.SupportTicket t
        ON t.SupportTicketId = e.SupportTicketId;

    UPDATE lab.BuildInfo
    SET
        DataGeneratedAtUtc = SYSUTCDATETIME(),
        SeedAsOfDate = @AsOfDate,
        ScaleFactor = @ScaleFactor
    WHERE BuildInfoId = 1;

    DECLARE @RestartWith bigint;
    DECLARE @SequenceSql nvarchar(200);

    SELECT @RestartWith = MAX(ProductId) + 1 FROM catalog.Product;
    SET @SequenceSql = CONCAT(N'ALTER SEQUENCE catalog.SeqProductId RESTART WITH ', @RestartWith, N';');
    EXEC sys.sp_executesql @SequenceSql;

    SELECT @RestartWith = MAX(CustomerId) + 1 FROM sales.Customer;
    SET @SequenceSql = CONCAT(N'ALTER SEQUENCE sales.SeqCustomerId RESTART WITH ', @RestartWith, N';');
    EXEC sys.sp_executesql @SequenceSql;

    SELECT @RestartWith = MAX(SalesOrderId) + 1 FROM sales.SalesOrder;
    SET @SequenceSql = CONCAT(N'ALTER SEQUENCE sales.SeqOrderId RESTART WITH ', @RestartWith, N';');
    EXEC sys.sp_executesql @SequenceSql;

    SELECT @RestartWith = MAX(SalesOrderLineId) + 1 FROM sales.SalesOrderLine;
    SET @SequenceSql = CONCAT(N'ALTER SEQUENCE sales.SeqOrderLineId RESTART WITH ', @RestartWith, N';');
    EXEC sys.sp_executesql @SequenceSql;

    SELECT @RestartWith = MAX(PaymentId) + 1 FROM sales.Payment;
    SET @SequenceSql = CONCAT(N'ALTER SEQUENCE sales.SeqPaymentId RESTART WITH ', @RestartWith, N';');
    EXEC sys.sp_executesql @SequenceSql;

    SELECT @RestartWith = MAX(StockMovementId) + 1 FROM inventory.StockMovement;
    SET @SequenceSql = CONCAT(N'ALTER SEQUENCE inventory.SeqStockMovementId RESTART WITH ', @RestartWith, N';');
    EXEC sys.sp_executesql @SequenceSql;

    SELECT @RestartWith = MAX(SupportTicketId) + 1 FROM support.SupportTicket;
    SET @SequenceSql = CONCAT(N'ALTER SEQUENCE support.SeqTicketId RESTART WITH ', @RestartWith, N';');
    EXEC sys.sp_executesql @SequenceSql;

    SELECT @RestartWith = MAX(TicketEventId) + 1 FROM support.TicketEvent;
    SET @SequenceSql = CONCAT(N'ALTER SEQUENCE support.SeqTicketEventId RESTART WITH ', @RestartWith, N';');
    EXEC sys.sp_executesql @SequenceSql;

    COMMIT TRANSACTION;
END;
GO

/*
    Change @ScaleFactor before execution if more data is required.
    Scale 1 is the recommended starting point.
*/
EXEC lab.usp_GenerateSampleData
    @ScaleFactor = 1,
    @AsOfDate = '2026-09-01';
GO
