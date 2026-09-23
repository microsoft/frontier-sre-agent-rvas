/*
    Purpose:
      Create a least-privilege database role for a read-only DBA SRE observer.

    The script creates the role but does not create a user. Add a contained
    Microsoft Entra user, service principal, managed identity, or SQL user to
    the role after installation.
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
    THROW 50040, 'Run 01_schema.sql before this script.', 1;
END;

IF DATABASE_PRINCIPAL_ID(N'sre_dba_observer') IS NULL
BEGIN
    CREATE ROLE sre_dba_observer AUTHORIZATION dbo;
END;

GRANT CONNECT TO sre_dba_observer;
GRANT SELECT TO sre_dba_observer;
GRANT SHOWPLAN TO sre_dba_observer;
GRANT VIEW DEFINITION TO sre_dba_observer;

REVOKE CONTROL TO sre_dba_observer;
DENY INSERT, UPDATE, DELETE, EXECUTE TO sre_dba_observer;
DENY ALTER, TAKE OWNERSHIP TO sre_dba_observer;

DECLARE @EngineEdition int = CONVERT(int, SERVERPROPERTY('EngineEdition'));
DECLARE @MajorVersion int = TRY_CONVERT(int, SERVERPROPERTY('ProductMajorVersion'));

IF @EngineEdition = 5 OR @MajorVersion >= 16
BEGIN
    EXEC(N'GRANT VIEW DATABASE PERFORMANCE STATE TO sre_dba_observer;');
END;
ELSE
BEGIN
    GRANT VIEW DATABASE STATE TO sre_dba_observer;
END;

SELECT
    rolePrincipal.name AS RoleName,
    permissionState.state_desc AS PermissionState,
    permissionState.permission_name AS PermissionName,
    permissionState.class_desc AS PermissionScope
FROM sys.database_principals rolePrincipal
INNER JOIN sys.database_permissions permissionState
    ON permissionState.grantee_principal_id = rolePrincipal.principal_id
WHERE rolePrincipal.name = N'sre_dba_observer'
ORDER BY
    permissionState.state_desc,
    permissionState.permission_name;
GO
