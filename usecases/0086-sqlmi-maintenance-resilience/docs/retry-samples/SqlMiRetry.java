// Java (Microsoft JDBC Driver for SQL Server) - exponential backoff retries with jitter.
// Maven: com.microsoft.sqlserver:mssql-jdbc
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.Set;
import java.util.concurrent.ThreadLocalRandom;

public final class SqlMiRetry {

    // Transient errors during a reconfiguration (maintenance or failover).
    private static final Set<Integer> TRANSIENT = Set.of(
        233, 997, 1204, 1205, 1222, 4060, 4221, 10053, 10054, 10060, 10928, 10929,
        40143, 40197, 40501, 40540, 40613, 49918, 49919, 49920);

    private static final int MAX_TRIES = 5;
    private static final long BASE_DELAY_MS = 1_000;
    private static final long MAX_DELAY_MS = 20_000;

    @FunctionalInterface
    public interface SqlWork<T> { T run(Connection connection) throws SQLException; }

    // connectRetryCount/connectRetryInterval: recovers idle connections.
    // Sample URL:
    // jdbc:sqlserver://<mi>.<dns-zone>.database.windows.net:1433;database=orders;encrypt=true;
    //   connectRetryCount=3;connectRetryInterval=10;loginTimeout=30;authentication=ActiveDirectoryDefault
    public static <T> T execute(String jdbcUrl, SqlWork<T> work) throws SQLException, InterruptedException {
        SQLException last = null;
        for (int attempt = 1; attempt <= MAX_TRIES; attempt++) {
            try (Connection connection = DriverManager.getConnection(jdbcUrl)) {
                return work.run(connection); // the whole unit of work is repeated
            } catch (SQLException ex) {
                if (!isTransient(ex) || attempt == MAX_TRIES) throw ex;
                last = ex;
                long delay = Math.min(MAX_DELAY_MS, BASE_DELAY_MS * (1L << (attempt - 1)));
                delay += ThreadLocalRandom.current().nextLong(0, 500); // jitter
                System.err.printf("Transient SQL error %d (try %d/%d). Retrying in %d ms%n",
                        ex.getErrorCode(), attempt, MAX_TRIES, delay);
                Thread.sleep(delay);
            }
        }
        throw last;
    }

    private static boolean isTransient(SQLException ex) {
        for (SQLException e = ex; e != null; e = e.getNextException()) {
            if (TRANSIENT.contains(e.getErrorCode())) return true;
            String state = e.getSQLState();
            if (state != null && state.startsWith("08")) return true; // connection errors
        }
        return false;
    }

    public static int countOrders(String jdbcUrl, String customerId) throws Exception {
        return execute(jdbcUrl, connection -> {
            try (PreparedStatement ps = connection.prepareStatement(
                    "SELECT COUNT(*) FROM dbo.Orders WHERE CustomerId = ?")) {
                ps.setString(1, customerId);
                try (ResultSet rs = ps.executeQuery()) { rs.next(); return rs.getInt(1); }
            }
        });
    }
}
// Spring: the equivalent is spring-retry (@Retryable) on the whole service method,
// never on a single command inside an open transaction.
