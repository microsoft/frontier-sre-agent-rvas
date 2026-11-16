// MIT License

using Alyio.McpMssql.Tests.Infrastructure.Fixtures;
using ModelContextProtocol.Client;

namespace Alyio.McpMssql.Tests.E2E;

/// <summary>
/// The resource URI template binds {id} straight from the request, and the SDK
/// percent-decodes after matching: a raw '/' fails to match the template, but
/// '%2F' matches and then decodes, so an encoded id can carry path separators
/// into the store.
/// </summary>
public class ResourceIdE2ETests(McpServerFixture fixture) : IClassFixture<McpServerFixture>
{
    private const string Secret = "TOP-SECRET-CONTENT";
    private readonly McpClient _client = fixture.Client;
    private static CancellationToken CancellationToken => TestContext.Current.CancellationToken;

    [Theory]
    [InlineData("mssql://plans", ".sqlplan.xml")]
    [InlineData("mssql://snapshots", ".snapshot.csv")]
    public async Task Resource_Does_Not_Return_A_File_Outside_The_Store(string uriPrefix, string extension)
    {
        var directory = Path.Combine(Path.GetTempPath(), Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(Path.Combine(directory, "sub"));
        await File.WriteAllTextAsync(
            Path.Combine(directory, $"leak{extension}"), Secret, CancellationToken);

        try
        {
            // Absolute, and traversing: Path.Combine discards the store directory
            // outright, and the '..' hop defeats a naive prefix check.
            var rawId = Path.Combine(directory, "sub", "..", "leak");
            Assert.True(
                File.Exists(rawId + extension),
                $"Planted file not reachable at '{rawId}{extension}'; the test proves nothing.");

            var ex = await Record.ExceptionAsync(async () => await _client.ReadResourceAsync(
                $"{uriPrefix}/{Uri.EscapeDataString(rawId)}", cancellationToken: CancellationToken));

            Assert.NotNull(ex);
            Assert.DoesNotContain(Secret, ex.Message, StringComparison.Ordinal);
        }
        finally
        {
            Directory.Delete(directory, recursive: true);
        }
    }
}
