// MIT License

using Alyio.McpMssql.Tests.Infrastructure.Fixtures;
using ModelContextProtocol.Client;

namespace Alyio.McpMssql.Tests.E2E;

public sealed class ObjectE2ETests(McpServerFixture fixture) : IClassFixture<McpServerFixture>
{
    private readonly McpClient _client = fixture.Client;
    private static CancellationToken CancellationToken => TestContext.Current.CancellationToken;

    private const string ObjectToolName = "get_object";
    private static readonly string[] s_includeColumns = ["columns"];
    private static readonly string[] s_includeIndexes = ["indexes"];
    private static readonly string[] s_includeConstraints = ["constraints"];
    private static readonly string[] s_includeDefinition = ["definition"];
    private static readonly string[] s_includeRelationships = ["relationships"];

    [Fact]
    public async Task DescribeColumns_Tool_Returns_Expected_Columns()
    {
        var result = await _client.CallToolAsync(
            ObjectToolName,
            new Dictionary<string, object?>
            {
                ["kind"] = "relation",
                ["catalog"] = "master",
                ["schema"] = "dbo",
                ["name"] = "sysobjects",
                ["includes"] = s_includeColumns
            },
            cancellationToken: CancellationToken);

        var root = result.ReadJsonRoot();
        var (columns, _) = root.ReadColumnRowsFrom("columns");

        columns.AssertHasColumns("name", "type", "is_nullable", "column_id");
    }

    [Fact]
    public async Task DescribeIndexes_Tool_Returns_Expected_Columns()
    {
        var result = await _client.CallToolAsync(
            ObjectToolName,
            new Dictionary<string, object?>
            {
                ["kind"] = "relation",
                ["catalog"] = "master",
                ["schema"] = "dbo",
                ["name"] = "sysobjects",
                ["includes"] = s_includeIndexes
            },
            cancellationToken: CancellationToken);

        var root = result.ReadJsonRoot();
        var (columns, _) = root.ReadColumnRowsFrom("indexes");

        columns.AssertHasColumns(
            "index_name", "index_type", "is_unique", "is_disabled", "has_filter",
            "filter_definition", "key_ordinal", "is_descending", "column_name", "is_included_column");
    }

    [Fact]
    public async Task DescribeConstraints_Tool_Returns_Expected_Structure()
    {
        var result = await _client.CallToolAsync(
            ObjectToolName,
            new Dictionary<string, object?>
            {
                ["kind"] = "relation",
                ["catalog"] = "master",
                ["schema"] = "dbo",
                ["name"] = "sysobjects",
                ["includes"] = s_includeConstraints
            },
            cancellationToken: CancellationToken);

        var root = result.ReadJsonRoot();

        Assert.True(root.TryGetProperty("constraints", out var constraints));
        Assert.True(constraints.TryGetProperty("primary_keys", out var pk));
        Assert.True(pk.TryGetProperty("columns", out _));
        Assert.True(pk.TryGetProperty("rows", out _));
        Assert.True(constraints.TryGetProperty("unique_constraints", out _));
        Assert.True(constraints.TryGetProperty("foreign_keys", out _));
        Assert.True(constraints.TryGetProperty("check_constraints", out _));
        Assert.True(constraints.TryGetProperty("default_constraints", out _));
    }

    [Fact]
    public async Task GetRoutineDefinition_Tool_Returns_Expected_Columns()
    {
        var result = await _client.CallToolAsync(
            ObjectToolName,
            new Dictionary<string, object?>
            {
                ["kind"] = "routine",
                ["catalog"] = "master",
                ["schema"] = "dbo",
                ["name"] = "sp_who",
                ["includes"] = s_includeDefinition
            },
            cancellationToken: CancellationToken);

        var root = result.ReadJsonRoot();
        var (columns, _) = root.ReadColumnRowsFrom("definition");

        columns.AssertHasColumns("definition");
    }
    [Fact]
    public async Task DescribeRelationships_Tool_Returns_Expected_Columns()
    {
        var result = await _client.CallToolAsync(
            ObjectToolName,
            new Dictionary<string, object?>
            {
                ["kind"] = "relation",
                ["catalog"] = "master",
                ["schema"] = "sys",
                ["name"] = "objects",
                ["includes"] = s_includeRelationships
            },
            cancellationToken: CancellationToken);

        var root = result.ReadJsonRoot();
        var (columns, _) = root.ReadColumnRowsFrom("relationships");

        columns.AssertHasColumns(
            "direction", "fk_name", "parent_schema", "parent_table", "parent_column",
            "referenced_schema", "referenced_table", "referenced_column",
            "delete_action", "update_action");
    }

    [Fact]
    public async Task GetObject_Without_Includes_Returns_Columns()
    {
        var result = await _client.CallToolAsync(
            ObjectToolName,
            new Dictionary<string, object?>
            {
                ["kind"] = "relation",
                ["catalog"] = "master",
                ["name"] = "[sys].[objects]"
            },
            cancellationToken: CancellationToken);

        var root = result.ReadJsonRoot();
        var (columns, _) = root.ReadColumnRowsFrom("columns");

        columns.AssertHasColumns("name", "type", "is_nullable", "column_id");
    }
}
