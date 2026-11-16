// MIT License

using Alyio.McpMssql.Internal;

namespace Alyio.McpMssql.Tests.Unit;

public sealed class ObjectNameTests
{
    [Theory]
    [InlineData("Users", null, "Users", null)]
    [InlineData("[Users]", null, "Users", null)]
    [InlineData("dbo.Users", null, "Users", "dbo")]
    [InlineData("[dbo].[Users]", null, "Users", "dbo")]
    [InlineData("McpMssqlTest.dbo.Users", null, "Users", "dbo")]
    [InlineData("  dbo.Users  ", null, "Users", "dbo")]
    public void Split_Parses_Qualified_And_Bracketed_Names(
        string name, string? schema, string expectedName, string? expectedSchema)
    {
        var (actualName, actualSchema) = ObjectName.Split(name, schema);

        Assert.Equal(expectedName, actualName);
        Assert.Equal(expectedSchema, actualSchema);
    }

    [Fact]
    public void Split_Prefers_Explicit_Schema_Over_Embedded_One()
    {
        var (name, schema) = ObjectName.Split("[staging].[Users]", "dbo");

        Assert.Equal("Users", name);
        Assert.Equal("dbo", schema);
    }

    [Fact]
    public void Split_Keeps_Dots_Inside_Brackets()
    {
        var (name, schema) = ObjectName.Split("[my.schema].[my.table]", null);

        Assert.Equal("my.table", name);
        Assert.Equal("my.schema", schema);
    }

    [Fact]
    public void Split_Unescapes_Doubled_Closing_Bracket()
    {
        var (name, _) = ObjectName.Split("[odd]]name]", null);

        Assert.Equal("odd]name", name);
    }
}
