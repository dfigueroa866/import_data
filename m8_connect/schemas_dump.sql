--
-- PostgreSQL database dump
--

\restrict pLGuBlyucUpvvULjxbLPmxK7gf4wNWPzaJcv6xXR5JooTfc1qePNMAB3OLaihj5

-- Dumped from database version 17.6
-- Dumped by pg_dump version 17.9 (Debian 17.9-1.pgdg13+1)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET transaction_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: fulfillment; Type: SCHEMA; Schema: -; Owner: postgres
--

CREATE SCHEMA fulfillment;


ALTER SCHEMA fulfillment OWNER TO postgres;

--
-- Name: m8_schema; Type: SCHEMA; Schema: -; Owner: postgres
--

CREATE SCHEMA m8_schema;


ALTER SCHEMA m8_schema OWNER TO postgres;

--
-- Name: public; Type: SCHEMA; Schema: -; Owner: pg_database_owner
--

CREATE SCHEMA public;


ALTER SCHEMA public OWNER TO pg_database_owner;

--
-- Name: SCHEMA public; Type: COMMENT; Schema: -; Owner: pg_database_owner
--

COMMENT ON SCHEMA public IS 'standard public schema';


--
-- Name: ApprovalStatus; Type: TYPE; Schema: public; Owner: postgres
--

CREATE TYPE public."ApprovalStatus" AS ENUM (
    'pending',
    'approved',
    'rejected'
);


ALTER TYPE public."ApprovalStatus" OWNER TO postgres;

--
-- Name: CycleStatus; Type: TYPE; Schema: public; Owner: postgres
--

CREATE TYPE public."CycleStatus" AS ENUM (
    'draft',
    'active',
    'locked'
);


ALTER TYPE public."CycleStatus" OWNER TO postgres;

--
-- Name: ForecastRunStatus; Type: TYPE; Schema: public; Owner: postgres
--

CREATE TYPE public."ForecastRunStatus" AS ENUM (
    'pending',
    'running',
    'complete',
    'failed'
);


ALTER TYPE public."ForecastRunStatus" OWNER TO postgres;

--
-- Name: OverrideDriver; Type: TYPE; Schema: public; Owner: postgres
--

CREATE TYPE public."OverrideDriver" AS ENUM (
    'promo',
    'price',
    'event',
    'new_listing',
    'other'
);


ALTER TYPE public."OverrideDriver" OWNER TO postgres;

--
-- Name: SegmentType; Type: TYPE; Schema: public; Owner: postgres
--

CREATE TYPE public."SegmentType" AS ENUM (
    'intermittent',
    'discontinued',
    'new_launch',
    'mature_x',
    'mature_yb',
    'mature_ya_trend',
    'mature_ya_season',
    'no_match'
);


ALTER TYPE public."SegmentType" OWNER TO postgres;

--
-- Name: SkuStatus; Type: TYPE; Schema: public; Owner: postgres
--

CREATE TYPE public."SkuStatus" AS ENUM (
    'active',
    'discontinued',
    'new_launch'
);


ALTER TYPE public."SkuStatus" OWNER TO postgres;

--
-- Name: UserRole; Type: TYPE; Schema: public; Owner: postgres
--

CREATE TYPE public."UserRole" AS ENUM (
    'admin',
    'manager',
    'planner',
    'viewer'
);


ALTER TYPE public."UserRole" OWNER TO postgres;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: upload_logs; Type: TABLE; Schema: m8_schema; Owner: postgres
--

CREATE TABLE m8_schema.upload_logs (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    company_name text NOT NULL,
    module text NOT NULL,
    file_type text NOT NULL,
    status text NOT NULL,
    error_details text,
    created_at timestamp with time zone DEFAULT now()
);


ALTER TABLE m8_schema.upload_logs OWNER TO postgres;

--
-- Name: _prisma_migrations; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public._prisma_migrations (
    id character varying(36) NOT NULL,
    checksum character varying(64) NOT NULL,
    finished_at timestamp with time zone,
    migration_name character varying(255) NOT NULL,
    logs text,
    rolled_back_at timestamp with time zone,
    started_at timestamp with time zone DEFAULT now() NOT NULL,
    applied_steps_count integer DEFAULT 0 NOT NULL
);


ALTER TABLE public._prisma_migrations OWNER TO postgres;

--
-- Name: approvals; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.approvals (
    id text NOT NULL,
    cycle_id text NOT NULL,
    search_id text NOT NULL,
    organization_id text NOT NULL,
    submitted_by text NOT NULL,
    submitted_at timestamp(3) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    reviewed_by text,
    reviewed_at timestamp(3) without time zone,
    status public."ApprovalStatus" DEFAULT 'pending'::public."ApprovalStatus" NOT NULL,
    comment text
);


