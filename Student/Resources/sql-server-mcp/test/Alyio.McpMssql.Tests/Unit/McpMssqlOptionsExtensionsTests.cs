// MIT License

using System.Globalization;
using Alyio.McpMssql.Configuration;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Options;

namespace Alyio.McpMssql.Tests.Unit;

public sealed class McpMssqlOptionsExtensionsTests
{
    [Theory]
    [InlineData("0", 1)]
    [InlineData("3600", AnalyzeOptions.HardCommandTimeoutSeconds)]
    public void AddMcpMssqlOptions_Clamps_Analyze_Timeout_To_Hard_Limits(
        string configuredTimeout,
        int expectedTimeout)
    {
        var values = new Dictionary<string, string?>
        {
            ["MCPMSSQL_CONNECTION_STRING"] =
                "Server=.;Database=DefaultDb;TrustServerCertificate=True;",
            ["MCPMSSQL_ANALYZE_COMMAND_TIMEOUT_SECONDS"] = configuredTimeout,
        };
        IConfiguration configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(values)
            .Build();
        var services = new ServiceCollection();
        services.AddMcpMssqlOptions(configuration);
        using var provider = services.BuildServiceProvider();

        var options = provider.GetRequiredService<IOptions<McpMssqlOptions>>().Value;

        Assert.Equal(
            expectedTimeout,
            options.Profiles[McpMssqlOptions.DefaultProfileName].Analyze.CommandTimeoutSeconds);
    }

    [Fact]
    public void AddMcpMssqlOptions_Logs_A_Warning_When_A_Value_Is_Clamped()
    {
        var records = Resolve(
            ("MCPMSSQL_QUERY_MAX_ROWS", "5000"),
            out var options);

        Assert.Equal(
            QueryOptions.HardRowLimit,
            options.Profiles[McpMssqlOptions.DefaultProfileName].Query.MaxRows);

        var warning = Assert.Single(records, r => r.Level == LogLevel.Warning);
        Assert.Contains("Query:MaxRows", warning.Message, StringComparison.Ordinal);
        Assert.Contains("5000", warning.Message, StringComparison.Ordinal);
        Assert.Contains(
            QueryOptions.HardRowLimit.ToString(CultureInfo.InvariantCulture),
            warning.Message,
            StringComparison.Ordinal);
    }

    [Fact]
    public void AddMcpMssqlOptions_Stays_Quiet_When_Every_Value_Is_In_Bounds()
    {
        var records = Resolve(
            ("MCPMSSQL_QUERY_MAX_ROWS", "500"),
            out _);

        Assert.DoesNotContain(records, r => r.Level == LogLevel.Warning);
    }

    [Fact]
    public void AddMcpMssqlOptions_Rejects_Write_Enabled_Profile()
    {
        var values = new Dictionary<string, string?>
        {
            ["MCPMSSQL_CONNECTION_STRING"] = "Server=.;Database=DefaultDb;",
            ["MCPMSSQL_ALLOW_WRITE"] = "true",
        };
        IConfiguration configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(values)
            .Build();
        var services = new ServiceCollection();
        services.AddMcpMssqlOptions(configuration);

        using var provider = services.BuildServiceProvider();

        var exception = Assert.Throws<InvalidOperationException>(
            () => provider.GetRequiredService<IOptions<McpMssqlOptions>>().Value);

        Assert.Contains("cannot enable AllowWrite", exception.Message, StringComparison.Ordinal);
    }

    private static List<LogRecord> Resolve(
        (string Key, string Value) setting,
        out McpMssqlOptions options)
    {
        var values = new Dictionary<string, string?>
        {
            ["MCPMSSQL_CONNECTION_STRING"] =
                "Server=.;Database=DefaultDb;TrustServerCertificate=True;",
            [setting.Key] = setting.Value,
        };
        IConfiguration configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(values)
            .Build();

        var provider = new CapturingLoggerProvider();
        var services = new ServiceCollection();
        services.AddMcpMssqlOptions(configuration);
        services.AddLogging(builder => builder.AddProvider(provider));

        using var serviceProvider = services.BuildServiceProvider();
        options = serviceProvider.GetRequiredService<IOptions<McpMssqlOptions>>().Value;

        return provider.Records;
    }

    private sealed record LogRecord(LogLevel Level, string Message);

    private sealed class CapturingLoggerProvider : ILoggerProvider
    {
        public List<LogRecord> Records { get; } = [];

        public ILogger CreateLogger(string categoryName) => new CapturingLogger(Records);

        public void Dispose()
        {
        }

        private sealed class CapturingLogger(List<LogRecord> records) : ILogger
        {
            public IDisposable? BeginScope<TState>(TState state)
                where TState : notnull => null;

            public bool IsEnabled(LogLevel logLevel) => true;

            public void Log<TState>(
                LogLevel logLevel,
                EventId eventId,
                TState state,
                Exception? exception,
                Func<TState, Exception?, string> formatter)
            {
                records.Add(new LogRecord(logLevel, formatter(state, exception)));
            }
        }
    }
}
