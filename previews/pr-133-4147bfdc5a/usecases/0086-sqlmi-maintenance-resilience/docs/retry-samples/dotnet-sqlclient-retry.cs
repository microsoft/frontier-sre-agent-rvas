// Microsoft.Data.SqlClient 5.x - exponential backoff retries for Azure SQL Managed Instance.
// dotnet add package Microsoft.Data.SqlClient
using System;
using System.Threading.Tasks;
using Microsoft.Data.SqlClient;

public static class SqlMi
{
    // Transient errors raised during a reconfiguration (maintenance or failover).
    private static readonly int[] TransientErrors =
    {
        233, 997, 1204, 1205, 1222, 4060, 4221, 10053, 10054, 10060, 10928, 10929,
        40143, 40197, 40501, 40540, 40613, 49918, 49919, 49920, -2
    };

    // 5 tries, starting at 1 s and never more than 20 s between tries: comfortably covers a
    // typical reconfiguration (usually < 30 s) without the user seeing the error.
    public static readonly SqlRetryLogicBaseProvider RetryProvider =
        SqlConfigurableRetryFactory.CreateExponentialRetryProvider(new SqlRetryLogicOption
        {
            NumberOfTries = 5,
            DeltaTime = TimeSpan.FromSeconds(1),
            MaxTimeInterval = TimeSpan.FromSeconds(20),
            TransientErrors = TransientErrors
        });

    // ConnectRetryCount/ConnectRetryInterval: recovers idle connections that get dropped.
    public static SqlConnection Open(string connectionString)
    {
        var builder = new SqlConnectionStringBuilder(connectionString)
        {
            ConnectRetryCount = 3,
            ConnectRetryInterval = 10,
            ConnectTimeout = 30
        };
        var connection = new SqlConnection(builder.ConnectionString) { RetryLogicProvider = RetryProvider };
        connection.Open(); // retries the open
        return connection;
    }

    public static async Task<int> CountOrdersAsync(string connectionString, string customerId)
    {
        using var connection = Open(connectionString);
        using var command = new SqlCommand("SELECT COUNT(*) FROM dbo.Orders WHERE CustomerId = @customerId", connection)
        {
            RetryLogicProvider = RetryProvider // retries the execution
        };
        command.Parameters.AddWithValue("@customerId", customerId);
        return (int)await command.ExecuteScalarAsync();
    }
}

// IMPORTANT
// - Retry only idempotent operations (reads) or the whole transaction.
// - A command inside an open transaction must NOT be retried on its own: if the connection
//   dropped, the transaction has already been rolled back. Repeat the whole block.
// - Log every retry (the provider's Retrying event) so it shows up in Application Insights.
