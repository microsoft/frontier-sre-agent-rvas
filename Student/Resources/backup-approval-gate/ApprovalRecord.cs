using Azure;
using Azure.Data.Tables;

public sealed class ApprovalRecord : ITableEntity
{
    public string PartitionKey { get; set; } = "backup";
    public string RowKey { get; set; } = string.Empty;
    public DateTimeOffset? Timestamp { get; set; }
    public ETag ETag { get; set; }
    public DateTimeOffset IncidentCreatedAt { get; set; }
    public DateTimeOffset RequestedAt { get; set; }
    public string Action { get; set; } = "RetryBackup";
    public string Decision { get; set; } = "Pending";
    public string? ResponderId { get; set; }
    public string? ResponderDisplayName { get; set; }
    public DateTimeOffset? DecidedAt { get; set; }
    public DateTimeOffset? ClaimedAt { get; set; }
    public string? OperationUrl { get; set; }
    public string? Failure { get; set; }
}