// MIT License

using Alyio.McpMssql.Configuration;
using Microsoft.Data.SqlClient;

namespace Alyio.McpMssql.Tests.Unit;

public sealed class AzureManagedIdentityConnectionPolicyTests
{
    private const string ClientId = "11111111-2222-3333-4444-555555555555";

    [Fact]
    public void GivenManagedIdentityConnection_WhenValidated_ReturnsHardenedConnection()
    {
        string input =
            "Server=tcp:example.database.windows.net,1433;"
            + "Database=stockOrders;"
            + "Authentication=Active Directory Managed Identity;"
            + $"User Id={ClientId};"
            + "Encrypt=False;"
            + "TrustServerCertificate=True;"
            + "Connect Timeout=120;";

        string actual = AzureManagedIdentityConnectionPolicy.ValidateAndNormalize(input, "default");
        var builder = new SqlConnectionStringBuilder(actual);

        Assert.Equal(SqlAuthenticationMethod.ActiveDirectoryManagedIdentity, builder.Authentication);
        Assert.Equal(ClientId, builder.UserID);
        Assert.Equal("stockOrders", builder.InitialCatalog);
        Assert.False(builder.TrustServerCertificate);
        Assert.False(builder.PersistSecurityInfo);
        Assert.Equal(ApplicationIntent.ReadOnly, builder.ApplicationIntent);
        Assert.Equal(30, builder.ConnectTimeout);
        Assert.Equal("AzureSRE-SqlDba", builder.ApplicationName);
    }

    [Theory]
    [InlineData(
        "Server=example.database.windows.net;Database=stockOrders;User Id=sa;Password=secret;",
        "Managed Identity")]
    [InlineData(
        "Server=example.database.windows.net;Authentication=Active Directory Managed Identity;User Id=11111111-2222-3333-4444-555555555555;",
        "explicit database")]
    [InlineData(
        "Server=example.database.windows.net;Database=stockOrders;Authentication=Active Directory Managed Identity;User Id=not-a-guid;",
        "client ID")]
    public void GivenUnsafeConnection_WhenValidated_Throws(
        string connectionString,
        string expectedMessage)
    {
        var exception = Assert.Throws<InvalidOperationException>(
            () => AzureManagedIdentityConnectionPolicy.ValidateAndNormalize(
                connectionString,
                "default"));

        Assert.Contains(expectedMessage, exception.Message, StringComparison.OrdinalIgnoreCase);
    }
}
