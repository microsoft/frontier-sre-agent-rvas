// MIT License

using System.ComponentModel;

namespace Alyio.McpMssql.Models;

/// <summary>
/// Summary information for a single MCP MSSQL profile.
/// </summary>
public sealed class Profile
{
    /// <summary>
    /// Profile name (e.g. default, warehouse).
    /// </summary>
    public required string Name { get; init; }

    /// <summary>
    /// Optional human- or agent-facing description.
    /// </summary>
    public string? Description { get; init; }

    /// <summary>
    /// Whether this profile permits write commands (DDL/DML) via run_command.
    /// </summary>
    /// <remarks>
    /// The write tool is only advertised when some profile sets this, so this
    /// flag is how an agent finds a writable profile in a multi-profile setup.
    /// </remarks>
    [Description("Whether run_command is permitted on this profile.")]
    public bool AllowWrite { get; init; }
}
