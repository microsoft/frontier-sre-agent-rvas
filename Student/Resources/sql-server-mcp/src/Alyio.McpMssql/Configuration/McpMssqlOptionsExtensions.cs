// MIT License

using Alyio.McpMssql.Configuration;
using Microsoft.Data.SqlClient;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging;

#pragma warning disable IDE0130 // Intentional: extension methods for IServiceCollection
namespace Microsoft.Extensions.DependencyInjection;
#pragma warning restore IDE0130

/// <summary>
/// Dependency injection helpers for the MCP SQL Server integration.
/// </summary>
public static partial class McpMssqlOptionsExtensions
{
    /// <summary>
    /// Registers and validates MCP MSSQL configuration options.
    ///
    /// Configuration is bound using standard .NET configuration behavior.
    /// MCP-specific flat environment variables are applied to the default
    /// profile only, preserving backward compatibility for single-profile
    /// configurations.
    /// </summary>
    public static IServiceCollection AddMcpMssqlOptions(this IServiceCollection services, IConfiguration configuration)
    {
        // The clamp warnings below need a logger, and this method is callable
        // on a bare collection, so guarantee one rather than require callers
        // to register logging first. AddLogging is idempotent.
        services.AddLogging();

        services
            .AddOptions<McpMssqlOptions>()
            .Bind(configuration.GetSection("McpMssql"))
            .PostConfigure<ILoggerFactory>((options, loggerFactory) =>
            {
                ILogger logger = loggerFactory.CreateLogger(typeof(McpMssqlOptionsExtensions));

                EnsureProfilesExist(options);
                DefaultProfileOverrideApplier.Apply(configuration, options);
                ValidateAndNormalize(options, logger);
            })
            .ValidateOnStart();

        return services;
    }

    // -------------------------
    // Configuration processing
    // -------------------------

    private static void EnsureProfilesExist(McpMssqlOptions options)
    {
        if (!options.Profiles.ContainsKey(McpMssqlOptions.DefaultProfileName))
        {
            options.Profiles[McpMssqlOptions.DefaultProfileName] = new McpMssqlProfileOptions();
        }
    }

    private static void ValidateAndNormalize(McpMssqlOptions options, ILogger logger)
    {
        foreach ((string name, McpMssqlProfileOptions profile) in options.Profiles)
        {
            if (string.IsNullOrWhiteSpace(profile.ConnectionString))
            {
                throw new InvalidOperationException(
                    $"ConnectionString is required for MCP MSSQL profile '{name}'.");
            }

            if (profile.AllowWrite)
            {
                throw new InvalidOperationException(
                    $"Profile '{name}' cannot enable AllowWrite in this read-only server.");
            }

            if (options.RequireAzureManagedIdentity)
            {
                profile.ConnectionString = AzureManagedIdentityConnectionPolicy
                    .ValidateAndNormalize(profile.ConnectionString, name);
            }

            ClampQueryOptions(profile.Query, logger, name);
            ClampAnalyzeOptions(profile.Analyze, logger, name);
        }
    }

    // -------------------------
    // Normalization helpers
    // -------------------------

    private static void ClampQueryOptions(QueryOptions query, ILogger logger, string profile)
    {
        query.MaxRows = Clamp(
            logger,
            profile,
            "Query:MaxRows",
            query.MaxRows,
            min: 1,
            max: QueryOptions.HardRowLimit);

        query.CommandTimeoutSeconds = Clamp(
            logger,
            profile,
            "Query:CommandTimeoutSeconds",
            query.CommandTimeoutSeconds,
            min: 1,
            max: QueryOptions.HardCommandTimeoutSeconds);

        query.MaxOutputBytes = Clamp(
            logger,
            profile,
            "Query:MaxOutputBytes",
            query.MaxOutputBytes,
            min: 1,
            max: QueryOptions.HardMaxOutputBytes);
    }

    private static void ClampAnalyzeOptions(AnalyzeOptions analyze, ILogger logger, string profile)
    {
        analyze.CommandTimeoutSeconds = Clamp(
            logger,
            profile,
            "Analyze:CommandTimeoutSeconds",
            analyze.CommandTimeoutSeconds,
            min: 1,
            max: AnalyzeOptions.HardCommandTimeoutSeconds);
    }

    /// <summary>
    /// Clamps a configured value to its hard bounds, reporting any adjustment.
    /// </summary>
    /// <remarks>
    /// The hard bounds are compile-time invariants, so a configured value
    /// outside them is silently ignored at runtime. Logging the adjustment is
    /// the only signal the operator gets that the effective value differs from
    /// what they wrote.
    /// </remarks>
    private static int Clamp(
        ILogger logger,
        string profile,
        string setting,
        int configured,
        int min,
        int max)
    {
        var effective = Math.Clamp(configured, min, max);

        if (effective != configured)
        {
            LogClamped(logger, setting, profile, configured, effective);
        }

        return effective;
    }

    [LoggerMessage(
        Level = LogLevel.Warning,
        Message = "Clamped {Setting} for MCP MSSQL profile '{Profile}': configured {Configured}, effective {Effective}.")]
    private static partial void LogClamped(
        ILogger logger,
        string setting,
        string profile,
        int configured,
        int effective);

}
