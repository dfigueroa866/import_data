import { describe, it, expect } from 'vitest';
import {
    classifyCatalogColumn,
    buildColumnRequiredMap,
    deriveCatalogMappingFields,
} from '../utils/catalogColumnRules';

describe('catalogColumnRules', () => {
    const schemaColumns = [
        { name: 'organization_id', type: 'uuid', is_primary_key: false },
        { name: 'location_id', type: 'uuid', is_primary_key: true },
        { name: 'code', type: 'character varying', is_primary_key: false, nullable: false },
        { name: 'city', type: 'character varying', is_primary_key: false, nullable: true },
        { name: 'created_at', type: 'timestamp without time zone', is_primary_key: false },
    ];

    it('classifies system columns', () => {
        expect(classifyCatalogColumn(schemaColumns[0])).toBe('organization');
        expect(classifyCatalogColumn(schemaColumns[1])).toBe('primary_key');
        expect(classifyCatalogColumn(schemaColumns[4])).toBe('audit');
        expect(classifyCatalogColumn(schemaColumns[2])).toBe('mappable');
    });

    it('derives mapping fields from toggles', () => {
        const map = buildColumnRequiredMap(schemaColumns, []);
        expect(map).toEqual({ code: true, city: false });

        const derived = deriveCatalogMappingFields(schemaColumns, map);
        expect(derived.required_mapping_columns).toEqual(['code']);
        expect(derived.non_mappable_targets).toContain('organization_id');
        expect(derived.non_mappable_targets).toContain('location_id');
        expect(derived.non_mappable_targets).toContain('created_at');
        expect(derived.optional_columns).toEqual(['city']);
    });

    it('respects toggle map when saving derived fields', () => {
        const map = { code: false, city: false };
        const derived = deriveCatalogMappingFields(schemaColumns, map);
        expect(derived.required_mapping_columns).toEqual([]);
        expect(derived.optional_columns).toEqual(['code', 'city']);
    });

    it('restores optional NOT NULL from saved optional_columns', () => {
        const map = buildColumnRequiredMap(schemaColumns, [], ['code']);
        expect(map).toEqual({ code: false, city: false });
    });
});
