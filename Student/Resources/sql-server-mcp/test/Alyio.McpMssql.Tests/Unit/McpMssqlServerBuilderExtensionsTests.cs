// MIT License

using Alyio.McpMssql.Features;
using Alyio.McpMssql.Internal;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Options;
using ModelContextProtocol.Server;

namespace Alyio.McpMssql.Tests.Unit;

public sealed class McpMssqlServerBuilderExtensionsTests
{
    private static readonly string[] s_readOnlyToolNames =
    [
        "list_profiles",
        "get_object",
        "run_query",
        "analyze_query",
    ];

    [Fact]
    public void WithMcpMssqlTools_Hides_Write_Tool_When_No_Profile_Allows_Write()
    {
        List<string> tools = RegisteredToolNames(
            ("MCPMSSQL_CONNECTION_STRING", "Server=.;Database=DefaultDb;"));

        // The literal pins the wire contract; the gate's own constant is asserted
        // against it below, so a rename of either side fails a test.
        Assert.DoesNotContain("run_command", tools);
        Assert.DoesNotContain(WriteTools.ToolName, tools);
    }

    [Fact]
    public void WithMcpMssqlTools_Hides_Write_Tool_When_The_Default_Profile_Allows_Write()
    {
        List<string> tools = RegisteredToolNames(
            ("MCPMSSQL_CONNECTION_STRING", "Server=.;Database=DefaultDb;"),
            ("MCPMSSQL_ALLOW_WRITE", "true"));

        Assert.DoesNotContain(WriteTools.ToolName, tools);
    }

    [Fact]
    public void WithMcpMssqlTools_Hides_Write_Tool_When_Any_Named_Profile_Allows_Write()
    {
        List<string> tools = RegisteredToolNames(
            ("McpMssql:Profiles:default:ConnectionString", "Server=.;Database=DefaultDb;"),
            ("McpMssql:Profiles:writer:ConnectionString", "Server=.;Database=WriterDb;"),
            ("McpMssql:Profiles:writer:AllowWrite", "true"));

        Assert.DoesNotContain(WriteTools.ToolName, tools);
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public void WithMcpMssqlTools_Always_Advertises_The_Read_Only_Tools(bool allowWrite)
    {
        List<string> tools = RegisteredToolNames(
            ("MCPMSSQL_CONNECTION_STRING", "Server=.;Database=DefaultDb;"),
            ("MCPMSSQL_ALLOW_WRITE", allowWrite ? "true" : "false"));

        foreach (var name in s_readOnlyToolNames)
        {
            Assert.Contains(name, tools);
        }
    }

    private static List<string> RegisteredToolNames(
        params (string Key, string? Value)[] configuration)
    {
        IConfiguration config = new ConfigurationBuilder()
            .AddInMemoryCollection(configuration.ToDictionary(kv => kv.Key, kv => kv.Value))
            .Build();

        var services = new ServiceCollection();
        services.AddMcpMssql(config);
        services.AddMcpServer().WithMcpMssqlTools(McpJsonDefaults.Options);

        using var provider = services.BuildServiceProvider();
        McpServerOptions options = provider.GetRequiredService<IOptions<McpServerOptions>>().Value;

        Assert.NotNull(options.ToolCollection);

        return options.ToolCollection.PrimitiveNames.ToList();
    }
}
