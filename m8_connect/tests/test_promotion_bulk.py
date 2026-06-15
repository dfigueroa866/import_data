import pyarrow as pa

from data_staging.utils.promotion_bulk import (
    build_upsert_from_staging_batch_sql,
    build_upsert_from_staging_sql,
    copy_arrow_batch_to_staging,
    staging_select_expr,
)


def test_staging_select_expr_uuid_cast():
    expr = staging_select_expr("organization_id", "uuid")
    assert expr == 'NULLIF(s."organization_id", \'\')::uuid'


def test_staging_select_expr_text_passthrough():
    expr = staging_select_expr("location_code", "character varying")
    assert expr == 's."location_code"'


def test_staging_select_expr_integer_accepts_float_text():
    expr = staging_select_expr("pieces", "integer")
    assert expr == 'NULLIF(s."pieces", \'\')::numeric::integer'


def test_build_upsert_from_staging_sql_casts_integer_column():
    sql = build_upsert_from_staging_sql(
        "public",
        "sales_history",
        ['"pieces"', '"quantity"'],
        ["pieces", "quantity"],
        "",
        include_imported_at=False,
        db_columns={
            "pieces": "integer",
            "quantity": "double precision",
        },
    )
    assert 'NULLIF(s."pieces", \'\')::numeric::integer' in sql
    assert 'NULLIF(s."quantity", \'\')::double precision' in sql


def test_copy_arrow_batch_to_staging_builds_rows():
    batch = pa.RecordBatch.from_pydict(
        {
            "organization_id": ["uuid-1", None],
            "pieces": [1, 2],
        }
    )
    buffer_rows: list = []

    class _Cursor:
        def copy_expert(self, _sql, buffer):
            buffer_rows.extend(buffer.getvalue().splitlines())

    copied = copy_arrow_batch_to_staging(
        _Cursor(),
        batch,
        ["organization_id", "pieces"],
        ["organization_id", "pieces"],
    )
    assert copied == 2
    assert buffer_rows[0] == "uuid-1\t1"
    assert buffer_rows[1] == "\\N\t2"


def test_build_upsert_from_staging_sql_split_insert_update_counts():
    conflict = (
        'ON CONFLICT ("organization_id", "sku", "period_start") '
        'DO UPDATE SET "quantity" = EXCLUDED."quantity"'
    )
    sql = build_upsert_from_staging_sql(
        "public",
        "sales_history",
        ['"organization_id"', '"sku"', '"period_start"', '"quantity"'],
        ["organization_id", "sku", "period_start", "quantity"],
        conflict,
        include_imported_at=False,
        count_split=True,
    )
    assert "xmax = 0" in sql
    assert "FILTER (WHERE is_insert)" in sql
    assert "FILTER (WHERE NOT is_insert)" in sql

    sql = build_upsert_from_staging_sql(
        "public",
        "sales_history",
        ['"organization_id"', '"location_code"'],
        ["organization_id", "location_code"],
        "",
        include_imported_at=False,
        db_columns={
            "organization_id": "uuid",
            "location_code": "character varying",
        },
    )
    assert 'NULLIF(s."organization_id", \'\')::uuid' in sql
    assert 's."location_code"' in sql


def test_build_upsert_from_staging_batch_sql_limits_and_deletes():
    conflict = (
        'ON CONFLICT ("organization_id", "granularity", "location_code", "sku", '
        '"sales_channel", "period_start") DO UPDATE SET "quantity" = EXCLUDED."quantity"'
    )
    sql = build_upsert_from_staging_batch_sql(
        "public",
        "sales_history",
        ['"organization_id"', '"sku"', '"quantity"'],
        ["organization_id", "sku", "quantity"],
        conflict,
        batch_limit=500_000,
        include_imported_at=False,
        order_by_cols=["organization_id", "sku"],
        count_split=True,
    )
    assert "LIMIT 500000" in sql
    assert 'ORDER BY s."organization_id", s."sku"' in sql
    assert "WITH batch AS" in sql
    assert "DELETE FROM batch_promo_staging_acc d" in sql
    assert "USING batch b" in sql
    assert "xmax = 0" in sql


def test_build_upsert_from_staging_batch_sql_no_count_split():
    sql = build_upsert_from_staging_batch_sql(
        "public",
        "sales_history",
        ['"organization_id"', '"quantity"'],
        ["organization_id", "quantity"],
        "",
        batch_limit=250_000,
        include_imported_at=False,
        count_split=False,
    )
    assert "LIMIT 250000" in sql
    assert "xmax" not in sql
    assert "SELECT COUNT(*)::int FROM batch" in sql
    assert "SELECT 1" not in sql
