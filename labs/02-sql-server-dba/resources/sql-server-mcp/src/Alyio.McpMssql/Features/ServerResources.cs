// MIT License

using System.ComponentModel;
using Alyio.McpMssql.Internal;
using ModelContextProtocol.Server;

namespace Alyio.McpMssql.Features;

/// <summary>
/// Resources for server metadata: list profiles (mssql://profiles). Mirrors the list_profiles tool.
/// </summary>
[McpServerResourceType]
public sealed class ServerResources
{
    /// <summary>
    /// List configured profiles.
    /// </summary>
    [McpServerResource(
        Name = "profiles",
        UriTemplate = "mssql://profiles",
        MimeType = "application/json")]
    [Description(
        "[MSSQL] List configured connection profiles.")]
    public static async Task<string> ListProfilesAsync(
        IProfileService profileService,
        CancellationToken cancellationToken = default)
    {
        return await McpExecutor.RunAsTextAsync(
            _ => Task.FromResult(profileService.GetProfiles()),
            cancellationToken).ConfigureAwait(false);
    }
}
