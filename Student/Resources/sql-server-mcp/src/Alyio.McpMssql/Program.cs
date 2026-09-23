// MIT License

using Alyio.McpMssql.Internal;
using Alyio.McpMssql.Features;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Http;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;
using ModelContextProtocol.AspNetCore;

const string HttpTransport = "http";
const string StdioTransport = "stdio";

string transport = Environment.GetEnvironmentVariable("MCPMSSQL_TRANSPORT")?
    .Trim()
    .ToLowerInvariant() ?? StdioTransport;

if (transport == HttpTransport)
{
    await RunHttpAsync(args);
}
else if (transport == StdioTransport)
{
    await RunStdioAsync(args);
}
else
{
    throw new InvalidOperationException(
        $"Unsupported MCPMSSQL_TRANSPORT '{transport}'. Use '{StdioTransport}' or '{HttpTransport}'.");
}

static async Task RunHttpAsync(string[] args)
{
    var builder = WebApplication.CreateBuilder(args);
    ConfigureSources(builder.Configuration, builder.Environment, args);

    builder.Services
        .AddMcpMssql(builder.Configuration)
        .AddMcpServer()
        .WithHttpTransport()
        .WithMcpMssqlTools(McpJsonDefaults.Options)
        .WithResources<PlanResources>()
        .WithResources<ServerResources>();

    var app = builder.Build();

    app.MapGet(
        "/healthz",
        () => Results.Ok(new
        {
            service = "mcp-mssql",
            status = "healthy",
        }));
    app.MapMcp("/mcp");

    await app.RunAsync();
}

static async Task RunStdioAsync(string[] args)
{
    var builder = Host.CreateApplicationBuilder(args);
    ConfigureSources(builder.Configuration, builder.Environment, args);

    // MCP stdio uses stdout for protocol messages. Keep logs on stderr.
    builder.Logging.AddConsole(options =>
    {
        options.LogToStandardErrorThreshold = LogLevel.Trace;
    });

    builder.Services
        .AddMcpMssql(builder.Configuration)
        .AddMcpServer()
        .WithStdioServerTransport()
        .WithMcpMssqlTools(McpJsonDefaults.Options)
        .WithResources<PlanResources>()
        .WithResources<ServerResources>();

    await builder.Build().RunAsync();
}

static void ConfigureSources(
    ConfigurationManager configuration,
    IHostEnvironment environment,
    string[] args)
{
    string userConfigPath = Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.UserProfile),
        ".config",
        "mcp-mssql",
        "appsettings.json");

    configuration.Sources.Clear();
    configuration.AddJsonFile(userConfigPath, optional: true, reloadOnChange: false);

    if (environment.IsDevelopment())
    {
        configuration
            .AddJsonFile("appsettings.json", optional: true, reloadOnChange: false)
            .AddJsonFile(
                $"appsettings.{environment.EnvironmentName}.json",
                optional: true,
                reloadOnChange: false)
            .AddUserSecrets(
                System.Reflection.Assembly.GetExecutingAssembly(),
                optional: true,
                reloadOnChange: false);
    }

    configuration
        .AddEnvironmentVariables()
        .AddCommandLine(args);
}
