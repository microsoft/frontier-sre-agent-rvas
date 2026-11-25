// Entity Framework Core - execution strategy with retries for Azure SQL Managed Instance.
// dotnet add package Microsoft.EntityFrameworkCore.SqlServer
using System;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.DependencyInjection;

public static class EfCoreSetup
{
    public static IServiceCollection AddAppDb(this IServiceCollection services, string connectionString)
    {
        services.AddDbContext<AppDbContext>(options =>
            options.UseSqlServer(connectionString, sql => sql.EnableRetryOnFailure(
                maxRetryCount: 5,
                maxRetryDelay: TimeSpan.FromSeconds(20),
                // EF Core already includes the known Azure SQL transient errors.
                // Only add extra codes here if you see them in Application Insights.
                errorNumbersToAdd: new[] { 4221, 10928, 10929 })));
        return services;
    }
}

public class AppDbContext : DbContext
{
    public AppDbContext(DbContextOptions<AppDbContext> options) : base(options) { }
}

// Explicit transactions must be wrapped in the execution strategy so that, if a reconfiguration
// happens, the whole transaction is repeated and not a single command.
//
//   var strategy = db.Database.CreateExecutionStrategy();
//   await strategy.ExecuteAsync(async () =>
//   {
//       await using var tx = await db.Database.BeginTransactionAsync();
//       // ... changes ...
//       await db.SaveChangesAsync();
//       await tx.CommitAsync();
//   });
