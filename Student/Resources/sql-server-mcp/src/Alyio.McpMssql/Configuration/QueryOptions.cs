// MIT License

namespace Alyio.McpMssql.Configuration;

/// <summary>
/// Server-enforced execution defaults and safety limits
/// for interactive read-only queries.
/// </summary>
public sealed class QueryOptions
{
    /// <summary>
    /// Maximum number of rows that may be returned for a single interactive query.
    /// Clamped to <see cref="HardRowLimit"/>.
    /// </summary>
    public int MaxRows { get; set; } = 250;

    /// <summary>
    /// Maximum execution time for an interactive query command, in seconds.
    /// Clamped to <see cref="HardCommandTimeoutSeconds"/>.
    /// </summary>
    public int CommandTimeoutSeconds { get; set; } = 30;

    /// <summary>
    /// Maximum UTF-8 response size for an interactive query.
    /// Clamped to <see cref="HardMaxOutputBytes"/>.
    /// </summary>
    public int MaxOutputBytes { get; set; } = 256 * 1024;

    // -------------------------
    // Hard safety invariants
    // -------------------------

    /// <summary>
    /// Absolute, non-configurable hard limit for interactive query row counts.
    /// </summary>
    internal const int HardRowLimit = 1_000;

    /// <summary>
    /// Absolute, non-configurable hard limit for interactive query execution time.
    /// </summary>
    internal const int HardCommandTimeoutSeconds = 120;

    /// <summary>
    /// Absolute, non-configurable hard limit for UTF-8 query output.
    /// </summary>
    internal const int HardMaxOutputBytes = 1024 * 1024;
}
