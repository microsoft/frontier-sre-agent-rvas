using System.Net.Http.Headers;
using System.Net.Http.Json;
using Azure.Core;

public sealed class BackupRetryClient(HttpClient httpClient, TokenCredential credential)
{
    public async Task<string> TriggerAsync(CancellationToken cancellationToken)
    {
        var protectedItemId = Environment.GetEnvironmentVariable("BACKUP_PROTECTED_ITEM_ID");
        if (string.IsNullOrWhiteSpace(protectedItemId))
        {
            throw new InvalidOperationException("BACKUP_PROTECTED_ITEM_ID is not configured.");
        }

        var token = await credential.GetTokenAsync(
            new TokenRequestContext(["https://management.azure.com/.default"]),
            cancellationToken);
        var endpoint = $"https://management.azure.com{protectedItemId}/backup?api-version=2025-08-01";

        using var request = new HttpRequestMessage(HttpMethod.Post, endpoint);
        request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", token.Token);
        request.Content = JsonContent.Create(new
        {
            properties = new
            {
                objectType = "IaasVMBackupRequest",
                recoveryPointExpiryTimeInUTC = DateTimeOffset.UtcNow.AddDays(7)
            }
        });

        using var response = await httpClient.SendAsync(request, cancellationToken);
        response.EnsureSuccessStatusCode();

        return response.Headers.TryGetValues("Azure-AsyncOperation", out var values)
            ? values.Single()
            : response.Headers.Location?.ToString() ?? "Accepted";
    }
}