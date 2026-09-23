// MIT License

using Alyio.McpMssql.Internal;

namespace Alyio.McpMssql.Tests.Unit;

public class SqlReadOnlyValidatorTests
{
    [Theory]
    [InlineData("select * from Users")]
    [InlineData("SELECT Id, Name FROM dbo.Users")]
    [InlineData(" select * from Users ; ")]
    [InlineData("with cte as (select * from Users) select * from cte")]
    [InlineData("-- comment\nselect * from Users")]
    [InlineData("select 'insert into table' as Value")]
    [InlineData("select [insert] from [table]")]
    [InlineData("select \"delete\" from \"table\"")]
    [InlineData("select '--' as Value")]
    [InlineData("select '/* not a comment */' as Value")]
    [InlineData("select * from Users with (nolock)")]
    [InlineData("select * from Users with (rowlock, readpast)")]
    public void Validate_Allows_ReadOnly_Select_Queries(string sql)
    {
        // Act / Assert
        SqlReadOnlyValidator.Validate(sql);
    }

    [Theory]
    [InlineData(null)]
    [InlineData("")]
    [InlineData("   ")]
    public void Validate_Throws_For_Null_Or_Empty(string? sql)
    {
        Assert.Throws<ArgumentException>(() =>
            SqlReadOnlyValidator.Validate(sql!));
    }

    [Theory]
    [InlineData("insert into Users values (1)")]
    [InlineData("update Users set Name = 'x'")]
    [InlineData("delete from Users")]
    [InlineData("merge into Users as t using Users as s on 1=0")]
    [InlineData("create table Test(Id int)")]
    [InlineData("drop table Users")]
    [InlineData("truncate table Users")]
    [InlineData("exec SomeProc")]
    [InlineData("execute SomeProc")]
    [InlineData("select * into TempTable from Users")]
    [InlineData("select *\ninto TempTable\nfrom Users")]
    [InlineData("select next value for dbo.SequenceName")]
    [InlineData("select @value = Id from Users")]
    [InlineData("select * from openrowset('SQLNCLI', 'Server=example;Trusted_Connection=yes;', 'select 1')")]
    [InlineData("select * from Users with (updlock)")]
    [InlineData("select * from Users with (xlock)")]
    [InlineData("select * from Users with (tablockx)")]
    [InlineData("select * from Users with (holdlock)")]
    [InlineData("select * from Users with (serializable)")]
    [InlineData("select * from Users with (repeatableread)")]
    [InlineData("select * from Users with (tablock)")]
    [InlineData("select * from Users with (serializable, rowlock)")]
    [InlineData("select * from Users u join Orders o with (serializable) on o.UserId = u.Id")]
    [InlineData("with cte as (select * from Users with (serializable)) select * from cte")]
    public void Validate_Throws_For_Forbidden_Keywords(string sql)
    {
        Assert.Throws<InvalidOperationException>(() =>
            SqlReadOnlyValidator.Validate(sql));
    }

    [Fact]
    public void Validate_Throws_For_Oversized_Query()
    {
        var sql = $"select * from Users where Name = '{new string('x', 64 * 1024)}'";

        Assert.Throws<InvalidOperationException>(() =>
            SqlReadOnlyValidator.Validate(sql));
    }

    [Fact]
    public void Validate_Throws_For_Deeply_Nested_Query()
    {
        // Far below the depth that overflows the stack, so the guard is what
        // rejects this rather than the process dying.
        var sql = $"select {new string('(', 200)}1{new string(')', 200)}";

        Assert.Throws<InvalidOperationException>(() =>
            SqlReadOnlyValidator.Validate(sql));
    }

    [Fact]
    public void Validate_Allows_Moderately_Nested_Query()
    {
        var sql = $"select {new string('(', 50)}1{new string(')', 50)}";

        SqlReadOnlyValidator.Validate(sql);
    }

    [Fact]
    public void Validate_Ignores_Parentheses_Inside_Literals()
    {
        // Depth is counted over tokens, so these never open a nesting level.
        var sql = $"select '{new string('(', 500)}' as Value";

        SqlReadOnlyValidator.Validate(sql);
    }

    [Fact]
    public void Validate_Throws_For_Multiple_Statements()
    {
        var sql = "select * from Users; select * from Orders";

        Assert.Throws<InvalidOperationException>(() =>
            SqlReadOnlyValidator.Validate(sql));
    }

    [Theory]
    [InlineData("select '--'; update Users set Name = 'x'")]
    [InlineData("select '/*'; delete from Users; /* */")]
    [InlineData("select 1\nupdate\nUsers set Name = 'x'")]
    [InlineData("select 1\tdelete\tfrom Users")]
    public void Validate_Throws_For_Obfuscated_Write_Batches(string sql)
    {
        Assert.Throws<InvalidOperationException>(() =>
            SqlReadOnlyValidator.Validate(sql));
    }


    [Theory]
    [InlineData("select 'delete from Users' as SqlText")]
    [InlineData("select '-- drop table Users' as Comment")]
    [InlineData("select 'insert into x values (1)'")]
    [InlineData("select * from Users /* update Users */")]
    public void Validate_Ignores_Keywords_In_Strings_And_Comments(string sql)
    {
        SqlReadOnlyValidator.Validate(sql);
    }

    [Theory]
    [InlineData("with cte as (select * from Users) update Users set Name = 'x'")]
    [InlineData("with cte as (select * from Users) delete from Users")]
    public void Validate_Throws_For_Cte_That_Executes_Write(string sql)
    {
        Assert.Throws<InvalidOperationException>(() =>
            SqlReadOnlyValidator.Validate(sql));
    }
}

