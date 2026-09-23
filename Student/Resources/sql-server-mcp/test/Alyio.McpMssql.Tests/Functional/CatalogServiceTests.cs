// MIT License

using Alyio.McpMssql.Features;
using Alyio.McpMssql.Models;
using Alyio.McpMssql.Tests.Infrastructure.Fixtures;
using Microsoft.Extensions.DependencyInjection;

namespace Alyio.McpMssql.Tests.Functional;

public sealed class CatalogServiceTests(SqlServerFixture fixture) : SqlServerFunctionalTest(fixture)
{
    private readonly ICatalogService _service = fixture.Services.GetRequiredService<ICatalogService>();
    private static CancellationToken CancellationToken => TestContext.Current.CancellationToken;

    // -----------------------------
    // Routine definition
    // -----------------------------

    [Fact]
    public async Task GetRoutineDefinition_Returns_NonEmpty_Definition_For_Existing_Routine()
    {
        var result = await _service.GetRoutineDefinitionAsync(
            name: "GetUserById",
            catalog: TestDatabaseName,
            schema: "dbo",
            cancellationToken: CancellationToken);

        result.Columns.AssertHasColumns("definition");
        Assert.Single(result.Rows);
        var definition = result.Rows[0][0]?.ToString();
        Assert.NotNull(definition);
        Assert.Contains("SELECT", definition, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public async Task GetRoutineDefinition_Returns_Empty_Rows_For_Nonexistent_Routine()
    {
        var result = await _service.GetRoutineDefinitionAsync(
            name: "NonExistentRoutine_XYZ",
            catalog: TestDatabaseName,
            schema: "dbo",
            cancellationToken: CancellationToken);

        result.Columns.AssertHasColumns("definition");
        Assert.Empty(result.Rows);
    }

    // -----------------------------
    // GetObject – combined includes
    // -----------------------------

    [Fact]
    public async Task GetObject_WithColumnsAndIndexes_Returns_Both_Sections()
    {
        var result = await ObjectTools.GetObjectAsync(
            _service,
            ObjectKind.Relation,
            "Orders",
            catalog: TestDatabaseName,
            schema: "dbo",
            includes: [ObjectInclude.Columns, ObjectInclude.Indexes],
            cancellationToken: CancellationToken);

        Assert.NotNull(result.Columns);
        Assert.NotEmpty(result.Columns.Rows);
        result.Columns.Columns.AssertHasColumns("name", "type", "is_nullable", "column_id");

        Assert.NotNull(result.Indexes);
        Assert.NotEmpty(result.Indexes.Rows);
        result.Indexes.Columns.AssertHasColumns(
            "index_name", "index_type", "is_unique", "is_disabled", "has_filter",
            "filter_definition", "key_ordinal", "is_descending", "column_name", "is_included_column");

        Assert.Null(result.Constraints);
        Assert.Null(result.Relationships);
        Assert.Null(result.Definition);

        // Always-on for relations, independent of includes.
        Assert.NotNull(result.RowCount);
    }

    // -----------------------------
    // Describe columns
    // -----------------------------

    [Fact]
    public async Task DescribeColumns_Returns_Users_Column_Metadata()
    {
        var result = await _service.DescribeColumnsAsync(
            name: "Users",
            catalog: TestDatabaseName,
            schema: "dbo",
            cancellationToken: CancellationToken);

        Assert.NotEmpty(result.Columns);
        Assert.NotEmpty(result.Rows);

        result.Columns.AssertHasColumns(
            "name",
            "type",
            "is_nullable",
            "column_id");

        var nameIndex =
            result.Columns
                  .Select((c, i) => (c, i))
                  .First(p => p.c.Equals("name", StringComparison.OrdinalIgnoreCase))
                  .i;

        var columnNames =
            result.Rows.Select(r => r[nameIndex]?.ToString()).ToList();

        Assert.Contains("UserId", columnNames);
        Assert.Contains("UserName", columnNames);
        Assert.Contains("Email", columnNames);
        Assert.Contains("CreatedDate", columnNames);
    }

    [Fact]
    public async Task DescribeColumns_Without_Catalog_Or_Schema_Uses_Default_Resolution()
    {
        var result = await _service.DescribeColumnsAsync("Users", cancellationToken: CancellationToken);

        Assert.NotEmpty(result.Rows);
    }

    // -----------------------------
    // Describe indexes
    // -----------------------------

    [Fact]
    public async Task DescribeIndexes_Returns_Orders_Index_Metadata()
    {
        var result = await _service.DescribeIndexesAsync(
            name: "Orders",
            catalog: TestDatabaseName,
            schema: "dbo",
            cancellationToken: CancellationToken);

        Assert.NotEmpty(result.Columns);
        Assert.NotEmpty(result.Rows);

        result.Columns.AssertHasColumns(
            "index_name",
            "index_type",
            "is_unique",
            "is_disabled",
            "has_filter",
            "filter_definition",
            "key_ordinal",
            "is_descending",
            "column_name",
            "is_included_column");

        var indexNameIndex = result.Columns
            .Select((c, i) => (c, i))
            .First(p => p.c.Equals("index_name", StringComparison.OrdinalIgnoreCase))
            .i;

        var indexNames = result.Rows.Select(r => r[indexNameIndex]?.ToString()).Distinct().ToList();

        // PK name is system-generated (e.g. PK__Orders__...); we assert on the named indexes we created
        Assert.Contains("IX_Orders_OrderDate", indexNames);
        Assert.Contains("IX_Orders_User_Date", indexNames);
        Assert.Contains("IX_Orders_OrderDate_Filtered", indexNames);
        Assert.True(indexNames.Count >= 4, "Orders should have at least 4 indexes (PK + 3 named).");
    }

    [Fact]
    public async Task DescribeIndexes_Without_Catalog_Or_Schema_Uses_Default_Resolution()
    {
        var result = await _service.DescribeIndexesAsync("Orders", cancellationToken: CancellationToken);

        Assert.NotEmpty(result.Rows);
    }

    // -----------------------------
    // Constraints
    // -----------------------------

    [Fact]
    public async Task DescribeConstraints_Returns_Orders_Constraint_Metadata()
    {
        var result = await _service.DescribeConstraintsAsync(
            name: "Orders",
            catalog: TestDatabaseName,
            schema: "dbo",
            cancellationToken: CancellationToken);

        Assert.NotNull(result.PrimaryKeys);
        Assert.NotNull(result.UniqueConstraints);
        Assert.NotNull(result.ForeignKeys);
        Assert.NotNull(result.CheckConstraints);
        Assert.NotNull(result.DefaultConstraints);

        result.PrimaryKeys.Columns.AssertHasColumns("constraint_name", "column_name", "column_ordinal");
        result.UniqueConstraints.Columns.AssertHasColumns("constraint_name", "column_name", "column_ordinal");
        result.ForeignKeys.Columns.AssertHasColumns(
            "constraint_name", "column_name", "column_ordinal",
            "referenced_schema", "referenced_table", "referenced_column",
            "on_delete", "on_update", "is_disabled", "is_not_trusted");
        result.CheckConstraints.Columns.AssertHasColumns(
            "constraint_name", "definition", "is_disabled", "is_not_trusted");
        result.DefaultConstraints.Columns.AssertHasColumns("constraint_name", "column_name", "definition");

        Assert.NotEmpty(result.PrimaryKeys.Rows);
        Assert.NotEmpty(result.ForeignKeys.Rows);
        Assert.NotEmpty(result.CheckConstraints.Rows);
        Assert.NotEmpty(result.DefaultConstraints.Rows);
    }
    // -----------------------------
    // Describe relationships
    // -----------------------------

    private static IEnumerable<string?> Column(Alyio.McpMssql.Models.TabularResult result, string column)
    {
        var index = result.Columns
            .Select((name, i) => (name, i))
            .First(c => string.Equals(c.name, column, StringComparison.OrdinalIgnoreCase)).i;

        return result.Rows.Select(r => r[index]?.ToString());
    }

    [Fact]
    public async Task DescribeRelationships_Orders_Returns_Outgoing_Edge_To_Users()
    {
        var result = await _service.DescribeRelationshipsAsync(
            "Orders",
            catalog: TestDatabaseName,
            schema: "dbo",
            cancellationToken: CancellationToken);

        result.Columns.AssertHasColumns(
            "direction", "fk_name", "parent_schema", "parent_table", "parent_column",
            "referenced_schema", "referenced_table", "referenced_column",
            "delete_action", "update_action");

        Assert.NotEmpty(result.Rows);
        Assert.Contains("outgoing", Column(result, "direction"));
        Assert.Contains("Users", Column(result, "referenced_table"));
        Assert.Contains("UserId", Column(result, "referenced_column"));
    }

    [Fact]
    public async Task DescribeRelationships_Users_Returns_Incoming_Edge_From_Orders()
    {
        var result = await _service.DescribeRelationshipsAsync(
            "Users",
            catalog: TestDatabaseName,
            schema: "dbo",
            cancellationToken: CancellationToken);

        Assert.NotEmpty(result.Rows);
        Assert.Contains("incoming", Column(result, "direction"));
        Assert.Contains("Orders", Column(result, "parent_table"));
    }

    [Fact]
    public async Task GetObject_Relationships_Include_Returns_Edges_For_Relation()
    {
        var result = await ObjectTools.GetObjectAsync(
            _service,
            ObjectKind.Relation,
            "Orders",
            catalog: TestDatabaseName,
            schema: "dbo",
            includes: [ObjectInclude.Relationships],
            cancellationToken: CancellationToken);

        Assert.NotNull(result.Relationships);
        Assert.NotEmpty(result.Relationships.Rows);
        Assert.Null(result.Columns);
    }

    // -----------------------------
    // Row count
    // -----------------------------

    [Fact]
    public async Task GetRowCount_Returns_Seeded_Count_For_Table()
    {
        var count = await _service.GetRowCountAsync(
            "Users",
            catalog: TestDatabaseName,
            schema: "dbo",
            cancellationToken: CancellationToken);

        Assert.NotNull(count);
        Assert.True(count > 0, $"Expected a positive row count, got {count}.");
    }

    [Fact]
    public async Task GetRowCount_Returns_Null_For_View()
    {
        var count = await _service.GetRowCountAsync(
            "ActiveUsers",
            catalog: TestDatabaseName,
            schema: "dbo",
            cancellationToken: CancellationToken);

        Assert.Null(count);
    }

    [Fact]
    public async Task GetObject_RowCount_Is_Null_For_Routine()
    {
        var result = await ObjectTools.GetObjectAsync(
            _service,
            ObjectKind.Routine,
            "GetUserCount",
            catalog: TestDatabaseName,
            schema: "dbo",
            includes: [ObjectInclude.Definition],
            cancellationToken: CancellationToken);

        Assert.NotNull(result.Definition);
        Assert.Null(result.RowCount);
    }

    // -----------------------------
    // Includes default and name resolution
    // -----------------------------

    [Fact]
    public async Task GetObject_Without_Includes_Defaults_To_Columns()
    {
        var result = await ObjectTools.GetObjectAsync(
            _service,
            ObjectKind.Relation,
            "Users",
            catalog: TestDatabaseName,
            schema: "dbo",
            cancellationToken: CancellationToken);

        Assert.NotNull(result.Columns);
        Assert.NotEmpty(result.Columns.Rows);
        Assert.Null(result.Indexes);
    }
}