ALTER TABLE public.approvals OWNER TO postgres;

--
-- Name: audit_log; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.audit_log (
    id text NOT NULL,
    organization_id text NOT NULL,
    user_id text NOT NULL,
    action text NOT NULL,
    entity_type text NOT NULL,
    entity_id text NOT NULL,
    before jsonb,
    after jsonb,
    created_at timestamp(3) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL
);


ALTER TABLE public.audit_log OWNER TO postgres;

--
-- Name: comments; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.comments (
    id text NOT NULL,
    organization_id text NOT NULL,
    user_id text NOT NULL,
    entity_type text NOT NULL,
    entity_id text NOT NULL,
    body text NOT NULL,
    mentions text[],
    created_at timestamp(3) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    edited_at timestamp(3) without time zone
);


ALTER TABLE public.comments OWNER TO postgres;

--
-- Name: company_config; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.company_config (
    id bigint NOT NULL,
    company_name text DEFAULT 'My Company'::text NOT NULL,
    company_logo_url text,
    company_description text,
    currency_code text DEFAULT 'USD'::text NOT NULL,
    currency_symbol text DEFAULT '$'::text NOT NULL,
    timezone text DEFAULT 'UTC'::text NOT NULL,
    country_code text,
    language_code text DEFAULT 'en'::text NOT NULL,
    planning_horizon_days integer DEFAULT 90 NOT NULL,
    planning_horizon_weeks integer DEFAULT 13 NOT NULL,
    planning_frequency text DEFAULT 'weekly'::text NOT NULL,
    distance_unit text DEFAULT 'km'::text NOT NULL,
    inventory_valuation_method text DEFAULT 'FIFO'::text NOT NULL,
    enable_multi_echelon boolean DEFAULT true NOT NULL,
    forecast_update_frequency text DEFAULT 'weekly'::text NOT NULL,
    enable_alerts boolean DEFAULT true NOT NULL,
    system_date date,
    CONSTRAINT company_config_single_row CHECK ((id = 1))
);


ALTER TABLE public.company_config OWNER TO postgres;

--
-- Name: company_config_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.company_config_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.company_config_id_seq OWNER TO postgres;

--
-- Name: company_config_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.company_config_id_seq OWNED BY public.company_config.id;


--
-- Name: consensus; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.consensus (
    id text NOT NULL,
    cycle_id text NOT NULL,
    search_id text NOT NULL,
    organization_id text NOT NULL,
    sku_id uuid NOT NULL,
    period_start timestamp(3) without time zone NOT NULL,
    granularity text NOT NULL,
    final_qty double precision NOT NULL,
    source text NOT NULL,
    approved_by text NOT NULL,
    approved_at timestamp(3) without time zone NOT NULL
);


ALTER TABLE public.consensus OWNER TO postgres;

--
-- Name: cycles; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.cycles (
    id text NOT NULL,
    organization_id text NOT NULL,
    name text NOT NULL,
    period_label text NOT NULL,
    status public."CycleStatus" DEFAULT 'draft'::public."CycleStatus" NOT NULL,
    phases jsonb NOT NULL,
    forecast_run_id text,
    created_by text NOT NULL,
    locked_at timestamp(3) without time zone,
    locked_by text,
    created_at timestamp(3) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL
);


ALTER TABLE public.cycles OWNER TO postgres;

--
-- Name: forecast_results; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.forecast_results (
    id text NOT NULL,
    run_id text NOT NULL,
    sku_id uuid NOT NULL,
    organization_id text NOT NULL,
    period_start timestamp(3) without time zone NOT NULL,
    granularity text NOT NULL,
    model_used text NOT NULL,
    mape double precision,
    rmse double precision,
    bias double precision,
    forecast_accuracy double precision,
    baseline_qty double precision NOT NULL,
    model_ranking jsonb
);


ALTER TABLE public.forecast_results OWNER TO postgres;

--
-- Name: forecast_runs; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.forecast_runs (
    id text NOT NULL,
    organization_id text NOT NULL,
    triggered_by text NOT NULL,
    status public."ForecastRunStatus" DEFAULT 'pending'::public."ForecastRunStatus" NOT NULL,
    parameters jsonb,
    run_at timestamp(3) without time zone,
    created_at timestamp(3) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL
);


ALTER TABLE public.forecast_runs OWNER TO postgres;

--
-- Name: location; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.location (
    id text DEFAULT (gen_random_uuid())::text NOT NULL,
    organization_id text NOT NULL,
    location_name character varying(200) NOT NULL,
    location_code character varying(200) NOT NULL,
    country character varying(100) DEFAULT 'Desconocido'::character varying NOT NULL,
    city character varying(100),
    timezone character varying(50) DEFAULT 'UTC'::character varying NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    location_type character varying(100)
);


