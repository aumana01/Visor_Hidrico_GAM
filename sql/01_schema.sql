-- Esquema base para la herramienta GAM Hídrico.
-- Ejecutar en Supabase SQL Editor antes de publicar la aplicación.

create table if not exists public.sistemas_clusters (
  sistema_nombre text primary key,
  cluster text,
  sistema_codigo text,
  sistema_codigo_formal text
);

create table if not exists public.proyectos (
  id bigserial primary key,
  accion text,
  bpip text,
  proyecto text not null,
  descripcion text,
  latitud double precision,
  longitud double precision,
  estado_iniciativa text,
  inicio_perforacion text,
  fin_perforacion text,
  tipo_incorporacion text,
  expectativa_caudal_lps double precision,
  caudal_temporal_lps double precision,
  poblacion_beneficiada_estimada double precision,
  anio_incorporacion_texto text,
  anio_efecto integer check (anio_efecto is null or anio_efecto between 2024 and 2040),
  sistema_codigo text,
  sistema_nombre text,
  cluster text,
  beneficios text,
  impacto text,
  actividades_criticas text,
  dependencia_responsable text,
  estudio_hidrogeologico text,
  situacion_terrenos text,
  activo_en_capacidad boolean default true,
  observaciones text,
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

create table if not exists public.capacidad_base (
  escenario text not null check (escenario in ('SIN_PAAM', 'CON_PAAM')),
  cluster text,
  cod text not null,
  sistema text not null,
  anio integer not null check (anio between 2024 and 2040),
  balance_lps double precision,
  primary key (escenario, cod, anio)
);

create table if not exists public.necesidades (
  id bigserial primary key,
  id_origen text,
  objetivo_de_la_iniciativa text,
  breve_descripcion text,
  tipo_de_proyecto text,
  codigo_de_sistema text,
  sistema_de_abastecimiento text,
  zona text,
  prioridad text,
  plazo text,
  costo text,
  estado text,
  principal_reto_por_superar text,
  observacion text,
  caudal_estimado_lps double precision,
  volumen_estimado_m3 double precision,
  km_estimado double precision,
  responsabilidad_atencion text,
  activo boolean default true,
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);


-- Compatibilidad para proyectos Supabase creados con versiones previas.
alter table if exists public.necesidades
  add column if not exists responsabilidad_atencion text;

alter table if exists public.necesidades
  add column if not exists caudal_estimado_lps double precision,
  add column if not exists volumen_estimado_m3 double precision,
  add column if not exists km_estimado double precision;

create table if not exists public.catalogo_tipos_proyecto (
  tipo_proyecto text primary key
);

create table if not exists public.catalogo_beneficios_impactos (
  "Beneficios" text,
  "Impacto" text,
  primary key ("Beneficios", "Impacto")
);

create table if not exists public.catalogo_actividades_criticas (
  "Actividades Críticas para su avance" text,
  "Actividades Críticas para su avance_2" text,
  primary key ("Actividades Críticas para su avance", "Actividades Críticas para su avance_2")
);

create table if not exists public.catalogo_plazos (
  "Plazo" text,
  "Plazo_2" text,
  primary key ("Plazo", "Plazo_2")
);

create table if not exists public.catalogo_situacion_terrenos (
  "Situación de terrenos" text primary key
);

create or replace function public.set_updated_at()
returns trigger as $$
begin
  new.updated_at = now();
  return new;
end;
$$ language plpgsql;

drop trigger if exists trg_proyectos_updated_at on public.proyectos;
create trigger trg_proyectos_updated_at
before update on public.proyectos
for each row execute function public.set_updated_at();

drop trigger if exists trg_necesidades_updated_at on public.necesidades;
create trigger trg_necesidades_updated_at
before update on public.necesidades
for each row execute function public.set_updated_at();

-- Índices para filtros frecuentes.
create index if not exists idx_proyectos_cluster on public.proyectos(cluster);
create index if not exists idx_proyectos_sistema on public.proyectos(sistema_nombre);
create index if not exists idx_proyectos_anio on public.proyectos(anio_efecto);
create index if not exists idx_capacidad_escenario_cluster_anio on public.capacidad_base(escenario, cluster, anio);
create index if not exists idx_necesidades_tipo on public.necesidades(tipo_de_proyecto);
create index if not exists idx_necesidades_sistema on public.necesidades(sistema_de_abastecimiento);
create index if not exists idx_necesidades_responsabilidad on public.necesidades(responsabilidad_atencion);

-- Seguridad / RLS:
-- Para una app institucional privada, lo más simple es usar una SERVICE_ROLE_KEY solo en secrets de Streamlit.
-- No subir esa llave a GitHub. Si se usa ANON_KEY, habilitar RLS y crear políticas específicas por usuario/rol.
