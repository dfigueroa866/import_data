create table m8_schema.products (
  product_id character varying(50) not null,
  product_name character varying(255) not null,
  product_code character varying(100) null,
  category character varying(100) null,
  subcategory character varying(100) null,
  unit_of_measure character varying(50) null default 'units'::character varying,
  unit_cost numeric(10, 2) null,
  supplier_id character varying(50) null,
  supplier_name character varying(255) null,
  lead_time_days integer null default 14,
  minimum_order_quantity integer null default 1,
  is_active boolean null default true,
  created_at timestamp with time zone null default now(),
  updated_at timestamp with time zone null default now(),
  constraint products_pkey primary key (product_id),
  constraint products_product_code_key unique (product_code)
) TABLESPACE pg_default;

create index IF not exists idx_products_code on m8_schema.products using btree (product_code) TABLESPACE pg_default;

create index IF not exists idx_products_category on m8_schema.products using btree (category) TABLESPACE pg_default;

create trigger update_products_updated_at BEFORE
update on products for EACH row
execute FUNCTION update_updated_at_column ();