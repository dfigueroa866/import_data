from data_staging.utils.promotion_bulk import build_upsert_from_staging_sql, staging_select_expr


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


def test_build_upsert_from_staging_sql_casts_uuid_column():
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
