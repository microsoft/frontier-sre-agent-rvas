// MIT License

using Alyio.McpMssql.Models;

#pragma warning disable IDE0130 // Namespace does not match folder structure
namespace Alyio.McpMssql;
#pragma warning restore IDE0130 // Namespace does not match folder structure

/// <summary>
/// Provides read-only access to SQL Server catalog metadata.
///
/// Describes a single tabular relation (table or view) or routine
/// (procedure or function); discovery of names is left to queries.
/// </summary>
public interface ICatalogService
{
    /// <summary>
    /// Describes the column-level structure of a tabular relation.
    /// </summary>
    /// <param name="name">
    /// Name of the relation (table or view).
    /// </param>
    /// <param name="catalog">
    /// Optional catalog (database) name. If omitted, uses the active catalog.
    /// </param>
    /// <param name="schema">
    /// Optional schema name. If omitted, uses default schema resolution.
    /// </param>
    /// <param name="profile">
    /// Optional profile name. If null or empty, the default profile is used.
    /// </param>
    /// <param name="cancellationToken">
    /// Token used to cancel the operation.
    /// </param>
    /// <returns>
    /// A read-only list of column metadata describing the relation structure.
    /// </returns>
    Task<TabularResult> DescribeColumnsAsync(
        string name,
        string? catalog = null,
        string? schema = null,
        string? profile = null,
        CancellationToken cancellationToken = default);

    /// <summary>
    /// Describes the indexes of a tabular relation (table or view).
    /// </summary>
    /// <param name="name">
    /// Name of the relation (table or view).
    /// </param>
    /// <param name="catalog">
    /// Optional catalog (database) name. If omitted, uses the active catalog.
    /// </param>
    /// <param name="schema">
    /// Optional schema name. If omitted, uses default schema resolution.
    /// </param>
    /// <param name="profile">
    /// Optional profile name. If null or empty, the default profile is used.
    /// </param>
    /// <param name="cancellationToken">
    /// Token used to cancel the operation.
    /// </param>
    /// <returns>
    /// A read-only list of index metadata (one row per index column).
    /// </returns>
    Task<TabularResult> DescribeIndexesAsync(
        string name,
        string? catalog = null,
        string? schema = null,
        string? profile = null,
        CancellationToken cancellationToken = default);

    /// <summary>
    /// Describes the constraints of a table (PK, UQ, FK, CHECK, DEFAULT). Tables only; views are not supported.
    /// </summary>
    /// <param name="name">Name of the table.</param>
    /// <param name="catalog">Optional catalog (database) name. If omitted, uses the active catalog.</param>
    /// <param name="schema">Optional schema name. If omitted, uses default schema resolution.</param>
    /// <param name="profile">Optional profile name. If null or empty, the default profile is used.</param>
    /// <param name="cancellationToken">Token used to cancel the operation.</param>
    /// <returns>The five constraint result sets.</returns>
    Task<TableConstraints> DescribeConstraintsAsync(
        string name,
        string? catalog = null,
        string? schema = null,
        string? profile = null,
        CancellationToken cancellationToken = default);

    /// <summary>
    /// Gets the T-SQL definition of a routine (procedure or function). Tabular result with one column "definition"; one row when found, zero rows when not found.
    /// </summary>
    Task<TabularResult> GetRoutineDefinitionAsync(
        string name,
        string? catalog = null,
        string? schema = null,
        string? profile = null,
        CancellationToken cancellationToken = default);
    /// <summary>
    /// Describes the foreign keys of a table in both directions: those it
    /// declares (outgoing) and those declared against it (incoming).
    /// </summary>
    /// <param name="name">Name of the table.</param>
    /// <param name="catalog">Optional catalog (database) name. If omitted, uses the active catalog.</param>
    /// <param name="schema">Optional schema name. If omitted, uses default schema resolution.</param>
    /// <param name="profile">Optional profile name. If null or empty, the default profile is used.</param>
    /// <param name="cancellationToken">Token used to cancel the operation.</param>
    /// <returns>One row per foreign key column, with a direction discriminator.</returns>
    Task<TabularResult> DescribeRelationshipsAsync(
        string name,
        string? catalog = null,
        string? schema = null,
        string? profile = null,
        CancellationToken cancellationToken = default);

    /// <summary>
    /// Gets the approximate row count of a table from partition statistics.
    /// Returns null for views, for objects that do not exist, and when the
    /// caller lacks VIEW DATABASE STATE.
    /// </summary>
    /// <param name="name">Name of the table.</param>
    /// <param name="catalog">Optional catalog (database) name. If omitted, uses the active catalog.</param>
    /// <param name="schema">Optional schema name. If omitted, uses default schema resolution.</param>
    /// <param name="profile">Optional profile name. If null or empty, the default profile is used.</param>
    /// <param name="cancellationToken">Token used to cancel the operation.</param>
    /// <returns>The approximate row count, or null when unavailable.</returns>
    Task<long?> GetRowCountAsync(
        string name,
        string? catalog = null,
        string? schema = null,
        string? profile = null,
        CancellationToken cancellationToken = default);
}
