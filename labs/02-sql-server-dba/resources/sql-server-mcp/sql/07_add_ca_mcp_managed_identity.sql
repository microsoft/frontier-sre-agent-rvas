/*
    Purpose:
      Map an Azure managed identity to a contained Microsoft Entra database user
      and add that user to the existing sre_dba_observer role.

    Run this script in the target user database from a Microsoft Entra
    administrative session. Do not run it in master.

    Before running:
      1. Replace @ManagedIdentityName with the managed identity display name.
      2. Leave @ManagedIdentityObjectId as NULL when the display name is unique.
      3. For a duplicate display name, use a unique database alias for
         @ManagedIdentityName and set @ManagedIdentityObjectId to the identity's
         Object (principal) ID. Do not use its client ID.
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

DECLARE @ManagedIdentityName sysname = N'<managed-identity-display-name>';
DECLARE @ManagedIdentityObjectId uniqueidentifier = NULL;

IF DB_NAME() = N'master'
BEGIN
    THROW 50060, 'Connect to the target user database before running this script.', 1;
END;

IF @ManagedIdentityName IS NULL
   OR @ManagedIdentityName = N''
   OR @ManagedIdentityName = N'<managed-identity-display-name>'
BEGIN
    THROW 50061, 'Set @ManagedIdentityName before running this script.', 1;
END;

IF DATABASE_PRINCIPAL_ID(N'sre_dba_observer') IS NULL
BEGIN
    THROW 50062, 'The sre_dba_observer role is missing. Run 05_observer_role.sql first.', 1;
END;

DECLARE @ExistingPrincipalId int = DATABASE_PRINCIPAL_ID(@ManagedIdentityName);
DECLARE @Sql nvarchar(max);

IF @ExistingPrincipalId IS NULL
BEGIN
    IF @ManagedIdentityObjectId IS NULL
    BEGIN
        SET @Sql =
            N'CREATE USER ' + QUOTENAME(@ManagedIdentityName)
            + N' FROM EXTERNAL PROVIDER;';
    END;
    ELSE
    BEGIN
        SET @Sql =
            N'CREATE USER ' + QUOTENAME(@ManagedIdentityName)
            + N' FROM EXTERNAL PROVIDER WITH OBJECT_ID = '''
            + CONVERT(nvarchar(36), @ManagedIdentityObjectId)
            + N''';';
    END;

    EXEC sys.sp_executesql @Sql;
    SET @ExistingPrincipalId = DATABASE_PRINCIPAL_ID(@ManagedIdentityName);
END;
ELSE IF NOT EXISTS
(
    SELECT 1
    FROM sys.database_principals
    WHERE principal_id = @ExistingPrincipalId
      AND type = 'E'
      AND authentication_type_desc = N'EXTERNAL'
)
BEGIN
    THROW 50063, 'A database principal with this name exists but is not a Microsoft Entra external user.', 1;
END;

IF NOT EXISTS
(
    SELECT 1
    FROM sys.database_role_members roleMember
    WHERE roleMember.role_principal_id = DATABASE_PRINCIPAL_ID(N'sre_dba_observer')
      AND roleMember.member_principal_id = @ExistingPrincipalId
)
BEGIN
    SET @Sql =
        N'ALTER ROLE sre_dba_observer ADD MEMBER '
        + QUOTENAME(@ManagedIdentityName)
        + N';';

    EXEC sys.sp_executesql @Sql;
END;

SELECT
    memberPrincipal.name AS DatabaseUserName,
    memberPrincipal.type_desc AS PrincipalType,
    memberPrincipal.authentication_type_desc AS AuthenticationType,
    rolePrincipal.name AS DatabaseRoleName,
    memberPrincipal.create_date AS UserCreatedAt,
    memberPrincipal.modify_date AS UserModifiedAt
FROM sys.database_role_members roleMember
INNER JOIN sys.database_principals rolePrincipal
    ON rolePrincipal.principal_id = roleMember.role_principal_id
INNER JOIN sys.database_principals memberPrincipal
    ON memberPrincipal.principal_id = roleMember.member_principal_id
WHERE rolePrincipal.name = N'sre_dba_observer'
  AND memberPrincipal.name = @ManagedIdentityName;

SELECT
    permissionState.state_desc AS PermissionState,
    permissionState.permission_name AS PermissionName,
    permissionState.class_desc AS PermissionScope
FROM sys.database_permissions permissionState
WHERE permissionState.grantee_principal_id =
    DATABASE_PRINCIPAL_ID(N'sre_dba_observer')
ORDER BY
    permissionState.state_desc,
    permissionState.permission_name;
GO
