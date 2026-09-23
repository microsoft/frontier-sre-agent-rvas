// MIT License

using Alyio.McpMssql.Tests.Infrastructure.Fixtures;
using ModelContextProtocol.Client;

namespace Alyio.McpMssql.Tests.E2E;

public class SnapshotE2ETests(McpServerFixture fixture) : IClassFixture<McpServerFixture>
{
    private const string RunQueryTool = "run_query";
    private readonly McpClient _client = fixture.Client;
    private static CancellationToken CancellationToken => TestContext.Current.CancellationToken;

    [Fact]
    public async Task RunQuery_Snapshot_Argument_Is_Rejected()
    {
        var result = await _client.CallToolAsync(
            RunQueryTool,
            new Dictionary<string, object?> { ["sql"] = "SELECT 1 AS Value", ["snapshot"] = true },
            cancellationToken: CancellationToken);

        Assert.True(result.IsError);
    }

    [Fact]
    public async Task Snapshot_Unknown_Id_Throws()
    {
        var ex = await Assert.ThrowsAnyAsync<Exception>(async () =>
            await _client.ReadResourceAsync("mssql://snapshots/nonexistent", cancellationToken: CancellationToken));

        Assert.Contains("not found", ex.Message, StringComparison.OrdinalIgnoreCase);
    }
}
