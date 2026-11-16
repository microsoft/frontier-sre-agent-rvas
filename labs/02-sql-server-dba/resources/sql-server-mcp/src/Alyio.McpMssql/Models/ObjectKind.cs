// MIT License

using System.Text.Json.Serialization;

namespace Alyio.McpMssql.Models;

/// <summary>
/// Scope for get_object: relation (tables/views) or routine (procedures/functions).
/// </summary>
[JsonConverter(typeof(JsonStringEnumConverter))]
public enum ObjectKind
{
    /// <summary>A relation: table or view.</summary>
    Relation,

    /// <summary>A routine: procedure or function.</summary>
    Routine,
}
