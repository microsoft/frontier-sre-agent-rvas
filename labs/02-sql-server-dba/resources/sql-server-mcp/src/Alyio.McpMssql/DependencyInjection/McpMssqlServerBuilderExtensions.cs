// MIT License

using System.Text.Json;
using Alyio.McpMssql.Configuration;
using Alyio.McpMssql.Features;
using Microsoft.Extensions.Logging;
using ModelContextProtocol.Server;

#pragma warning disable IDE0130 // Intentional: extension methods for IMcpServerBuilder
namespace Microsoft.Extensions.DependencyInjection;
#pragma warning restore IDE0130

/// <summary>
/// MCP server builder helpers for the MCP SQL Server integration.
/// </summary>
public static partial class McpMssqlServerBuilderExtensions
{
    /// <summary>
    /// Registers the MCP MSSQL tools and permanently removes the write tool.
    /// </summary>
    /// <param name="builder">The MCP server builder to add the tools to.</param>
    /// <param name="serializerOptions">
    /// The JSON options used to marshal tool arguments and results.
    /// </param>
    /// <returns>The <paramref name="builder"/>, for chaining.</returns>
    public static IMcpServerBuilder WithMcpMssqlTools(
        this IMcpServerBuilder builder,
        JsonSerializerOptions? serializerOptions = null)
    {
        ArgumentNullException.ThrowIfNull(builder);

        builder.WithToolsFromAssembly(typeof(ServerTools).Assembly, serializerOptions);

        // The SDK copies the discovered tools into ToolCollection from an
        // IConfigureOptions<McpServerOptions>, and the options pattern runs every
        // Configure step before any PostConfigure one, so the collection is fully
        // populated here regardless of registration order.
        builder.Services
            .AddOptions<McpServerOptions>()
            .PostConfigure<ILoggerFactory>(RemoveWriteTool);

        return builder;
    }

    private static void RemoveWriteTool(
        McpServerOptions serverOptions,
        ILoggerFactory loggerFactory)
    {
        if (serverOptions.ToolCollection is not { } tools
            || !tools.TryGetPrimitive(WriteTools.ToolName, out McpServerTool? tool)
            || tool is null)
        {
            return;
        }

        if (tools.Remove(tool))
        {
            ILogger logger = loggerFactory.CreateLogger(typeof(McpMssqlServerBuilderExtensions));

            LogWriteToolRemoved(logger, WriteTools.ToolName);
        }
    }

    [LoggerMessage(
        Level = LogLevel.Information,
        Message = "Tool '{Tool}' is not advertised: this MCP server is permanently read-only.")]
    private static partial void LogWriteToolRemoved(ILogger logger, string tool);
}
