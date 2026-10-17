using Xunit;

public sealed class ApprovalPolicyTests
{
    private static readonly DateTimeOffset IncidentTime = new(2026, 9, 1, 12, 0, 0, TimeSpan.Zero);

    [Fact]
    public void DeniesPendingRequest()
    {
        var record = CreateRecord(decision: "Pending");

        var reason = ApprovalPolicy.GetDenialReason(record, IncidentTime.AddMinutes(5));

        Assert.Contains("Pending", reason);
    }

    [Fact]
    public void DeniesApprovedRequestBeforeFiveMinutes()
    {
        var record = CreateRecord(decision: "Approved");

        var reason = ApprovalPolicy.GetDenialReason(record, IncidentTime.AddMinutes(4).AddSeconds(59));

        Assert.Contains("less than five minutes", reason);
    }

    [Fact]
    public void AllowsApprovedRequestAtFiveMinutes()
    {
        var record = CreateRecord(decision: "Approved");

        var reason = ApprovalPolicy.GetDenialReason(record, IncidentTime.AddMinutes(5));

        Assert.Null(reason);
    }

    [Fact]
    public void DeniesClaimedRequestReplay()
    {
        var record = CreateRecord(decision: "Approved");
        record.ClaimedAt = IncidentTime.AddMinutes(5);

        var reason = ApprovalPolicy.GetDenialReason(record, IncidentTime.AddMinutes(6));

        Assert.Contains("already been claimed", reason);
    }

    private static ApprovalRecord CreateRecord(string decision) => new()
    {
        RowKey = "incident-123",
        IncidentCreatedAt = IncidentTime,
        RequestedAt = IncidentTime,
        Decision = decision
    };
}