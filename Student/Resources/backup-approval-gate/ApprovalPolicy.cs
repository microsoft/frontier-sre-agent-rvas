public static class ApprovalPolicy
{
    public static string? GetDenialReason(ApprovalRecord record, DateTimeOffset now)
    {
        if (!string.Equals(record.Action, "RetryBackup", StringComparison.Ordinal))
        {
            return "The approved action does not match RetryBackup.";
        }

        if (!string.Equals(record.Decision, "Approved", StringComparison.Ordinal))
        {
            return $"The request decision is {record.Decision}.";
        }

        if (now < record.IncidentCreatedAt.AddMinutes(5))
        {
            return "The incident is less than five minutes old.";
        }

        if (record.ClaimedAt is not null)
        {
            return "The approved action has already been claimed.";
        }

        return null;
    }
}