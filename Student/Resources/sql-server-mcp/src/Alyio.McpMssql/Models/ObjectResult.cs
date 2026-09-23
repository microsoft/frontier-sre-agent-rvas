// MIT License

using System.ComponentModel;

namespace Alyio.McpMssql.Models;

/// <summary>
/// Response shape for get_object (single object detail).
/// Identity plus optional detail parts (columns, indexes, constraints, relationships, definition) per include request.
/// </summary>
public sealed class ObjectResult
{
    /// <summary>Column metadata. Present when include requested columns.</summary>
    [Description("Null unless includes requested columns.")]
    public TabularResult? Columns { get; init; }

    /// <summary>Index metadata. Present when include requested indexes.</summary>
    [Description("Null unless includes requested indexes.")]
    public TabularResult? Indexes { get; init; }

    /// <summary>Table constraints (PK, UQ, FK, CHECK, DEFAULT). Present when include requested constraints; relation only.</summary>
    [Description("Null unless includes requested constraints; relations only.")]
    public TableConstraints? Constraints { get; init; }

    /// <summary>Foreign keys in both directions. Present when include requested relationships; relation only.</summary>
    [Description("Foreign keys both directions. Null unless includes requested relationships.")]
    public TabularResult? Relationships { get; init; }

    /// <summary>T-SQL routine body. Present when include requested definition; routine only.</summary>
    [Description("Null unless includes requested definition; routines only.")]
    public TabularResult? Definition { get; init; }

    /// <summary>
    /// Approximate row count for a relation; null for routines, views, and
    /// when the caller lacks VIEW DATABASE STATE.
    /// </summary>
    [Description("Approximate row count from partition stats, not COUNT(*). Null for routines and views.")]
    public long? RowCount { get; init; }
}