ALTER TABLE public.location OWNER TO postgres;

--
-- Name: notifications; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.notifications (
    id text NOT NULL,
    organization_id text NOT NULL,
    user_id text NOT NULL,
    type text NOT NULL,
    payload jsonb NOT NULL,
    read_at timestamp(3) without time zone,
    created_at timestamp(3) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL
);


ALTER TABLE public.notifications OWNER TO postgres;

--
-- Name: organization_data_modules; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.organization_data_modules (
    id text NOT NULL,
    organization_id text NOT NULL,
    sales_data bigint DEFAULT 0 NOT NULL,
    promo_data bigint DEFAULT 0 NOT NULL,
    products bigint DEFAULT 0 NOT NULL,
    locations bigint DEFAULT 0 NOT NULL,
    inventory bigint DEFAULT 0 NOT NULL,
    demand_module bigint DEFAULT 0 NOT NULL,
    fulfillment_module bigint DEFAULT 0 NOT NULL,
    master_plan_module bigint DEFAULT 0 NOT NULL,
    created_at timestamp(3) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at timestamp(3) without time zone NOT NULL
);


ALTER TABLE public.organization_data_modules OWNER TO postgres;

--
-- Name: organizations; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.organizations (
    id text NOT NULL,
    name text NOT NULL,
    slug text NOT NULL,
    plan text DEFAULT 'starter'::text NOT NULL,
    created_at timestamp(3) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL
);


ALTER TABLE public.organizations OWNER TO postgres;

--
-- Name: overrides; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.overrides (
    id text NOT NULL,
    organization_id text NOT NULL,
    cycle_id text NOT NULL,
    search_id text NOT NULL,
    sku_id uuid NOT NULL,
    user_id text NOT NULL,
    period_start timestamp(3) without time zone NOT NULL,
    granularity text NOT NULL,
    baseline_qty double precision NOT NULL,
    override_qty double precision NOT NULL,
    delta_pct double precision NOT NULL,
    driver public."OverrideDriver" DEFAULT 'other'::public."OverrideDriver" NOT NULL,
    justification text NOT NULL,
    version integer DEFAULT 1 NOT NULL,
    created_at timestamp(3) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at timestamp(3) without time zone NOT NULL
);


ALTER TABLE public.overrides OWNER TO postgres;

--
-- Name: sales_history; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.sales_history (
    id text NOT NULL,
    sku_id uuid NOT NULL,
    period_start timestamp(3) without time zone NOT NULL,
    granularity text NOT NULL,
    quantity double precision NOT NULL,
    source text DEFAULT 'csv'::text NOT NULL,
    organization_id text,
    location_code text
);


ALTER TABLE public.sales_history OWNER TO postgres;

--
-- Name: search_assignments; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.search_assignments (
    search_id text NOT NULL,
    user_id text NOT NULL,
    can_override boolean DEFAULT true NOT NULL
);


ALTER TABLE public.search_assignments OWNER TO postgres;

--
-- Name: searches; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.searches (
    id text NOT NULL,
    organization_id text NOT NULL,
    name text NOT NULL,
    filter_definition jsonb NOT NULL,
    created_by text NOT NULL,
    created_at timestamp(3) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL
);


ALTER TABLE public.searches OWNER TO postgres;

--
-- Name: segments; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.segments (
    id text NOT NULL,
    sku_id uuid NOT NULL,
    organization_id text NOT NULL,
    segment_type public."SegmentType" NOT NULL,
    confidence double precision,
    override_reason text,
    overridden_by text,
    overridden_at timestamp(3) without time zone,
    segment_history jsonb,
    created_at timestamp(3) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL
);


ALTER TABLE public.segments OWNER TO postgres;

--
-- Name: skus; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.skus (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    organization_id text NOT NULL,
    code text NOT NULL,
    name text NOT NULL,
    category text,
    family text,
    brand text,
    status public."SkuStatus" DEFAULT 'active'::public."SkuStatus" NOT NULL,
    attributes jsonb
);


ALTER TABLE public.skus OWNER TO postgres;

--
-- Name: users; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.users (
    id text NOT NULL,
    organization_id text NOT NULL,
    email text NOT NULL,
    display_name text NOT NULL,
    avatar_url text,
    role public."UserRole" DEFAULT 'planner'::public."UserRole" NOT NULL,
    created_at timestamp(3) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    supabase_id text,
    password_hash text
);


ALTER TABLE public.users OWNER TO postgres;

--
-- Name: v_sales_history; Type: VIEW; Schema: public; Owner: postgres
--

