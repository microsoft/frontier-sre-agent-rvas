// MIT License

using Alyio.McpMssql.Services;
using Microsoft.Extensions.Logging.Abstractions;

namespace Alyio.McpMssql.Tests.Unit;

/// <summary>
/// Save, retrieval and eviction all live on <see cref="ContentStore"/>; the two
/// stores differ only in cache directory, extension and TTL, so each case runs
/// over both rather than being written out twice.
/// </summary>
public sealed class ContentStoreTests : IDisposable
{
    private readonly string _directory = Path.Combine(Path.GetTempPath(), $"mcpmssql-content-{Guid.NewGuid():N}");

    private static CancellationToken CancellationToken => TestContext.Current.CancellationToken;

    public static TheoryData<string> Stores => [PlanStoreKind, SnapshotStoreKind];

    private const string PlanStoreKind = "plan";
    private const string SnapshotStoreKind = "snapshot";

    public void Dispose()
    {
        try
        {
            if (Directory.Exists(_directory))
            {
                Directory.Delete(_directory, recursive: true);
            }
        }
        catch
        {
            // Best effort test cleanup.
        }
    }

    private IContentStore Create(string kind) => kind switch
    {
        PlanStoreKind => new PlanStore(_directory, NullLogger<PlanStore>.Instance),
        _ => new SnapshotStore(_directory, NullLogger<SnapshotStore>.Instance),
    };

    private static string Extension(string kind) =>
        kind == PlanStoreKind ? ".sqlplan.xml" : ".snapshot.csv";

    private static TimeSpan Ttl(string kind) =>
        kind == PlanStoreKind ? PlanStore.Ttl : SnapshotStore.Ttl;

    private static string Content(string kind) =>
        kind == PlanStoreKind ? "<ShowPlanXML/>" : "id,name\n1,Alice\n";

    [Theory]
    [MemberData(nameof(Stores))]
    public async Task Save_Produces_Unique_Guid_Ids(string kind)
    {
        var store = Create(kind);

        var first = await store.SaveAsync(Content(kind), CancellationToken);
        var second = await store.SaveAsync(Content(kind), CancellationToken);

        Assert.True(Guid.TryParseExact(first, "N", out _), $"Expected a GUID id, got '{first}'.");
        Assert.NotEqual(first, second);
    }

    [Theory]
    [MemberData(nameof(Stores))]
    public async Task TryGet_Returns_Saved_Content(string kind)
    {
        var store = Create(kind);
        var id = await store.SaveAsync(Content(kind), CancellationToken);

        Assert.Equal(Content(kind), await store.TryGetAsync(id, CancellationToken));
    }

    [Theory]
    [MemberData(nameof(Stores))]
    public async Task TryGet_Returns_Null_For_Unknown_Id(string kind)
    {
        var store = Create(kind);

        Assert.Null(await store.TryGetAsync(Guid.NewGuid().ToString("N"), CancellationToken));
    }

    [Theory]
    [MemberData(nameof(Stores))]
    public async Task TryGet_Rejects_Id_That_Escapes_The_Store_Directory(string kind)
    {
        // Without the GUID guard this id resolves through Path.Combine and
        // reads a file the store never wrote.
        Directory.CreateDirectory(_directory);
        var outsidePath = Path.Combine(_directory, $"..{Path.DirectorySeparatorChar}escape{Extension(kind)}");
        await File.WriteAllTextAsync(outsidePath, Content(kind), CancellationToken);

        try
        {
            Assert.Null(await Create(kind).TryGetAsync("../escape", CancellationToken));
        }
        finally
        {
            File.Delete(outsidePath);
        }
    }

    [Theory]
    [MemberData(nameof(Stores))]
    public async Task TryGet_Loads_An_Existing_File_Into_Memory(string kind)
    {
        var id = Guid.NewGuid().ToString("N");
        var path = Path.Combine(_directory, $"{id}{Extension(kind)}");
        Directory.CreateDirectory(_directory);
        await File.WriteAllTextAsync(path, Content(kind), CancellationToken);

        var store = Create(kind);
        Assert.Equal(Content(kind), await store.TryGetAsync(id, CancellationToken));

        // Served from memory once loaded, so the file is no longer needed.
        File.Delete(path);
        Assert.Equal(Content(kind), await store.TryGetAsync(id, CancellationToken));
    }

    [Theory]
    [MemberData(nameof(Stores))]
    public async Task TryGet_Evicts_An_Expired_File_On_First_Load(string kind)
    {
        var id = await Create(kind).SaveAsync(Content(kind), CancellationToken);
        var path = Path.Combine(_directory, $"{id}{Extension(kind)}");
        File.SetLastWriteTimeUtc(path, DateTime.UtcNow - Ttl(kind) - TimeSpan.FromDays(1));

        Assert.Null(await Create(kind).TryGetAsync(id, CancellationToken));
        Assert.False(File.Exists(path));
    }
}
