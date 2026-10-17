using Azure;
using Azure.Data.Tables;

public sealed class ApprovalStore
{
    private const string TableName = "BackupApprovals";
    private readonly TableClient _table;

    public ApprovalStore(TableServiceClient tableServiceClient)
    {
        _table = tableServiceClient.GetTableClient(TableName);
        _table.CreateIfNotExists();
    }

    public async Task<ApprovalRecord> CreateAsync(
        string incidentId,
        DateTimeOffset incidentCreatedAt,
        DateTimeOffset requestedAt,
        CancellationToken cancellationToken)
    {
        var record = new ApprovalRecord
        {
            RowKey = incidentId,
            IncidentCreatedAt = incidentCreatedAt,
            RequestedAt = requestedAt
        };

        try
        {
            await _table.AddEntityAsync(record, cancellationToken);
            return record;
        }
        catch (RequestFailedException exception) when (exception.Status == 409)
        {
            return await GetRequiredAsync(incidentId, cancellationToken);
        }
    }

    public async Task<ApprovalRecord?> GetAsync(string incidentId, CancellationToken cancellationToken)
    {
        var response = await _table.GetEntityIfExistsAsync<ApprovalRecord>(
            "backup",
            incidentId,
            cancellationToken: cancellationToken);
        return response.HasValue ? response.Value : null;
    }

    public async Task<ApprovalRecord> GetRequiredAsync(string incidentId, CancellationToken cancellationToken)
    {
        return await _table.GetEntityAsync<ApprovalRecord>(
            "backup",
            incidentId,
            cancellationToken: cancellationToken);
    }

    public async Task UpdateAsync(ApprovalRecord record, CancellationToken cancellationToken)
    {
        var response = await _table.UpdateEntityAsync(
            record,
            record.ETag,
            TableUpdateMode.Replace,
            cancellationToken);
        record.ETag = response.Headers.ETag ?? record.ETag;
    }
}