CREATE VIEW public.v_sales_history AS
 SELECT sales_history.id,
    sales_history.sku_id,
    sales_history.period_start,
    sales_history.granularity,
    sales_history.quantity,
    sales_history.source,
    sales_history.organization_id,
    sales_history.location_code,
    skus.code
   FROM (public.sales_history
     JOIN public.skus ON ((sales_history.sku_id = skus.id)));


ALTER VIEW public.v_sales_history OWNER TO postgres;

--
-- Name: company_config id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.company_config ALTER COLUMN id SET DEFAULT nextval('public.company_config_id_seq'::regclass);


--
-- Name: upload_logs upload_logs_pkey; Type: CONSTRAINT; Schema: m8_schema; Owner: postgres
--

ALTER TABLE ONLY m8_schema.upload_logs
    ADD CONSTRAINT upload_logs_pkey PRIMARY KEY (id);


--
-- Name: _prisma_migrations _prisma_migrations_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public._prisma_migrations
    ADD CONSTRAINT _prisma_migrations_pkey PRIMARY KEY (id);


--
-- Name: approvals approvals_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.approvals
    ADD CONSTRAINT approvals_pkey PRIMARY KEY (id);


--
-- Name: audit_log audit_log_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.audit_log
    ADD CONSTRAINT audit_log_pkey PRIMARY KEY (id);


--
-- Name: comments comments_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.comments
    ADD CONSTRAINT comments_pkey PRIMARY KEY (id);


--
-- Name: company_config company_config_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.company_config
    ADD CONSTRAINT company_config_pkey PRIMARY KEY (id);


--
-- Name: consensus consensus_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.consensus
    ADD CONSTRAINT consensus_pkey PRIMARY KEY (id);


--
-- Name: cycles cycles_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.cycles
    ADD CONSTRAINT cycles_pkey PRIMARY KEY (id);


--
-- Name: forecast_results forecast_results_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.forecast_results
    ADD CONSTRAINT forecast_results_pkey PRIMARY KEY (id);


--
-- Name: forecast_runs forecast_runs_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.forecast_runs
    ADD CONSTRAINT forecast_runs_pkey PRIMARY KEY (id);


--
-- Name: location location_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.location
    ADD CONSTRAINT location_pkey PRIMARY KEY (id);


--
-- Name: notifications notifications_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.notifications
    ADD CONSTRAINT notifications_pkey PRIMARY KEY (id);


--
-- Name: organization_data_modules organization_data_modules_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.organization_data_modules
    ADD CONSTRAINT organization_data_modules_pkey PRIMARY KEY (id);


--
-- Name: organizations organizations_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.organizations
    ADD CONSTRAINT organizations_pkey PRIMARY KEY (id);


--
-- Name: overrides overrides_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.overrides
    ADD CONSTRAINT overrides_pkey PRIMARY KEY (id);


--
-- Name: sales_history sales_history_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.sales_history
    ADD CONSTRAINT sales_history_pkey PRIMARY KEY (id);


--
-- Name: search_assignments search_assignments_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.search_assignments
    ADD CONSTRAINT search_assignments_pkey PRIMARY KEY (search_id, user_id);


--
-- Name: searches searches_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.searches
    ADD CONSTRAINT searches_pkey PRIMARY KEY (id);


--
-- Name: segments segments_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.segments
    ADD CONSTRAINT segments_pkey PRIMARY KEY (id);


--
-- Name: skus skus_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.skus
    ADD CONSTRAINT skus_pkey PRIMARY KEY (id);


--
-- Name: users users_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (id);


--
-- Name: approvals_cycle_id_search_id_key; Type: INDEX; Schema: public; Owner: postgres
--

CREATE UNIQUE INDEX approvals_cycle_id_search_id_key ON public.approvals USING btree (cycle_id, search_id);


--
-- Name: audit_log_organization_id_entity_type_entity_id_idx; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX audit_log_organization_id_entity_type_entity_id_idx ON public.audit_log USING btree (organization_id, entity_type, entity_id);


--
-- Name: comments_organization_id_entity_type_entity_id_idx; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX comments_organization_id_entity_type_entity_id_idx ON public.comments USING btree (organization_id, entity_type, entity_id);


--
-- Name: consensus_cycle_id_sku_id_period_start_granularity_key; Type: INDEX; Schema: public; Owner: postgres
--

CREATE UNIQUE INDEX consensus_cycle_id_sku_id_period_start_granularity_key ON public.consensus USING btree (cycle_id, sku_id, period_start, granularity);


--
-- Name: forecast_results_run_id_sku_id_period_start_granularity_key; Type: INDEX; Schema: public; Owner: postgres
--

CREATE UNIQUE INDEX forecast_results_run_id_sku_id_period_start_granularity_key ON public.forecast_results USING btree (run_id, sku_id, period_start, granularity);


