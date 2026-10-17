using System.Net.Http.Json;

public sealed class ApprovalWorkflowClient(HttpClient httpClient)
{
    public async Task RequestAsync(ApprovalRecord record, CancellationToken cancellationToken)
    {
        var endpoint = Environment.GetEnvironmentVariable("APPROVAL_WORKFLOW_URL");
        if (string.IsNullOrWhiteSpace(endpoint))
        {
            throw new InvalidOperationException("APPROVAL_WORKFLOW_URL is not configured.");
        }

        using var response = await httpClient.PostAsJsonAsync(endpoint, new
        {
            incidentId = record.RowKey,
            incidentCreatedAt = record.IncidentCreatedAt,
            requestedAction = record.Action,
            title = "vm-parking-madrid backup retry approval",
            summary = "Azure Backup reported a failed VM backup. Approve one on-demand retry after the five-minute safety window."
        }, cancellationToken);
        response.EnsureSuccessStatusCode();
    }
}