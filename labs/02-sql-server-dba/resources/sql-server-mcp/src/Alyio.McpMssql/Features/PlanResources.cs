// MIT License

using System.ComponentModel;
using Alyio.McpMssql.Internal;
using ModelContextProtocol.Server;

namespace Alyio.McpMssql.Features;

/// <summary>
/// Resource for retrieving the full XML execution plan by identifier.
/// </summary>
[McpServerResourceType]
public sealed class PlanResources
{
    /// <summary>
    /// Retrieve the full XML execution plan.
    /// </summary>
    [McpServerResource(
        Name = "plan",
        UriTemplate = "mssql://plans/{id}",
        MimeType = "application/xml")]
    [Description(
        "[MSSQL] Retrieve full XML execution plan by ID. " +
        "Entries expire. Src: analyze_query.")]
    public static async Task<string> GetPlanAsync(
        IPlanStore planStore,
        [Description("Opaque id from analyze_query (plan_uri path segment). Src: analyze_query.")]
        string id,
        CancellationToken cancellationToken = default)
    {
        return await McpExecutor.RunAsTextAsync(async ct =>
        {
            var xml = await planStore.TryGetAsync(id, ct).ConfigureAwait(false)
                ?? throw new InvalidOperationException($"Plan '{id}' not found or has expired.");

            return xml;
        }, cancellationToken).ConfigureAwait(false);
    }
}