--
-- Name: location_organization_id_location_code_key; Type: INDEX; Schema: public; Owner: postgres
--

CREATE UNIQUE INDEX location_organization_id_location_code_key ON public.location USING btree (organization_id, location_code);


--
-- Name: notifications_user_id_read_at_idx; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX notifications_user_id_read_at_idx ON public.notifications USING btree (user_id, read_at);


--
-- Name: organization_data_modules_organization_id_key; Type: INDEX; Schema: public; Owner: postgres
--

CREATE UNIQUE INDEX organization_data_modules_organization_id_key ON public.organization_data_modules USING btree (organization_id);


--
-- Name: organizations_slug_key; Type: INDEX; Schema: public; Owner: postgres
--

CREATE UNIQUE INDEX organizations_slug_key ON public.organizations USING btree (slug);


--
-- Name: overrides_cycle_id_sku_id_period_start_granularity_key; Type: INDEX; Schema: public; Owner: postgres
--

CREATE UNIQUE INDEX overrides_cycle_id_sku_id_period_start_granularity_key ON public.overrides USING btree (cycle_id, sku_id, period_start, granularity);


--
-- Name: sales_history_sku_id_period_start_granularity_key; Type: INDEX; Schema: public; Owner: postgres
--

CREATE UNIQUE INDEX sales_history_sku_id_period_start_granularity_key ON public.sales_history USING btree (sku_id, period_start, granularity);


--
-- Name: skus_organization_id_code_key; Type: INDEX; Schema: public; Owner: postgres
--

CREATE UNIQUE INDEX skus_organization_id_code_key ON public.skus USING btree (organization_id, code);


--
-- Name: users_organization_id_email_key; Type: INDEX; Schema: public; Owner: postgres
--

CREATE UNIQUE INDEX users_organization_id_email_key ON public.users USING btree (organization_id, email);


--
-- Name: users_supabase_id_key; Type: INDEX; Schema: public; Owner: postgres
--

CREATE UNIQUE INDEX users_supabase_id_key ON public.users USING btree (supabase_id);


--
-- Name: approvals approvals_cycle_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.approvals
    ADD CONSTRAINT approvals_cycle_id_fkey FOREIGN KEY (cycle_id) REFERENCES public.cycles(id) ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: approvals approvals_organization_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.approvals
    ADD CONSTRAINT approvals_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES public.organizations(id) ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: approvals approvals_search_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.approvals
    ADD CONSTRAINT approvals_search_id_fkey FOREIGN KEY (search_id) REFERENCES public.searches(id) ON UPDATE CASCADE ON DELETE RESTRICT;


--
-- Name: approvals approvals_submitted_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.approvals
    ADD CONSTRAINT approvals_submitted_by_fkey FOREIGN KEY (submitted_by) REFERENCES public.users(id) ON UPDATE CASCADE ON DELETE RESTRICT;


--
-- Name: audit_log audit_log_organization_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.audit_log
    ADD CONSTRAINT audit_log_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES public.organizations(id) ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: audit_log audit_log_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.audit_log
    ADD CONSTRAINT audit_log_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON UPDATE CASCADE ON DELETE RESTRICT;


--
-- Name: comments comments_organization_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.comments
    ADD CONSTRAINT comments_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES public.organizations(id) ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: comments comments_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.comments
    ADD CONSTRAINT comments_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON UPDATE CASCADE ON DELETE RESTRICT;


--
-- Name: consensus consensus_cycle_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.consensus
    ADD CONSTRAINT consensus_cycle_id_fkey FOREIGN KEY (cycle_id) REFERENCES public.cycles(id) ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: consensus consensus_organization_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.consensus
    ADD CONSTRAINT consensus_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES public.organizations(id) ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: consensus consensus_search_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.consensus
    ADD CONSTRAINT consensus_search_id_fkey FOREIGN KEY (search_id) REFERENCES public.searches(id) ON UPDATE CASCADE ON DELETE RESTRICT;


--
-- Name: cycles cycles_forecast_run_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.cycles
    ADD CONSTRAINT cycles_forecast_run_id_fkey FOREIGN KEY (forecast_run_id) REFERENCES public.forecast_runs(id) ON UPDATE CASCADE ON DELETE SET NULL;


--
-- Name: cycles cycles_organization_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.cycles
    ADD CONSTRAINT cycles_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES public.organizations(id) ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: forecast_results forecast_results_run_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.forecast_results
    ADD CONSTRAINT forecast_results_run_id_fkey FOREIGN KEY (run_id) REFERENCES public.forecast_runs(id) ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: forecast_runs forecast_runs_organization_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.forecast_runs
    ADD CONSTRAINT forecast_runs_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES public.organizations(id) ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: location location_organization_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.location
    ADD CONSTRAINT location_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES public.organizations(id) ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: notifications notifications_organization_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.notifications
    ADD CONSTRAINT notifications_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES public.organizations(id) ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: notifications notifications_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.notifications
    ADD CONSTRAINT notifications_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON UPDATE CASCADE ON DELETE RESTRICT;


