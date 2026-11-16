-- describe_relationships: foreign keys in both directions for one relation.
-- outgoing = this table references another; incoming = another references this table.
SELECT
    CASE
        WHEN pt.name = @table AND (@schema IS NULL OR ps.name = @schema)
        THEN 'outgoing'
        ELSE 'incoming'
    END                                     AS direction,
    fk.name                                 AS fk_name,
    ps.name                                 AS parent_schema,
    pt.name                                 AS parent_table,
    pc.name                                 AS parent_column,
    rs.name                                 AS referenced_schema,
    rt.name                                 AS referenced_table,
    rc.name                                 AS referenced_column,
    fk.delete_referential_action_desc       AS delete_action,
    fk.update_referential_action_desc       AS update_action
FROM sys.foreign_keys fk
INNER JOIN sys.foreign_key_columns fkc
    ON fkc.constraint_object_id = fk.object_id
INNER JOIN sys.tables pt
    ON pt.object_id = fk.parent_object_id
INNER JOIN sys.schemas ps
    ON ps.schema_id = pt.schema_id
INNER JOIN sys.columns pc
    ON pc.object_id = fkc.parent_object_id AND pc.column_id = fkc.parent_column_id
INNER JOIN sys.tables rt
    ON rt.object_id = fk.referenced_object_id
INNER JOIN sys.schemas rs
    ON rs.schema_id = rt.schema_id
INNER JOIN sys.columns rc
    ON rc.object_id = fkc.referenced_object_id AND rc.column_id = fkc.referenced_column_id
WHERE
    (pt.name = @table AND (@schema IS NULL OR ps.name = @schema))
    OR (rt.name = @table AND (@schema IS NULL OR rs.name = @schema))
ORDER BY
    direction,
    fk_name,
    fkc.constraint_column_id;
