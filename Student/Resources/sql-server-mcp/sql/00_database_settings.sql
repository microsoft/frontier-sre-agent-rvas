/*
    Purpose:
      Validate the target database and enable Query Store for the DBA SRE lab.

    Compatibility:
      SQL Server 2017+ and Azure SQL Database.

    Run this script while connected to the database that will host the lab.
    Do not run it in master.
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

DECLARE @ProductVersion nvarchar(128) = CONVERT(nvarchar(128), SERVERPROPERTY('ProductVersion'));
DECLARE @EngineEdition int = CONVERT(int, SERVERPROPERTY('EngineEdition'));
DECLARE @MajorVersion int = TRY_CONVERT(int, SERVERPROPERTY('ProductMajorVersion'));

IF @EngineEdition <> 5 AND ISNULL(@MajorVersion, 0) < 14
BEGIN
    THROW 50001, 'This lab requires SQL Server 2017 or later, or Azure SQL Database.', 1;
END;

ALTER DATABASE CURRENT SET QUERY_STORE = ON;
ALTER DATABASE CURRENT SET QUERY_STORE
(
    OPERATION_MODE = READ_WRITE,
    CLEANUP_POLICY = (STALE_QUERY_THRESHOLD_DAYS = 30),
    DATA_FLUSH_INTERVAL_SECONDS = 900,
    INTERVAL_LENGTH_MINUTES = 15,
    MAX_STORAGE_SIZE_MB = 512,
    SIZE_BASED_CLEANUP_MODE = AUTO,
    QUERY_CAPTURE_MODE = AUTO
);

SELECT
    DB_NAME() AS DatabaseName,
    @ProductVersion AS ProductVersion,
    @EngineEdition AS EngineEdition,
    actual_state_desc AS QueryStoreState,
    desired_state_desc AS QueryStoreDesiredState,
    current_storage_size_mb AS QueryStoreSizeMb,
    max_storage_size_mb AS QueryStoreMaxSizeMb
FROM sys.database_query_store_options;
GO
