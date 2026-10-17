using System.Text.Json;
using Microsoft.Azure.Functions.Worker;
using Microsoft.Azure.Functions.Worker.Extensions.Mcp;

public sealed class BackupApprovalTools(
    ApprovalStore store,
    ApprovalWorkflowClient workflow,
    BackupRetryClient backupRetry,
    TimeProvider timeProvider)
{
    [Function(nameof(CreateBackupApproval))]
    public async Task<string> CreateBackupApproval(
        [McpToolTrigger("create_backup_approval", "Create one durable Teams approval request for a vm-parking-madrid backup incident.")]
            ToolInvocationContext context,
        [McpToolProperty("incidentId", "The immutable Azure Monitor incident identifier.", true)]
            string incidentId,
        [McpToolProperty("incidentCreatedAt", "The Azure Monitor incident creation time in ISO 8601 UTC format.", true)]
            string incidentCreatedAt,
        CancellationToken cancellationToken)
    {
        if (!DateTimeOffset.TryParse(incidentCreatedAt, out var createdAt))
        {
            throw new ArgumentException("incidentCreatedAt must be an ISO 8601 timestamp.");
        }

        var existing = await store.GetAsync(incidentId, cancellationToken);
        var record = await store.CreateAsync(
            incidentId,
            createdAt.ToUniversalTime(),
            timeProvider.GetUtcNow(),
            cancellationToken);

        if (existing is null)
        {
            await workflow.RequestAsync(record, cancellationToken);
        }

        return JsonSerializer.Serialize(ToResult(record));
    }

    [Function(nameof(GetBackupApproval))]
    public async Task<string> GetBackupApproval(
        [McpToolTrigger("get_backup_approval", "Get the durable decision and execution state for a vm-parking-madrid backup incident.")]
            ToolInvocationContext context,
        [McpToolProperty("incidentId", "The immutable Azure Monitor incident identifier.", true)]
            string incidentId,
        CancellationToken cancellationToken)
    {
        var record = await store.GetAsync(incidentId, cancellationToken);
        return JsonSerializer.Serialize(record is null ? new { found = false } : ToResult(record));
    }

    [Function(nameof(ExecuteApprovedBackupRetry))]
    public async Task<string> ExecuteApprovedBackupRetry(
        [McpToolTrigger("execute_approved_backup_retry", "Trigger one vm-parking-madrid VM backup only when Teams approval exists and the incident is at least five minutes old.")]
            ToolInvocationContext context,
        [McpToolProperty("incidentId", "The immutable Azure Monitor incident identifier.", true)]
            string incidentId,
        CancellationToken cancellationToken)
    {
        var record = await store.GetRequiredAsync(incidentId, cancellationToken);
        var denialReason = ApprovalPolicy.GetDenialReason(record, timeProvider.GetUtcNow());
        if (denialReason is not null)
        {
            return JsonSerializer.Serialize(new { executed = false, reason = denialReason });
        }

        record.ClaimedAt = timeProvider.GetUtcNow();
        await store.UpdateAsync(record, cancellationToken);

        try
        {
            record.OperationUrl = await backupRetry.TriggerAsync(cancellationToken);
            await store.UpdateAsync(record, cancellationToken);
            return JsonSerializer.Serialize(new { executed = true, operationUrl = record.OperationUrl });
        }
        catch (Exception exception)
        {
            record.Failure = exception.Message;
            await store.UpdateAsync(record, cancellationToken);
            throw;
        }
    }

    private static object ToResult(ApprovalRecord record) => new
    {
        incidentId = record.RowKey,
        incidentCreatedAt = record.IncidentCreatedAt,
        requestedAt = record.RequestedAt,
        action = record.Action,
        decision = record.Decision,
        responderId = record.ResponderId,
        responderDisplayName = record.ResponderDisplayName,
        decidedAt = record.DecidedAt,
        claimedAt = record.ClaimedAt,
        operationUrl = record.OperationUrl,
        failure = record.Failure
    };
}