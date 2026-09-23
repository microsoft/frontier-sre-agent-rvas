// MIT License

using Microsoft.SqlServer.TransactSql.ScriptDom;

namespace Alyio.McpMssql.Internal;

/// <summary>
/// Validates that a SQL statement is a single, read-only SELECT query.
/// </summary>
internal static class SqlReadOnlyValidator
{
    // ScriptDom parses by recursive descent and the visitor walks the tree the
    // same way, so deeply nested input overflows the stack. That abort cannot
    // be caught and takes the whole server down, which makes it a denial of
    // service rather than a failed query, so the input is bounded up front.
    // Measured on a thread-pool thread, the cheapest crash is ~4,000 levels of
    // nested derived tables (~72 KB); nesting that needs no parentheses, such
    // as CASE, takes ~138 KB. Both limits sit far below those and far above
    // any hand-written query.
    private const int MaxLength = 64 * 1024;
    private const int MaxNestingDepth = 100;

    /// <summary>
    /// Parses and validates the provided T-SQL text.
    /// </summary>
    /// <remarks>
    /// <para>
    /// The text must parse as a single batch holding exactly one
    /// <c>SELECT</c> statement. Everything else is rejected, including DDL,
    /// DML, <c>EXEC</c>, and multi-statement or <c>GO</c>-separated scripts.
    /// Within that statement the following are rejected as well:
    /// <list type="bullet">
    ///   <item><description>
    ///     <c>SELECT ... INTO</c>, which materializes a new table.
    ///   </description></item>
    ///   <item><description>
    ///     Variable assignment (<c>SELECT @v = ...</c>), which mutates
    ///     session state.
    ///   </description></item>
    ///   <item><description>
    ///     <c>NEXT VALUE FOR</c>, which advances a sequence.
    ///   </description></item>
    ///   <item><description>
    ///     Ad-hoc external data sources: <c>OPENQUERY</c>,
    ///     <c>OPENDATASOURCE</c>, <c>OPENROWSET</c>, and
    ///     <c>OPENROWSET(BULK)</c>.
    ///   </description></item>
    ///   <item><description>
    ///     Locking hints that impede writers: <c>HOLDLOCK</c> and its synonym
    ///     <c>SERIALIZABLE</c>, <c>REPEATABLEREAD</c>, <c>TABLOCK</c>,
    ///     <c>TABLOCKX</c>, <c>UPDLOCK</c>, and <c>XLOCK</c>.
    ///   </description></item>
    /// </list>
    /// Hints that take no additional locks, such as <c>NOLOCK</c>,
    /// <c>ROWLOCK</c> and <c>READPAST</c>, stay allowed.
    /// </para>
    /// <para>
    /// Input longer than 64 KB, or nested more than 100 parentheses deep, is
    /// rejected before parsing to keep the recursive-descent parser away from
    /// a stack overflow.
    /// </para>
    /// </remarks>
    /// <exception cref="ArgumentException">
    /// Thrown when the SQL is null or empty.
    /// </exception>
    /// <exception cref="InvalidOperationException">
    /// Thrown when the SQL exceeds the size limits, is invalid, or is not a
    /// read-only SELECT query.
    /// </exception>
    public static void Validate(string sql)
    {
        if (string.IsNullOrWhiteSpace(sql))
        {
            throw new ArgumentException("SQL query cannot be empty.", nameof(sql));
        }

        if (sql.Length > MaxLength)
        {
            throw new InvalidOperationException(
                $"The query exceeds the maximum length of {MaxLength} characters.");
        }

        // TSql180Parser is the newest grammar the pinned ScriptDom ships and is
        // ahead of SQL Server 2025, so it accepts what current servers accept;
        // syntax introduced after it needs a parser bump here. SqlEngineType is
        // left at its default so no engine flavour is excluded. The server
        // stays the authority on what it can actually execute.
        var parser = new TSql180Parser(initialQuotedIdentifiers: true);

        EnsureNestingWithinLimit(parser, sql);

        using var reader = new StringReader(sql);

        TSqlFragment fragment = parser.Parse(reader, out IList<ParseError> errors);

        if (errors.Count > 0)
        {
            // ScriptDom stops at the first error within a statement, so a
            // single-statement query reports exactly one. Several errors mean
            // several batches, which the single-SELECT check below rejects
            // regardless of their syntax.
            ParseError first = errors[0];
            throw new InvalidOperationException(
                $"Invalid T-SQL at line {first.Line}, column {first.Column}: {first.Message}");
        }

        if (fragment is not TSqlScript { Batches.Count: 1 } script
            || script.Batches[0].Statements is not [SelectStatement select])
        {
            throw new InvalidOperationException(
                "Only one read-only SELECT statement is allowed.");
        }

        var visitor = new ReadOnlyViolationVisitor();
        select.Accept(visitor);

        if (visitor.Violation is not null)
        {
            throw new InvalidOperationException(visitor.Violation);
        }
    }

    /// <summary>
    /// Rejects text nested deeper than <see cref="MaxNestingDepth"/>.
    /// </summary>
    /// <remarks>
    /// Tokenizing is iterative, so it is safe to run over input that would
    /// overflow the stack during parsing. Counting tokens rather than
    /// characters keeps parentheses inside string literals and comments from
    /// contributing to the depth. Lexer errors are left for
    /// <c>TSqlParser.Parse</c> to report.
    /// </remarks>
    private static void EnsureNestingWithinLimit(TSqlParser parser, string sql)
    {
        using var reader = new StringReader(sql);
        IList<TSqlParserToken> tokens = parser.GetTokenStream(reader, out _);

        var depth = 0;

        foreach (TSqlParserToken token in tokens)
        {
            if (token.TokenType == TSqlTokenType.LeftParenthesis)
            {
                depth++;

                if (depth > MaxNestingDepth)
                {
                    throw new InvalidOperationException(
                        $"The query exceeds the maximum nesting depth of {MaxNestingDepth}.");
                }
            }
            else if (token.TokenType == TSqlTokenType.RightParenthesis)
            {
                depth--;
            }
        }
    }

    private sealed class ReadOnlyViolationVisitor : TSqlFragmentVisitor
    {
        public string? Violation { get; private set; }

        public override void Visit(TSqlFragment node)
        {
            if (node is AdHocTableReference
                or OpenQueryTableReference
                or OpenRowsetTableReference
                or InternalOpenRowset
                or OpenRowsetCosmos
                or BulkOpenRowset)
            {
                Reject("Ad-hoc external data sources are not allowed.");
            }

            base.Visit(node);
        }

        public override void ExplicitVisit(SelectStatement node)
        {
            if (node.Into is not null)
            {
                Reject("SELECT INTO is not allowed.");
            }

            base.ExplicitVisit(node);
        }

        public override void ExplicitVisit(SelectSetVariable node)
        {
            Reject("Assigning variables in SELECT is not allowed.");
            base.ExplicitVisit(node);
        }

        public override void ExplicitVisit(NextValueForExpression node)
        {
            Reject("NEXT VALUE FOR is not allowed because it changes sequence state.");
            base.ExplicitVisit(node);
        }

        public override void ExplicitVisit(TableHint node)
        {
            if (node.HintKind is TableHintKind.HoldLock
                or TableHintKind.RepeatableRead
                or TableHintKind.Serializable
                or TableHintKind.TabLock
                or TableHintKind.TabLockX
                or TableHintKind.UpdLock
                or TableHintKind.XLock)
            {
                Reject($"The {node.HintKind} locking hint is not allowed.");
            }

            base.ExplicitVisit(node);
        }

        private void Reject(string message)
        {
            Violation ??= message;
        }
    }
}
