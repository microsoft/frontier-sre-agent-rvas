// MIT License

using Microsoft.Data.SqlClient;

namespace Alyio.McpMssql.Configuration;

/// <summary>
/// Validates and normalizes Azure SQL managed identity connection strings.
/// </summary>
internal static class AzureManagedIdentityConnectionPolicy
{
    private const int MaximumConnectTimeoutSeconds = 30;

    /// <summary>
    /// Validates a connection string for the hardened Azure SQL deployment.
    /// </summary>
    /// <param name="connectionString">The connection string to validate.</param>
    /// <param name="profileName">The profile name used in error messages.</param>
    /// <returns>A normalized, encrypted, read-only connection string.</returns>
    /// <exception cref="InvalidOperationException">
    /// Thrown when the connection string does not use a user-assigned managed
    /// identity or omits an explicit database.
    /// </exception>
    public static string ValidateAndNormalize(string connectionString, string profileName)
    {
        SqlConnectionStringBuilder builder;

        try
        {
            builder = new SqlConnectionStringBuilder(connectionString);
        }
        catch (ArgumentException ex)
        {
            throw new InvalidOperationException(
                $"Profile '{profileName}' has an invalid SQL connection string.",
                ex);
        }

        if (builder.Authentication != SqlAuthenticationMethod.ActiveDirectoryManagedIdentity)
        {
            throw new InvalidOperationException(
                $"Profile '{profileName}' must use Active Directory Managed Identity authentication.");
        }

        if (!Guid.TryParse(builder.UserID, out _))
        {
            throw new InvalidOperationException(
                $"Profile '{profileName}' must set User ID to the user-assigned managed identity client ID.");
        }

        if (string.IsNullOrWhiteSpace(builder.InitialCatalog))
        {
            throw new InvalidOperationException(
                $"Profile '{profileName}' must specify an explicit database.");
        }

        if (string.IsNullOrWhiteSpace(builder.DataSource))
        {
            throw new InvalidOperationException(
                $"Profile '{profileName}' must specify a SQL Server endpoint.");
        }

        if (!string.IsNullOrEmpty(builder.Password)
            || builder.IntegratedSecurity)
        {
            throw new InvalidOperationException(
                $"Profile '{profileName}' cannot contain a password or integrated security.");
        }

        builder["Encrypt"] = "True";
        builder.TrustServerCertificate = false;
        builder.PersistSecurityInfo = false;
        builder.ApplicationIntent = ApplicationIntent.ReadOnly;
        builder.ConnectTimeout = Math.Clamp(
            builder.ConnectTimeout,
            1,
            MaximumConnectTimeoutSeconds);

        builder.ApplicationName = "AzureSRE-SqlDba";

        return builder.ConnectionString;
    }
}
