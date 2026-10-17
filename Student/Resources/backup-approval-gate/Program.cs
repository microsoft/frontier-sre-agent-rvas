using Azure.Core;
using Azure.Data.Tables;
using Azure.Identity;
using Microsoft.Azure.Functions.Worker.Builder;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;

var builder = FunctionsApplication.CreateBuilder(args);

builder.ConfigureFunctionsWebApplication();
builder.Services.AddSingleton<TimeProvider>(TimeProvider.System);
builder.Services.AddSingleton<TokenCredential>(_ => new DefaultAzureCredential());
builder.Services.AddSingleton(serviceProvider =>
{
    var connectionString = Environment.GetEnvironmentVariable("AzureWebJobsStorage");
    if (!string.IsNullOrWhiteSpace(connectionString))
    {
        return new TableServiceClient(connectionString);
    }

    var tableServiceUri = Environment.GetEnvironmentVariable("AzureWebJobsStorage__tableServiceUri")
        ?? throw new InvalidOperationException("AzureWebJobsStorage table endpoint is not configured.");
    return new TableServiceClient(
        new Uri(tableServiceUri),
        serviceProvider.GetRequiredService<TokenCredential>());
});
builder.Services.AddSingleton<ApprovalStore>();
builder.Services.AddHttpClient<ApprovalWorkflowClient>();
builder.Services.AddHttpClient<BackupRetryClient>();

builder.Build().Run();