// MIT License

namespace Alyio.McpMssql.Internal;

/// <summary>
/// Parses object names supplied by MCP callers, which may arrive unqualified,
/// schema-qualified, or bracket-delimited (as emitted in execution plans).
/// </summary>
internal static class ObjectName
{
    /// <summary>
    /// Splits <paramref name="name"/> into schema and object parts, accepting
    /// <c>Users</c>, <c>dbo.Users</c>, <c>[dbo].[Users]</c> and <c>[Users]</c>.
    /// A schema embedded in the name is used only when <paramref name="schema"/>
    /// is not supplied; an explicit argument always wins.
    /// </summary>
    public static (string Name, string? Schema) Split(string name, string? schema)
    {
        var parts = SplitUnbracketed(name);

        // A three-part name (catalog.schema.object) keeps its trailing two parts;
        // the catalog is selected by the caller's catalog argument instead.
        var parsedName = Unbracket(parts[^1]);
        var parsedSchema = parts.Count > 1 ? Unbracket(parts[^2]) : null;

        return (
            parsedName,
            string.IsNullOrWhiteSpace(schema) ? NullIfEmpty(parsedSchema) : schema);
    }

    private static List<string> SplitUnbracketed(string value)
    {
        var parts = new List<string>();
        var start = 0;
        var depth = 0;

        for (var i = 0; i < value.Length; i++)
        {
            switch (value[i])
            {
                case '[':
                    depth++;
                    break;
                case ']':
                    if (depth > 0)
                    {
                        depth--;
                    }

                    break;
                case '.' when depth == 0:
                    parts.Add(value[start..i]);
                    start = i + 1;
                    break;
            }
        }

        parts.Add(value[start..]);
        return parts;
    }

    private static string Unbracket(string value)
    {
        var trimmed = value.Trim();

        if (trimmed.Length >= 2 && trimmed[0] == '[' && trimmed[^1] == ']')
        {
            // ]] is the escape for a literal ] inside a delimited identifier.
            return trimmed[1..^1].Replace("]]", "]", StringComparison.Ordinal);
        }

        return trimmed;
    }

    private static string? NullIfEmpty(string? value) =>
        string.IsNullOrWhiteSpace(value) ? null : value;
}