--
-- Name: organization_data_modules organization_data_modules_organization_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.organization_data_modules
    ADD CONSTRAINT organization_data_modules_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES public.organizations(id) ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: overrides overrides_cycle_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.overrides
    ADD CONSTRAINT overrides_cycle_id_fkey FOREIGN KEY (cycle_id) REFERENCES public.cycles(id) ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: overrides overrides_organization_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.overrides
    ADD CONSTRAINT overrides_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES public.organizations(id) ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: overrides overrides_search_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.overrides
    ADD CONSTRAINT overrides_search_id_fkey FOREIGN KEY (search_id) REFERENCES public.searches(id) ON UPDATE CASCADE ON DELETE RESTRICT;


--
-- Name: overrides overrides_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.overrides
    ADD CONSTRAINT overrides_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON UPDATE CASCADE ON DELETE RESTRICT;


--
-- Name: sales_history sales_history_sku_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.sales_history
    ADD CONSTRAINT sales_history_sku_id_fkey FOREIGN KEY (sku_id) REFERENCES public.skus(id);


--
-- Name: search_assignments search_assignments_search_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.search_assignments
    ADD CONSTRAINT search_assignments_search_id_fkey FOREIGN KEY (search_id) REFERENCES public.searches(id) ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: search_assignments search_assignments_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.search_assignments
    ADD CONSTRAINT search_assignments_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: searches searches_organization_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.searches
    ADD CONSTRAINT searches_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES public.organizations(id) ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: skus skus_organization_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.skus
    ADD CONSTRAINT skus_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES public.organizations(id) ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: users users_organization_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES public.organizations(id) ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: company_config Authenticated users can CRUD; Type: POLICY; Schema: public; Owner: postgres
--

CREATE POLICY "Authenticated users can CRUD" ON public.company_config USING (true) WITH CHECK (true);


--
-- Name: company_config; Type: ROW SECURITY; Schema: public; Owner: postgres
--

ALTER TABLE public.company_config ENABLE ROW LEVEL SECURITY;

--
-- Name: SCHEMA m8_schema; Type: ACL; Schema: -; Owner: postgres
--

GRANT USAGE ON SCHEMA m8_schema TO authenticated;
GRANT USAGE ON SCHEMA m8_schema TO anon;
GRANT USAGE ON SCHEMA m8_schema TO service_role;


--
-- Name: SCHEMA public; Type: ACL; Schema: -; Owner: pg_database_owner
--

GRANT USAGE ON SCHEMA public TO postgres;
GRANT USAGE ON SCHEMA public TO anon;
GRANT USAGE ON SCHEMA public TO authenticated;
GRANT USAGE ON SCHEMA public TO service_role;


--
-- Name: TABLE upload_logs; Type: ACL; Schema: m8_schema; Owner: postgres
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE m8_schema.upload_logs TO anon;
GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE m8_schema.upload_logs TO authenticated;


--
-- Name: TABLE _prisma_migrations; Type: ACL; Schema: public; Owner: postgres
--

GRANT ALL ON TABLE public._prisma_migrations TO anon;
GRANT ALL ON TABLE public._prisma_migrations TO authenticated;
GRANT ALL ON TABLE public._prisma_migrations TO service_role;


--
-- Name: TABLE approvals; Type: ACL; Schema: public; Owner: postgres
--

GRANT ALL ON TABLE public.approvals TO anon;
GRANT ALL ON TABLE public.approvals TO authenticated;
GRANT ALL ON TABLE public.approvals TO service_role;


--
-- Name: TABLE audit_log; Type: ACL; Schema: public; Owner: postgres
--

GRANT ALL ON TABLE public.audit_log TO anon;
GRANT ALL ON TABLE public.audit_log TO authenticated;
GRANT ALL ON TABLE public.audit_log TO service_role;


--
-- Name: TABLE comments; Type: ACL; Schema: public; Owner: postgres
--

GRANT ALL ON TABLE public.comments TO anon;
GRANT ALL ON TABLE public.comments TO authenticated;
GRANT ALL ON TABLE public.comments TO service_role;


--
-- Name: TABLE company_config; Type: ACL; Schema: public; Owner: postgres
--

GRANT ALL ON TABLE public.company_config TO anon;
GRANT ALL ON TABLE public.company_config TO authenticated;
GRANT ALL ON TABLE public.company_config TO service_role;


