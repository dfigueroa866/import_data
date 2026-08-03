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
        { name: 'attr_1', type: 'character varying', is_primary_key: false, nullable: false },
        { name: 'created_at', type: 'timestamp without time zone', is_primary_key: false },
    ];

    it('classifies system columns', () => {
        expect(classifyCatalogColumn(schemaColumns[0])).toBe('organization');
        expect(classifyCatalogColumn(schemaColumns[1])).toBe('primary_key');
        expect(classifyCatalogColumn(schemaColumns[5])).toBe('audit');
        expect(classifyCatalogColumn(schemaColumns[2])).toBe('mappable');
    });

    it('seeds from DB NOT NULL only when no saved lists exist', () => {
        const map = buildColumnRequiredMap(schemaColumns, []);
        expect(map).toEqual({ code: true, city: false, attr_1: true });
    });

    it('uses saved config as bible and ignores DB NOT NULL for unset columns', () => {
        const map = buildColumnRequiredMap(
            schemaColumns,
            ['code'],
            ['city'],
            ['code']
        );
        // attr_1 is NOT NULL in DB but not in saved required/optional → optional
        expect(map).toEqual({ code: true, city: false, attr_1: false });
    });

    it('honors required_columns even if not in required_mapping_columns', () => {
        const map = buildColumnRequiredMap(
            schemaColumns,
            ['status'],
            ['city'],
            ['code', 'name']
        );
        expect(map.code).toBe(true);
        expect(map.city).toBe(false);
        expect(map.attr_1).toBe(false);
    });

    it('derives mapping fields from toggles', () => {
        const map = buildColumnRequiredMap(schemaColumns, []);
        const derived = deriveCatalogMappingFields(schemaColumns, map);
        expect(derived.required_mapping_columns).toEqual(['code', 'attr_1']);
        expect(derived.non_mappable_targets).toContain('organization_id');
        expect(derived.non_mappable_targets).toContain('location_id');
        expect(derived.non_mappable_targets).toContain('created_at');
        expect(derived.optional_columns).toEqual(['city']);
    });

    it('respects toggle map when saving derived fields', () => {
        const map = { code: false, city: false, attr_1: false };
        const derived = deriveCatalogMappingFields(schemaColumns, map);
        expect(derived.required_mapping_columns).toEqual([]);
        expect(derived.optional_columns).toEqual(['code', 'city', 'attr_1']);
    });

    it('persists defaults only when enabled with non-empty value', () => {
        const map = { code: true, city: false, attr_1: false };
        const derived = deriveCatalogMappingFields(
            schemaColumns,
            map,
            { code: false, city: false, attr_1: true },
            { attr_1: 'N/A', city: 'ignored' }
        );
        expect(derived.defaults).toEqual({ attr_1: 'N/A' });
        expect(derived.required_mapping_columns).toEqual(['code']);
    });
});
