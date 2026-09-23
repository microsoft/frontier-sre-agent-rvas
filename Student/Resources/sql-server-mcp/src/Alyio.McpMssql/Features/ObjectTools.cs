// MIT License

using System.ComponentModel;
using Alyio.McpMssql.Internal;
using Alyio.McpMssql.Models;
using ModelContextProtocol;
using ModelContextProtocol.Server;

namespace Alyio.McpMssql.Features;

/// <summary>
/// Describe one catalog object (relation or routine).
/// </summary>
[McpServerToolType]
public static class ObjectTools
{
    private static readonly ObjectInclude[] s_defaultIncludes = [ObjectInclude.Columns];

    /// <summary>
    /// Get metadata for one relation or routine.
    /// </summary>
    [McpServerTool(UseStructuredContent = true, ReadOnly = true, OpenWorld = false)]
    [Description(
        "[MSSQL] Get metadata for one relation or routine.")]
    public static async Task<ObjectResult> GetObjectAsync(
        ICatalogService catalogService,
        [Description("relation | routine.")]
        ObjectKind kind,
        [Description("Users | dbo.Users | [dbo].[Users]. analyze_query missing_indexes[].table works as-is. Src: sys.objects.")]
        string name,
        [Description("If omitted or empty, uses the default profile. Src: profiles.")]
        string? profile = null,
        [Description("If omitted, uses the active catalog. Src: sys.databases.")]
        string? catalog = null,
        [Description("If omitted, taken from name when qualified, else default resolution. Src: sys.schemas.")]
        string? schema = null,
        [Description("Omit → columns. relations: columns, indexes, constraints, relationships; routines: definition.")]
        IReadOnlyList<ObjectInclude>? includes = null,
        CancellationToken cancellationToken = default)
    {
        if (kind is not ObjectKind.Relation and not ObjectKind.Routine)
        {
            throw new McpException("kind must be relation or routine for get_object.");
        }

        if (string.IsNullOrWhiteSpace(name))
        {
            throw new McpException("name is required.");
        }

        var (objectName, objectSchema) = ObjectName.Split(name, schema);
        var requested = includes is { Count: > 0 } ? includes : s_defaultIncludes;

        return await McpExecutor.RunAsync(async ct =>
        {
            var includeSet = requested.ToHashSet();
            TabularResult? columns = null;
            TabularResult? indexes = null;
            TableConstraints? constraints = null;
            TabularResult? relationships = null;
            TabularResult? definition = null;

            if (includeSet.Contains(ObjectInclude.Columns))
            {
                columns = await catalogService.DescribeColumnsAsync(objectName, catalog, objectSchema, profile, ct).ConfigureAwait(false);
            }

            if (includeSet.Contains(ObjectInclude.Indexes))
            {
                indexes = await catalogService.DescribeIndexesAsync(objectName, catalog, objectSchema, profile, ct).ConfigureAwait(false);
            }

            if (includeSet.Contains(ObjectInclude.Constraints) && kind == ObjectKind.Relation)
            {
                constraints = await catalogService.DescribeConstraintsAsync(objectName, catalog, objectSchema, profile, ct).ConfigureAwait(false);
            }

            if (includeSet.Contains(ObjectInclude.Relationships) && kind == ObjectKind.Relation)
            {
                relationships = await catalogService.DescribeRelationshipsAsync(objectName, catalog, objectSchema, profile, ct).ConfigureAwait(false);
            }

            if (includeSet.Contains(ObjectInclude.Definition) && kind == ObjectKind.Routine)
            {
                definition = await catalogService.GetRoutineDefinitionAsync(objectName, catalog, objectSchema, profile, ct).ConfigureAwait(false);
            }

            var rowCount = kind == ObjectKind.Relation
                ? await catalogService.GetRowCountAsync(objectName, catalog, objectSchema, profile, ct).ConfigureAwait(false)
                : null;

            return new ObjectResult
            {
                Columns = columns,
                Indexes = indexes,
                Constraints = constraints,
                Relationships = relationships,
                Definition = definition,
                RowCount = rowCount,
            };
        }, cancellationToken).ConfigureAwait(false);
    }
}