--
-- Name: SEQUENCE company_config_id_seq; Type: ACL; Schema: public; Owner: postgres
--

GRANT ALL ON SEQUENCE public.company_config_id_seq TO anon;
GRANT ALL ON SEQUENCE public.company_config_id_seq TO authenticated;
GRANT ALL ON SEQUENCE public.company_config_id_seq TO service_role;


--
-- Name: TABLE consensus; Type: ACL; Schema: public; Owner: postgres
--

GRANT ALL ON TABLE public.consensus TO anon;
GRANT ALL ON TABLE public.consensus TO authenticated;
GRANT ALL ON TABLE public.consensus TO service_role;


--
-- Name: TABLE cycles; Type: ACL; Schema: public; Owner: postgres
--

GRANT ALL ON TABLE public.cycles TO anon;
GRANT ALL ON TABLE public.cycles TO authenticated;
GRANT ALL ON TABLE public.cycles TO service_role;


--
-- Name: TABLE forecast_results; Type: ACL; Schema: public; Owner: postgres
--

GRANT ALL ON TABLE public.forecast_results TO anon;
GRANT ALL ON TABLE public.forecast_results TO authenticated;
GRANT ALL ON TABLE public.forecast_results TO service_role;


--
-- Name: TABLE forecast_runs; Type: ACL; Schema: public; Owner: postgres
--

GRANT ALL ON TABLE public.forecast_runs TO anon;
GRANT ALL ON TABLE public.forecast_runs TO authenticated;
GRANT ALL ON TABLE public.forecast_runs TO service_role;


--
-- Name: TABLE location; Type: ACL; Schema: public; Owner: postgres
--

GRANT ALL ON TABLE public.location TO anon;
GRANT ALL ON TABLE public.location TO authenticated;
GRANT ALL ON TABLE public.location TO service_role;


--
-- Name: TABLE notifications; Type: ACL; Schema: public; Owner: postgres
--

GRANT ALL ON TABLE public.notifications TO anon;
GRANT ALL ON TABLE public.notifications TO authenticated;
GRANT ALL ON TABLE public.notifications TO service_role;


--
-- Name: TABLE organization_data_modules; Type: ACL; Schema: public; Owner: postgres
--

GRANT ALL ON TABLE public.organization_data_modules TO anon;
GRANT ALL ON TABLE public.organization_data_modules TO authenticated;
GRANT ALL ON TABLE public.organization_data_modules TO service_role;


--
-- Name: TABLE organizations; Type: ACL; Schema: public; Owner: postgres
--

GRANT ALL ON TABLE public.organizations TO anon;
GRANT ALL ON TABLE public.organizations TO authenticated;
GRANT ALL ON TABLE public.organizations TO service_role;


--
-- Name: TABLE overrides; Type: ACL; Schema: public; Owner: postgres
--

GRANT ALL ON TABLE public.overrides TO anon;
GRANT ALL ON TABLE public.overrides TO authenticated;
GRANT ALL ON TABLE public.overrides TO service_role;


--
-- Name: TABLE sales_history; Type: ACL; Schema: public; Owner: postgres
--

GRANT ALL ON TABLE public.sales_history TO anon;
GRANT ALL ON TABLE public.sales_history TO authenticated;
GRANT ALL ON TABLE public.sales_history TO service_role;


--
-- Name: TABLE search_assignments; Type: ACL; Schema: public; Owner: postgres
--

GRANT ALL ON TABLE public.search_assignments TO anon;
GRANT ALL ON TABLE public.search_assignments TO authenticated;
GRANT ALL ON TABLE public.search_assignments TO service_role;


--
-- Name: TABLE searches; Type: ACL; Schema: public; Owner: postgres
--

GRANT ALL ON TABLE public.searches TO anon;
GRANT ALL ON TABLE public.searches TO authenticated;
GRANT ALL ON TABLE public.searches TO service_role;


--
-- Name: TABLE segments; Type: ACL; Schema: public; Owner: postgres
--

GRANT ALL ON TABLE public.segments TO anon;
GRANT ALL ON TABLE public.segments TO authenticated;
GRANT ALL ON TABLE public.segments TO service_role;


--
-- Name: TABLE skus; Type: ACL; Schema: public; Owner: postgres
--

GRANT ALL ON TABLE public.skus TO anon;
GRANT ALL ON TABLE public.skus TO authenticated;
GRANT ALL ON TABLE public.skus TO service_role;


--
-- Name: TABLE users; Type: ACL; Schema: public; Owner: postgres
--

GRANT ALL ON TABLE public.users TO anon;
GRANT ALL ON TABLE public.users TO authenticated;
GRANT ALL ON TABLE public.users TO service_role;


