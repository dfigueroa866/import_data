/**
 * Fallback catalog table definitions when /catalog-tables API is unavailable
 * (e.g. backend not restarted after deploy). Shape matches GET catalog-tables response.
 */
export const FALLBACK_CATALOG_TABLES = [
    {
        name: 'skus',
        label: 'Productos (SKUs)',
        target_schema: 'public',
        required_columns: ['organization_id', 'code', 'name'],
        optional_columns: ['category', 'family', 'brand', 'status', 'attributes'],
        unique_keys: ['organization_id', 'code'],
        enums: { status: ['active', 'discontinued', 'new_launch'] },
        validation_hints: [
            'Clave única: (organization_id, code)',
            'status debe ser: active, discontinued o new_launch',
            'organization_id se asigna automáticamente del usuario',
        ],
        column_aliases: {
            organization_id: ['organization_id', 'org_id', 'organization'],
            code: ['code', 'sku_code', 'sku', 'product_code', 'sku_id'],
            name: ['name', 'sku_name', 'product_name', 'description'],
            category: ['category', 'categoria'],
            family: ['family', 'familia'],
            brand: ['brand', 'marca'],
            status: ['status', 'estado'],
            attributes: ['attributes', 'attrs', 'json_attributes'],
        },
    },
    {
        name: 'location',
        label: 'Ubicaciones',
        target_schema: 'public',
        required_columns: ['organization_id', 'location_code', 'location_name'],
        optional_columns: ['country', 'city', 'timezone', 'is_active', 'location_type'],
        unique_keys: ['organization_id', 'code'],
        enums: {},
        validation_hints: [
            'Clave única: (organization_id, location_code)',
            'organization_id se asigna automáticamente del usuario',
        ],
        column_aliases: {
            organization_id: ['organization_id', 'org_id', 'organization'],
            location_code: ['location_code', 'code', 'loc_code', 'location_id'],
            location_name: ['location_name', 'name', 'location', 'store_name'],
            country: ['country', 'pais', 'país'],
            city: ['city', 'ciudad'],
            timezone: ['timezone', 'tz'],
            is_active: ['is_active', 'active', 'status'],
            location_type: ['location_type', 'loc_type', 'loc_tyoe', 'type'],
        },
    },
];
