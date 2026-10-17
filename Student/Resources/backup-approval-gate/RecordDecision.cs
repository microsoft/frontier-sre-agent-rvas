using System.Net;
using System.Text.Json;
using Microsoft.Azure.Functions.Worker;
using Microsoft.Azure.Functions.Worker.Http;

public sealed class RecordDecision(ApprovalStore store, TimeProvider timeProvider)
{
    [Function(nameof(RecordBackupDecision))]
    public async Task<HttpResponseData> RecordBackupDecision(
        [HttpTrigger(AuthorizationLevel.Function, "post", Route = "approvals/{incidentId}/decision")]
            HttpRequestData request,
        string incidentId,
        CancellationToken cancellationToken)
    {
        var input = await JsonSerializer.DeserializeAsync<DecisionInput>(
            request.Body,
            cancellationToken: cancellationToken);
        if (input is null ||
            (input.Decision is not "Approved" && input.Decision is not "Denied") ||
            string.IsNullOrWhiteSpace(input.ResponderId))
        {
            return request.CreateResponse(HttpStatusCode.BadRequest);
        }

        var record = await store.GetAsync(incidentId, cancellationToken);
        if (record is null)
        {
            return request.CreateResponse(HttpStatusCode.NotFound);
        }

        if (record.Decision is not "Pending")
        {
            return request.CreateResponse(HttpStatusCode.Conflict);
        }

        record.Decision = input.Decision;
        record.ResponderId = input.ResponderId;
        record.ResponderDisplayName = input.ResponderDisplayName;
        record.DecidedAt = timeProvider.GetUtcNow();
        await store.UpdateAsync(record, cancellationToken);

        var response = request.CreateResponse(HttpStatusCode.OK);
        await response.WriteAsJsonAsync(new
        {
            incidentId,
            decision = record.Decision,
            decidedAt = record.DecidedAt
        }, cancellationToken);
        return response;
    }

    private sealed record DecisionInput(
        string Decision,
        string ResponderId,
        string? ResponderDisplayName);
}