--
-- Name: TABLE v_sales_history; Type: ACL; Schema: public; Owner: postgres
--

GRANT ALL ON TABLE public.v_sales_history TO anon;
GRANT ALL ON TABLE public.v_sales_history TO authenticated;
GRANT ALL ON TABLE public.v_sales_history TO service_role;


--
-- Name: DEFAULT PRIVILEGES FOR SEQUENCES; Type: DEFAULT ACL; Schema: m8_schema; Owner: postgres
--

ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA m8_schema GRANT USAGE ON SEQUENCES TO anon;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA m8_schema GRANT USAGE ON SEQUENCES TO authenticated;


--
-- Name: DEFAULT PRIVILEGES FOR TABLES; Type: DEFAULT ACL; Schema: m8_schema; Owner: postgres
--

ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA m8_schema GRANT SELECT,INSERT,DELETE,UPDATE ON TABLES TO anon;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA m8_schema GRANT SELECT,INSERT,DELETE,UPDATE ON TABLES TO authenticated;


--
-- Name: DEFAULT PRIVILEGES FOR SEQUENCES; Type: DEFAULT ACL; Schema: public; Owner: postgres
--

ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public GRANT ALL ON SEQUENCES TO postgres;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public GRANT ALL ON SEQUENCES TO anon;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public GRANT ALL ON SEQUENCES TO authenticated;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public GRANT ALL ON SEQUENCES TO service_role;


--
-- Name: DEFAULT PRIVILEGES FOR SEQUENCES; Type: DEFAULT ACL; Schema: public; Owner: supabase_admin
--

ALTER DEFAULT PRIVILEGES FOR ROLE supabase_admin IN SCHEMA public GRANT ALL ON SEQUENCES TO postgres;
ALTER DEFAULT PRIVILEGES FOR ROLE supabase_admin IN SCHEMA public GRANT ALL ON SEQUENCES TO anon;
ALTER DEFAULT PRIVILEGES FOR ROLE supabase_admin IN SCHEMA public GRANT ALL ON SEQUENCES TO authenticated;
ALTER DEFAULT PRIVILEGES FOR ROLE supabase_admin IN SCHEMA public GRANT ALL ON SEQUENCES TO service_role;


--
-- Name: DEFAULT PRIVILEGES FOR FUNCTIONS; Type: DEFAULT ACL; Schema: public; Owner: postgres
--

ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public GRANT ALL ON FUNCTIONS TO postgres;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public GRANT ALL ON FUNCTIONS TO anon;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public GRANT ALL ON FUNCTIONS TO authenticated;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public GRANT ALL ON FUNCTIONS TO service_role;


--
-- Name: DEFAULT PRIVILEGES FOR FUNCTIONS; Type: DEFAULT ACL; Schema: public; Owner: supabase_admin
--

ALTER DEFAULT PRIVILEGES FOR ROLE supabase_admin IN SCHEMA public GRANT ALL ON FUNCTIONS TO postgres;
ALTER DEFAULT PRIVILEGES FOR ROLE supabase_admin IN SCHEMA public GRANT ALL ON FUNCTIONS TO anon;
ALTER DEFAULT PRIVILEGES FOR ROLE supabase_admin IN SCHEMA public GRANT ALL ON FUNCTIONS TO authenticated;
ALTER DEFAULT PRIVILEGES FOR ROLE supabase_admin IN SCHEMA public GRANT ALL ON FUNCTIONS TO service_role;


--
-- Name: DEFAULT PRIVILEGES FOR TABLES; Type: DEFAULT ACL; Schema: public; Owner: postgres
--

ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public GRANT ALL ON TABLES TO postgres;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public GRANT ALL ON TABLES TO anon;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public GRANT ALL ON TABLES TO authenticated;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public GRANT ALL ON TABLES TO service_role;


--
-- Name: DEFAULT PRIVILEGES FOR TABLES; Type: DEFAULT ACL; Schema: public; Owner: supabase_admin
--

ALTER DEFAULT PRIVILEGES FOR ROLE supabase_admin IN SCHEMA public GRANT ALL ON TABLES TO postgres;
ALTER DEFAULT PRIVILEGES FOR ROLE supabase_admin IN SCHEMA public GRANT ALL ON TABLES TO anon;
ALTER DEFAULT PRIVILEGES FOR ROLE supabase_admin IN SCHEMA public GRANT ALL ON TABLES TO authenticated;
ALTER DEFAULT PRIVILEGES FOR ROLE supabase_admin IN SCHEMA public GRANT ALL ON TABLES TO service_role;


--
-- PostgreSQL database dump complete
--

\unrestrict pLGuBlyucUpvvULjxbLPmxK7gf4wNWPzaJcv6xXR5JooTfc1qePNMAB3OLaihj5

