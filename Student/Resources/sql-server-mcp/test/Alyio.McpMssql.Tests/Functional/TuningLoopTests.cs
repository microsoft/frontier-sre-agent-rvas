// MIT License

using System.Reflection;
using System.Xml.Linq;
using Alyio.McpMssql.Features;
using Alyio.McpMssql.Internal;
using Alyio.McpMssql.Models;
using Alyio.McpMssql.Tests.Infrastructure.Fixtures;
using Microsoft.Extensions.DependencyInjection;

namespace Alyio.McpMssql.Tests.Functional;

/// <summary>
/// analyze_query reports missing-index suggestions with bracket-qualified table
/// names ([schema].[table]); get_object must accept one verbatim so the two
/// tools compose without the caller reformatting anything in between.
/// </summary>
public sealed class TuningLoopTests(SqlServerFixture fixture) : SqlServerFunctionalTest(fixture)
{
    private readonly ICatalogService _catalog = fixture.Services.GetRequiredService<ICatalogService>();
    private static CancellationToken CancellationToken => TestContext.Current.CancellationToken;

    [Fact]
    public async Task MissingIndex_Table_Feeds_GetObject_Verbatim()
    {
        // A captured plan is used rather than a live analyze_query: the seeded
        // tables are far too small for the optimizer to suggest an index, so a
        // live plan would assert nothing.
        var suggestion = (await ParseCapturedPlanAsync()).MissingIndexes[0];

        Assert.Equal("[dbo].[Users]", suggestion.Table);

        var result = await ObjectTools.GetObjectAsync(
            _catalog,
            ObjectKind.Relation,
            suggestion.Table,
            catalog: TestDatabaseName,
            includes: [ObjectInclude.Indexes],
            cancellationToken: CancellationToken);

        Assert.NotNull(result.Indexes);
        Assert.NotEmpty(result.Indexes.Rows);
        Assert.NotNull(result.RowCount);
    }

    private static async Task<AnalyzeResult> ParseCapturedPlanAsync()
    {
        var stream = Assembly.GetAssembly(typeof(TuningLoopTests))!
            .GetManifestResourceStream("Alyio.McpMssql.Tests.Unit.Plans.complex_plan.xml")
            ?? throw new FileNotFoundException("Embedded plan fixture not found.");

        using var reader = new StreamReader(stream);
        var xml = await reader.ReadToEndAsync(CancellationToken);

        return PlanParser.Parse(XDocument.Parse(xml));
    }
}
