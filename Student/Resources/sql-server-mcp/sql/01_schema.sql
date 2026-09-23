/*
    Purpose:
      Create the schemas, sequences, tables, constraints, and baseline indexes for
      the DBA SRE sample database.

    This is a one-time installation script. Run sql/99_teardown.sql before
    reinstalling an existing lab.
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

IF DB_NAME() = N'master'
BEGIN
    THROW 50000, 'Connect to the target user database before running this script.', 1;
END;

IF OBJECT_ID(N'lab.BuildInfo', N'U') IS NOT NULL
BEGIN
    THROW 50002, 'The DBA SRE sample database is already installed. Run 99_teardown.sql before reinstalling.', 1;
END;
GO

IF SCHEMA_ID(N'ref') IS NULL EXEC(N'CREATE SCHEMA ref AUTHORIZATION dbo;');
IF SCHEMA_ID(N'catalog') IS NULL EXEC(N'CREATE SCHEMA catalog AUTHORIZATION dbo;');
IF SCHEMA_ID(N'sales') IS NULL EXEC(N'CREATE SCHEMA sales AUTHORIZATION dbo;');
IF SCHEMA_ID(N'inventory') IS NULL EXEC(N'CREATE SCHEMA inventory AUTHORIZATION dbo;');
IF SCHEMA_ID(N'support') IS NULL EXEC(N'CREATE SCHEMA support AUTHORIZATION dbo;');
IF SCHEMA_ID(N'lab') IS NULL EXEC(N'CREATE SCHEMA lab AUTHORIZATION dbo;');
GO

CREATE SEQUENCE catalog.SeqProductId AS int START WITH 1 INCREMENT BY 1 CACHE 100;
CREATE SEQUENCE sales.SeqCustomerId AS int START WITH 1 INCREMENT BY 1 CACHE 100;
CREATE SEQUENCE sales.SeqOrderId AS bigint START WITH 1 INCREMENT BY 1 CACHE 1000;
CREATE SEQUENCE sales.SeqOrderLineId AS bigint START WITH 1 INCREMENT BY 1 CACHE 1000;
CREATE SEQUENCE sales.SeqPaymentId AS bigint START WITH 1 INCREMENT BY 1 CACHE 1000;
CREATE SEQUENCE inventory.SeqStockMovementId AS bigint START WITH 1 INCREMENT BY 1 CACHE 1000;
CREATE SEQUENCE support.SeqTicketId AS bigint START WITH 1 INCREMENT BY 1 CACHE 100;
CREATE SEQUENCE support.SeqTicketEventId AS bigint START WITH 1 INCREMENT BY 1 CACHE 1000;
GO

CREATE TABLE lab.BuildInfo
(
    BuildInfoId tinyint NOT NULL
        CONSTRAINT PK_BuildInfo PRIMARY KEY
        CONSTRAINT CK_BuildInfo_SingleRow CHECK (BuildInfoId = 1),
    SchemaVersion varchar(20) NOT NULL,
    InstalledAtUtc datetime2(3) NOT NULL
        CONSTRAINT DF_BuildInfo_InstalledAtUtc DEFAULT SYSUTCDATETIME(),
    DataGeneratedAtUtc datetime2(3) NULL,
    SeedAsOfDate date NULL,
    ScaleFactor tinyint NULL,
    CONSTRAINT CK_BuildInfo_ScaleFactor
        CHECK (ScaleFactor IS NULL OR ScaleFactor BETWEEN 1 AND 5)
);

CREATE TABLE lab.Scenario
(
    ScenarioCode varchar(40) NOT NULL
        CONSTRAINT PK_Scenario PRIMARY KEY,
    ScenarioTitle nvarchar(120) NOT NULL,
    ScenarioCategory varchar(30) NOT NULL,
    Objective nvarchar(1000) NOT NULL,
    WorkloadScript varchar(200) NULL,
    ExpectedSignal nvarchar(1000) NOT NULL,
    IsEnabled bit NOT NULL
        CONSTRAINT DF_Scenario_IsEnabled DEFAULT (1),
    CONSTRAINT CK_Scenario_Category CHECK
    (
        ScenarioCategory IN
        (
            'BASELINE',
            'INDEXING',
            'QUERY_TUNING',
            'PLAN_QUALITY',
            'CONCURRENCY',
            'CAPACITY'
        )
    )
);

CREATE TABLE ref.Region
(
    RegionCode char(2) NOT NULL
        CONSTRAINT PK_Region PRIMARY KEY,
    RegionName nvarchar(100) NOT NULL,
    CurrencyCode char(3) NOT NULL,
    IsActive bit NOT NULL
        CONSTRAINT DF_Region_IsActive DEFAULT (1)
);

CREATE TABLE ref.OrderStatus
(
    OrderStatusCode varchar(20) NOT NULL
        CONSTRAINT PK_OrderStatus PRIMARY KEY,
    StatusName nvarchar(100) NOT NULL,
    IsTerminal bit NOT NULL,
    SortOrder tinyint NOT NULL,
    CONSTRAINT UQ_OrderStatus_SortOrder UNIQUE (SortOrder)
);

CREATE TABLE catalog.ProductCategory
(
    ProductCategoryId smallint NOT NULL
        CONSTRAINT PK_ProductCategory PRIMARY KEY,
    ParentProductCategoryId smallint NULL,
    CategoryName nvarchar(100) NOT NULL,
    IsActive bit NOT NULL
        CONSTRAINT DF_ProductCategory_IsActive DEFAULT (1),
    CONSTRAINT UQ_ProductCategory_CategoryName UNIQUE (CategoryName),
    CONSTRAINT FK_ProductCategory_Parent FOREIGN KEY (ParentProductCategoryId)
        REFERENCES catalog.ProductCategory(ProductCategoryId)
);

CREATE TABLE catalog.Product
(
    ProductId int NOT NULL
        CONSTRAINT DF_Product_ProductId DEFAULT (NEXT VALUE FOR catalog.SeqProductId)
        CONSTRAINT PK_Product PRIMARY KEY,
    Sku varchar(20) NOT NULL,
    ProductCategoryId smallint NOT NULL,
    ProductName nvarchar(200) NOT NULL,
    UnitPrice decimal(12, 2) NOT NULL,
    UnitCost decimal(12, 2) NOT NULL,
    IsActive bit NOT NULL
        CONSTRAINT DF_Product_IsActive DEFAULT (1),
    CreatedAtUtc datetime2(3) NOT NULL
        CONSTRAINT DF_Product_CreatedAtUtc DEFAULT SYSUTCDATETIME(),
    AttributesJson nvarchar(max) NULL,
    RowVersion rowversion NOT NULL,
    CONSTRAINT UQ_Product_Sku UNIQUE (Sku),
    CONSTRAINT CK_Product_Price CHECK (UnitPrice > 0 AND UnitCost >= 0 AND UnitPrice >= UnitCost),
    CONSTRAINT CK_Product_AttributesJson CHECK (AttributesJson IS NULL OR ISJSON(AttributesJson) = 1),
    CONSTRAINT FK_Product_ProductCategory FOREIGN KEY (ProductCategoryId)
        REFERENCES catalog.ProductCategory(ProductCategoryId)
);

CREATE TABLE sales.Customer
(
    CustomerId int NOT NULL
        CONSTRAINT DF_Customer_CustomerId DEFAULT (NEXT VALUE FOR sales.SeqCustomerId)
        CONSTRAINT PK_Customer PRIMARY KEY,
    ExternalReference varchar(30) NOT NULL,
    EmailAddress nvarchar(320) NOT NULL,
    FirstName nvarchar(100) NOT NULL,
    LastName nvarchar(100) NOT NULL,
    RegionCode char(2) NOT NULL,
    CustomerStatus varchar(20) NOT NULL,
    SignupDate date NOT NULL,
    LastLoginAtUtc datetime2(3) NULL,
    ProfileJson nvarchar(max) NULL,
    RowVersion rowversion NOT NULL,
    CONSTRAINT UQ_Customer_ExternalReference UNIQUE (ExternalReference),
    CONSTRAINT UQ_Customer_EmailAddress UNIQUE (EmailAddress),
    CONSTRAINT CK_Customer_Status CHECK (CustomerStatus IN ('ACTIVE', 'SUSPENDED', 'CLOSED')),
    CONSTRAINT CK_Customer_ProfileJson CHECK (ProfileJson IS NULL OR ISJSON(ProfileJson) = 1),
    CONSTRAINT FK_Customer_Region FOREIGN KEY (RegionCode)
        REFERENCES ref.Region(RegionCode)
);

CREATE TABLE sales.SalesOrder
(
    SalesOrderId bigint NOT NULL
        CONSTRAINT DF_SalesOrder_SalesOrderId DEFAULT (NEXT VALUE FOR sales.SeqOrderId)
        CONSTRAINT PK_SalesOrder PRIMARY KEY,
    OrderNumber varchar(20) NOT NULL,
    CustomerId int NOT NULL,
    OrderStatusCode varchar(20) NOT NULL,
    OrderDateUtc datetime2(3) NOT NULL,
    ShipToRegionCode char(2) NOT NULL,
    SalesChannel varchar(20) NOT NULL,
    PromotionCode varchar(30) NULL,
    SubtotalAmount decimal(19, 4) NOT NULL,
    TaxAmount decimal(19, 4) NOT NULL,
    ShippingAmount decimal(19, 4) NOT NULL,
    TotalAmount decimal(19, 4) NOT NULL,
    CustomerNotes nvarchar(1000) NULL,
    RowVersion rowversion NOT NULL,
    CONSTRAINT UQ_SalesOrder_OrderNumber UNIQUE (OrderNumber),
    CONSTRAINT CK_SalesOrder_Channel CHECK (SalesChannel IN ('WEB', 'MOBILE', 'MARKETPLACE', 'CALL_CENTER')),
    CONSTRAINT CK_SalesOrder_Amounts CHECK
    (
        SubtotalAmount >= 0
        AND TaxAmount >= 0
        AND ShippingAmount >= 0
        AND TotalAmount = SubtotalAmount + TaxAmount + ShippingAmount
    ),
    CONSTRAINT FK_SalesOrder_Customer FOREIGN KEY (CustomerId)
        REFERENCES sales.Customer(CustomerId),
    CONSTRAINT FK_SalesOrder_OrderStatus FOREIGN KEY (OrderStatusCode)
        REFERENCES ref.OrderStatus(OrderStatusCode),
    CONSTRAINT FK_SalesOrder_ShipToRegion FOREIGN KEY (ShipToRegionCode)
        REFERENCES ref.Region(RegionCode)
);

CREATE TABLE sales.SalesOrderLine
(
    SalesOrderLineId bigint NOT NULL
        CONSTRAINT DF_SalesOrderLine_SalesOrderLineId DEFAULT (NEXT VALUE FOR sales.SeqOrderLineId)
        CONSTRAINT PK_SalesOrderLine PRIMARY KEY,
    SalesOrderId bigint NOT NULL,
    LineNumber smallint NOT NULL,
    ProductId int NOT NULL,
    Quantity smallint NOT NULL,
    UnitPrice decimal(12, 2) NOT NULL,
    DiscountAmount decimal(12, 2) NOT NULL,
    TaxAmount decimal(12, 2) NOT NULL,
    LineTotal AS
    (
        CONVERT
        (
            decimal(19, 4),
            (CONVERT(decimal(19, 4), Quantity) * UnitPrice) - DiscountAmount + TaxAmount
        )
    ) PERSISTED,
    CONSTRAINT UQ_SalesOrderLine_Order_Line UNIQUE (SalesOrderId, LineNumber),
    CONSTRAINT CK_SalesOrderLine_Quantity CHECK (Quantity > 0),
    CONSTRAINT CK_SalesOrderLine_Amounts CHECK
    (
        UnitPrice > 0
        AND DiscountAmount >= 0
        AND TaxAmount >= 0
        AND DiscountAmount <= CONVERT(decimal(19, 4), Quantity) * UnitPrice
    ),
    CONSTRAINT FK_SalesOrderLine_SalesOrder FOREIGN KEY (SalesOrderId)
        REFERENCES sales.SalesOrder(SalesOrderId),
    CONSTRAINT FK_SalesOrderLine_Product FOREIGN KEY (ProductId)
        REFERENCES catalog.Product(ProductId)
);

CREATE TABLE sales.Payment
(
    PaymentId bigint NOT NULL
        CONSTRAINT DF_Payment_PaymentId DEFAULT (NEXT VALUE FOR sales.SeqPaymentId)
        CONSTRAINT PK_Payment PRIMARY KEY,
    SalesOrderId bigint NOT NULL,
    PaymentMethod varchar(20) NOT NULL,
    PaymentStatus varchar(20) NOT NULL,
    Amount decimal(19, 4) NOT NULL,
    ProcessedAtUtc datetime2(3) NOT NULL,
    ProviderReference varchar(50) NOT NULL,
    FailureReason nvarchar(500) NULL,
    CONSTRAINT UQ_Payment_ProviderReference UNIQUE (ProviderReference),
    CONSTRAINT CK_Payment_Method CHECK (PaymentMethod IN ('CARD', 'BANK_TRANSFER', 'WALLET', 'INVOICE')),
    CONSTRAINT CK_Payment_Status CHECK (PaymentStatus IN ('AUTHORIZED', 'CAPTURED', 'FAILED', 'REFUNDED')),
    CONSTRAINT CK_Payment_Amount CHECK (Amount > 0),
    CONSTRAINT FK_Payment_SalesOrder FOREIGN KEY (SalesOrderId)
        REFERENCES sales.SalesOrder(SalesOrderId)
);

CREATE TABLE inventory.Warehouse
(
    WarehouseId smallint NOT NULL
        CONSTRAINT PK_Warehouse PRIMARY KEY,
    WarehouseCode varchar(20) NOT NULL,
    WarehouseName nvarchar(100) NOT NULL,
    RegionCode char(2) NOT NULL,
    IsActive bit NOT NULL
        CONSTRAINT DF_Warehouse_IsActive DEFAULT (1),
    CONSTRAINT UQ_Warehouse_WarehouseCode UNIQUE (WarehouseCode),
    CONSTRAINT FK_Warehouse_Region FOREIGN KEY (RegionCode)
        REFERENCES ref.Region(RegionCode)
);

CREATE TABLE inventory.InventoryBalance
(
    WarehouseId smallint NOT NULL,
    ProductId int NOT NULL,
    QuantityOnHand int NOT NULL,
    QuantityReserved int NOT NULL,
    ReorderPoint int NOT NULL,
    BinLocation varchar(20) NOT NULL,
    LastCountedAtUtc datetime2(3) NOT NULL,
    RowVersion rowversion NOT NULL,
    CONSTRAINT PK_InventoryBalance PRIMARY KEY (WarehouseId, ProductId),
    CONSTRAINT CK_InventoryBalance_Quantities CHECK
    (
        QuantityOnHand >= 0
        AND QuantityReserved >= 0
        AND QuantityReserved <= QuantityOnHand
        AND ReorderPoint >= 0
    ),
    CONSTRAINT FK_InventoryBalance_Warehouse FOREIGN KEY (WarehouseId)
        REFERENCES inventory.Warehouse(WarehouseId),
    CONSTRAINT FK_InventoryBalance_Product FOREIGN KEY (ProductId)
        REFERENCES catalog.Product(ProductId)
);

CREATE TABLE inventory.StockMovement
(
    StockMovementId bigint NOT NULL
        CONSTRAINT DF_StockMovement_StockMovementId DEFAULT (NEXT VALUE FOR inventory.SeqStockMovementId)
        CONSTRAINT PK_StockMovement PRIMARY KEY,
    WarehouseId smallint NOT NULL,
    ProductId int NOT NULL,
    MovementType varchar(20) NOT NULL,
    QuantityChange int NOT NULL,
    OccurredAtUtc datetime2(3) NOT NULL,
    ReferenceNumber varchar(30) NOT NULL,
    Reason nvarchar(300) NULL,
    CONSTRAINT CK_StockMovement_Type CHECK
    (
        MovementType IN ('RECEIPT', 'SALE', 'RETURN', 'ADJUSTMENT', 'TRANSFER_IN', 'TRANSFER_OUT')
    ),
    CONSTRAINT CK_StockMovement_Quantity CHECK (QuantityChange <> 0),
    CONSTRAINT FK_StockMovement_Warehouse FOREIGN KEY (WarehouseId)
        REFERENCES inventory.Warehouse(WarehouseId),
    CONSTRAINT FK_StockMovement_Product FOREIGN KEY (ProductId)
        REFERENCES catalog.Product(ProductId)
);

CREATE TABLE support.SupportTicket
(
    SupportTicketId bigint NOT NULL
        CONSTRAINT DF_SupportTicket_SupportTicketId DEFAULT (NEXT VALUE FOR support.SeqTicketId)
        CONSTRAINT PK_SupportTicket PRIMARY KEY,
    CustomerId int NOT NULL,
    SalesOrderId bigint NULL,
    CreatedAtUtc datetime2(3) NOT NULL,
    ClosedAtUtc datetime2(3) NULL,
    PriorityCode varchar(10) NOT NULL,
    TicketStatus varchar(20) NOT NULL,
    TicketCategory varchar(30) NOT NULL,
    AssignedTeam varchar(30) NOT NULL,
    Subject nvarchar(200) NOT NULL,
    Description nvarchar(max) NOT NULL,
    SatisfactionScore tinyint NULL,
    RowVersion rowversion NOT NULL,
    CONSTRAINT CK_SupportTicket_Priority CHECK (PriorityCode IN ('P1', 'P2', 'P3', 'P4')),
    CONSTRAINT CK_SupportTicket_Status CHECK (TicketStatus IN ('OPEN', 'PENDING', 'RESOLVED', 'CLOSED')),
    CONSTRAINT CK_SupportTicket_Dates CHECK (ClosedAtUtc IS NULL OR ClosedAtUtc >= CreatedAtUtc),
    CONSTRAINT CK_SupportTicket_Satisfaction CHECK (SatisfactionScore IS NULL OR SatisfactionScore BETWEEN 1 AND 5),
    CONSTRAINT FK_SupportTicket_Customer FOREIGN KEY (CustomerId)
        REFERENCES sales.Customer(CustomerId),
    CONSTRAINT FK_SupportTicket_SalesOrder FOREIGN KEY (SalesOrderId)
        REFERENCES sales.SalesOrder(SalesOrderId)
);

CREATE TABLE support.TicketEvent
(
    TicketEventId bigint NOT NULL
        CONSTRAINT DF_TicketEvent_TicketEventId DEFAULT (NEXT VALUE FOR support.SeqTicketEventId)
        CONSTRAINT PK_TicketEvent PRIMARY KEY,
    SupportTicketId bigint NOT NULL,
    EventAtUtc datetime2(3) NOT NULL,
    EventType varchar(20) NOT NULL,
    ActorType varchar(20) NOT NULL,
    EventDetails nvarchar(max) NOT NULL,
    CONSTRAINT CK_TicketEvent_EventType CHECK (EventType IN ('CREATED', 'COMMENT', 'STATUS_CHANGE', 'ASSIGNMENT')),
    CONSTRAINT CK_TicketEvent_ActorType CHECK (ActorType IN ('CUSTOMER', 'AGENT', 'SYSTEM')),
    CONSTRAINT FK_TicketEvent_SupportTicket FOREIGN KEY (SupportTicketId)
        REFERENCES support.SupportTicket(SupportTicketId)
);
GO

CREATE INDEX IX_Product_ProductCategoryId
    ON catalog.Product(ProductCategoryId)
    INCLUDE (ProductName, UnitPrice, IsActive);

CREATE INDEX IX_Customer_RegionCode
    ON sales.Customer(RegionCode)
    INCLUDE (CustomerStatus, SignupDate);

CREATE INDEX IX_SalesOrder_CustomerId_OrderDateUtc
    ON sales.SalesOrder(CustomerId, OrderDateUtc DESC)
    INCLUDE (OrderStatusCode, TotalAmount, SalesChannel);

CREATE INDEX IX_SalesOrder_OrderDateUtc
    ON sales.SalesOrder(OrderDateUtc)
    INCLUDE (CustomerId, OrderStatusCode, TotalAmount);

CREATE INDEX IX_SalesOrderLine_SalesOrderId
    ON sales.SalesOrderLine(SalesOrderId)
    INCLUDE (ProductId, Quantity, UnitPrice, DiscountAmount, TaxAmount);

CREATE INDEX IX_Payment_SalesOrderId
    ON sales.Payment(SalesOrderId)
    INCLUDE (PaymentStatus, Amount, ProcessedAtUtc);

CREATE INDEX IX_StockMovement_ProductId_OccurredAtUtc
    ON inventory.StockMovement(ProductId, OccurredAtUtc DESC)
    INCLUDE (WarehouseId, MovementType, QuantityChange);

CREATE INDEX IX_TicketEvent_SupportTicketId_EventAtUtc
    ON support.TicketEvent(SupportTicketId, EventAtUtc)
    INCLUDE (EventType, ActorType);
GO

INSERT lab.BuildInfo (BuildInfoId, SchemaVersion)
VALUES (1, '1.0.0');
GO
