// MIT License

using Alyio.McpMssql.Models;
using Alyio.McpMssql.Services.Scripts;
using Microsoft.Data.SqlClient;

namespace Alyio.McpMssql.Services;

internal sealed class CatalogService(IProfileService profileService) : ICatalogService
{
    public async Task<TabularResult> DescribeColumnsAsync(
        string name,
        string? catalog = null,
        string? schema = null,
        string? profile = null,
        CancellationToken cancellationToken = default)
    {
        var resolved = profileService.Resolve(profile);
        var sql = await Loader.ReadText("columns.sql", cancellationToken).ConfigureAwait(false);

        using var conn = new SqlConnection(resolved.ConnectionString);
        await conn.OpenAsync(cancellationToken).ConfigureAwait(false);

        if (!string.IsNullOrWhiteSpace(catalog))
        {
            conn.ChangeDatabase(catalog);
        }

        var parameters = new[]
        {
            new SqlParameter("@name", name),
            new SqlParameter("@schema", schema ?? (object)DBNull.Value)
        };

        return await conn.ExecuteAsTabularResultAsync(sql, parameters, cancellationToken)
            .ConfigureAwait(false);
    }

    public async Task<TabularResult> DescribeIndexesAsync(
        string name,
        string? catalog = null,
        string? schema = null,
        string? profile = null,
        CancellationToken cancellationToken = default)
    {
        var resolved = profileService.Resolve(profile);
        var sql = await Loader.ReadText("indexes.sql", cancellationToken).ConfigureAwait(false);

        using var conn = new SqlConnection(resolved.ConnectionString);
        await conn.OpenAsync(cancellationToken).ConfigureAwait(false);

        if (!string.IsNullOrWhiteSpace(catalog))
        {
            conn.ChangeDatabase(catalog);
        }

        var parameters = new[]
        {
            new SqlParameter("@table", name),
            new SqlParameter("@schema", schema ?? (object)DBNull.Value)
        };

        return await conn.ExecuteAsTabularResultAsync(sql, parameters, cancellationToken)
            .ConfigureAwait(false);
    }

    public async Task<TableConstraints> DescribeConstraintsAsync(
        string name,
        string? catalog = null,
        string? schema = null,
        string? profile = null,
        CancellationToken cancellationToken = default)
    {
        var resolved = profileService.Resolve(profile);
        var sql = await Loader.ReadText("constraints.sql", cancellationToken).ConfigureAwait(false);

        using var conn = new SqlConnection(resolved.ConnectionString);
        await conn.OpenAsync(cancellationToken).ConfigureAwait(false);

        if (!string.IsNullOrWhiteSpace(catalog))
        {
            conn.ChangeDatabase(catalog);
        }

        var parameters = new[]
        {
            new SqlParameter("@table", name),
            new SqlParameter("@schema", schema ?? (object)DBNull.Value)
        };

        var results = await conn.ExecuteMultipleTabularResultsAsync(sql, parameters, cancellationToken)
            .ConfigureAwait(false);

        if (results.Count != 5)
        {
            throw new InvalidOperationException(
                $"Describe constraints script must return exactly 5 result sets; got {results.Count}.");
        }

        return new TableConstraints
        {
            PrimaryKeys = results[0],
            UniqueConstraints = results[1],
            ForeignKeys = results[2],
            CheckConstraints = results[3],
            DefaultConstraints = results[4]
        };
    }

    public async Task<TabularResult> GetRoutineDefinitionAsync(
        string name,
        string? catalog = null,
        string? schema = null,
        string? profile = null,
        CancellationToken cancellationToken = default)
    {
        var resolved = profileService.Resolve(profile);
        var sql = await Loader.ReadText("routine_definition.sql", cancellationToken).ConfigureAwait(false);

        using var conn = new SqlConnection(resolved.ConnectionString);
        await conn.OpenAsync(cancellationToken).ConfigureAwait(false);

        if (!string.IsNullOrWhiteSpace(catalog))
        {
            conn.ChangeDatabase(catalog);
        }

        var parameters = new[]
        {
            new SqlParameter("@schema", schema ?? (object)DBNull.Value),
            new SqlParameter("@name", name)
        };

        var result = await conn.ExecuteAsTabularResultAsync(sql, parameters, cancellationToken)
            .ConfigureAwait(false);

        if (result.Rows.Count == 0 || result.Columns.Count == 0)
        {
            return new TabularResult
            {
                Columns = ["definition"],
                Rows = []
            };
        }

        var definition = result.Rows[0][0];
        return new TabularResult
        {
            Columns = ["definition"],
            Rows = [[definition]],
        };
    }
    public async Task<TabularResult> DescribeRelationshipsAsync(
        string name,
        string? catalog = null,
        string? schema = null,
        string? profile = null,
        CancellationToken cancellationToken = default)
    {
        var resolved = profileService.Resolve(profile);
        var sql = await Loader.ReadText("relationships.sql", cancellationToken).ConfigureAwait(false);

        using var conn = new SqlConnection(resolved.ConnectionString);
        await conn.OpenAsync(cancellationToken).ConfigureAwait(false);

        if (!string.IsNullOrWhiteSpace(catalog))
        {
            conn.ChangeDatabase(catalog);
        }

        var parameters = new[]
        {
            new SqlParameter("@table", name),
            new SqlParameter("@schema", schema ?? (object)DBNull.Value)
        };

        return await conn.ExecuteAsTabularResultAsync(sql, parameters, cancellationToken)
            .ConfigureAwait(false);
    }

    public async Task<long?> GetRowCountAsync(
        string name,
        string? catalog = null,
        string? schema = null,
        string? profile = null,
        CancellationToken cancellationToken = default)
    {
        var resolved = profileService.Resolve(profile);
        var sql = await Loader.ReadText("row_count.sql", cancellationToken).ConfigureAwait(false);

        using var conn = new SqlConnection(resolved.ConnectionString);
        await conn.OpenAsync(cancellationToken).ConfigureAwait(false);

        if (!string.IsNullOrWhiteSpace(catalog))
        {
            conn.ChangeDatabase(catalog);
        }

        var parameters = new[]
        {
            new SqlParameter("@table", name),
            new SqlParameter("@schema", schema ?? (object)DBNull.Value)
        };

        // A caller that cannot see the table gets no row from sys.partitions
        // rather than a permission error, so the null degrades on its own.
        var result = await conn.ExecuteAsTabularResultAsync(sql, parameters, cancellationToken)
            .ConfigureAwait(false);

        if (result.Rows.Count == 0)
        {
            return null;
        }

        return result.Rows[0][0] switch
        {
            long l => l,
            int i => i,
            decimal d => (long)d,
            _ => null,
        };
    }
}
