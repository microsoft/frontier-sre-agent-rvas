// MIT License

using System.ComponentModel;
using Alyio.McpMssql.Models;
using ModelContextProtocol.Server;

namespace Alyio.McpMssql.Features;

/// <summary>
/// Tools for server metadata: list configured profiles.
/// </summary>
[McpServerToolType]
public static class ServerTools
{
    /// <summary>
    /// List configured profiles.
    /// </summary>
    [McpServerTool(UseStructuredContent = true, ReadOnly = true, OpenWorld = false)]
    [Description(
        "[MSSQL] List configured connection profiles.")]
    public static IReadOnlyList<Profile> ListProfiles(
        IProfileService profileService)
    {
        return profileService.GetProfiles();
    }
}
