// MIT License

using Alyio.McpMssql.Configuration;
using Alyio.McpMssql.Models;
using Alyio.McpMssql.Services;
using Alyio.McpMssql.Tests.Infrastructure.Database;
using Alyio.McpMssql.Tests.Infrastructure.Fixtures;
using Microsoft.Data.SqlClient;
using Microsoft.Extensions.DependencyInjection;

namespace Alyio.McpMssql.Tests.Functional;

/// <summary>
/// Row counts must survive a db_datareader login. The permission a least-privilege
/// login lacks is granted implicitly to nobody, so the denial arrives as error 262
/// followed by 297 — a shape that reading only <see cref="SqlException.Number"/>
/// misses. Reading sys.partitions instead of sys.dm_db_partition_stats avoids the
/// permission altogether; these tests pin that down.
/// </summary>
public sealed class CatalogServiceLeastPrivilegeTests(SqlServerFixture fixture)
    : SqlServerFunctionalTest(fixture), IAsyncLifetime
{
    private const string Login = "mcp_mssql_readonly_test";
    private const string Password = "Re@donly#Test1";

    private static CancellationToken CancellationToken => TestContext.Current.CancellationToken;

    private string AdminConnectionString =>
        Fixture.Services.GetRequiredService<IProfileService>().Resolve().ConnectionString;

    private string ReadOnlyConnectionString
    {
        get
        {
            var builder = new SqlConnectionStringBuilder(AdminConnectionString)
            {
                UserID = Login,
                Password = Password,
                InitialCatalog = TestDatabaseName,
            };
            builder.Remove("Integrated Security");
            return builder.ConnectionString;
        }
    }

    public async ValueTask InitializeAsync()
    {
        await DropPrincipalsAsync();
        await DatabaseInitializer.ExecuteScriptAsync(
            AdminConnectionString,
            $"""
            CREATE LOGIN [{Login}] WITH PASSWORD = '{Password}', CHECK_POLICY = OFF;
            """,
            CancellationToken);
        await DatabaseInitializer.ExecuteScriptAsync(
            AdminConnectionString,
            $"""
            USE [{TestDatabaseName}];
            CREATE USER [{Login}] FOR LOGIN [{Login}];
            ALTER ROLE db_datareader ADD MEMBER [{Login}];
            """,
            CancellationToken);
    }

    public async ValueTask DisposeAsync() => await DropPrincipalsAsync();

    private async Task DropPrincipalsAsync()
    {
        // The read-only connections are pooled; a live session blocks DROP LOGIN.
        SqlConnection.ClearAllPools();
        await DatabaseInitializer.ExecuteScriptAsync(
            AdminConnectionString,
            $"""
            USE [{TestDatabaseName}];
            IF EXISTS (SELECT 1 FROM sys.database_principals WHERE name = '{Login}')
                DROP USER [{Login}];
            USE [master];
            IF EXISTS (SELECT 1 FROM sys.server_principals WHERE name = '{Login}')
                DROP LOGIN [{Login}];
            """,
            CancellationToken);
    }

    private CatalogService CreateReadOnlyCatalogService()
        => new(new StubProfileService(ReadOnlyConnectionString));

    [Fact]
    public async Task GetRowCount_Matches_Admin_Count_For_DbDatareader_Login()
    {
        var admin = Fixture.Services.GetRequiredService<ICatalogService>();

        var expected = await admin.GetRowCountAsync(
            "Users", catalog: TestDatabaseName, schema: "dbo", cancellationToken: CancellationToken);
        var actual = await CreateReadOnlyCatalogService().GetRowCountAsync(
            "Users", catalog: TestDatabaseName, schema: "dbo", cancellationToken: CancellationToken);

        Assert.NotNull(actual);
        Assert.Equal(expected, actual);
    }

    [Fact]
    public async Task GetObject_Carries_RowCount_For_DbDatareader_Login()
    {
        var result = await Features.ObjectTools.GetObjectAsync(
            CreateReadOnlyCatalogService(),
            ObjectKind.Relation,
            "Users",
            catalog: TestDatabaseName,
            schema: "dbo",
            includes: [ObjectInclude.Columns],
            cancellationToken: CancellationToken);

        Assert.NotNull(result.RowCount);
    }

    private sealed class StubProfileService(string connectionString) : IProfileService
    {
        public McpMssqlProfileOptions Resolve(string? profileName = null)
            => new() { ConnectionString = connectionString };

        public IReadOnlyList<Profile> GetProfiles()
            => [new Profile { Name = "default" }];
    }
}
