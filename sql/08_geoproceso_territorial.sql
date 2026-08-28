-- Geoproceso territorial para Vista 3.2 · Mapa de Necesidades
-- Ejecutar una sola vez en Supabase SQL Editor.
-- No elimina ni modifica necesidades existentes.
--
-- El cálculo geométrico se realiza en Streamlit con:
--   cobertura (%) = área(intersección sistema, unidad administrativa)
--                  / área(total de la cobertura del sistema) * 100
-- y solo se sincronizan relaciones con cobertura > 10% de la huella del sistema.
-- Si por fragmentación ninguna unidad supera el umbral, la aplicación puede
-- conservar la unidad territorial dominante con umbral 0 para no dejar el sistema
-- sin asociación administrativa.
--
-- La tabla guarda el catálogo sistema-territorio. La vista asocia automáticamente
-- las necesidades actuales y futuras mediante public.necesidades_sistemas.

begin;

create table if not exists public.sistemas_territorios (
  sistema_codigo text not null,
  sistema_nombre text not null,
  nivel text not null
    check (nivel in ('canton', 'distrito')),
  provincia text not null,
  canton text not null,
  distrito text not null default '',
  etiqueta text not null,
  porcentaje_cobertura numeric(8,3) not null
    check (porcentaje_cobertura > 0 and porcentaje_cobertura <= 100),
  umbral_pct numeric(6,3) not null default 10.000,
  actualizado_en timestamptz not null default now(),
  constraint sistemas_territorios_pk
    primary key (sistema_codigo, nivel, provincia, canton, distrito)
);

create index if not exists idx_sistemas_territorios_codigo
  on public.sistemas_territorios(sistema_codigo);

create index if not exists idx_sistemas_territorios_provincia
  on public.sistemas_territorios(provincia);

create index if not exists idx_sistemas_territorios_canton
  on public.sistemas_territorios(provincia, canton);

create index if not exists idx_sistemas_territorios_distrito
  on public.sistemas_territorios(provincia, canton, distrito);

comment on table public.sistemas_territorios is
  'Relación derivada por geoproceso entre coberturas de sistemas de abastecimiento y cantones/distritos.';

comment on column public.sistemas_territorios.porcentaje_cobertura is
  'Porcentaje de la huella total del sistema que se localiza dentro de la unidad administrativa.';

create or replace function public.replace_sistemas_territorios(
  p_rows jsonb
)
returns void
language plpgsql
as $$
begin
  if p_rows is null or jsonb_typeof(p_rows) <> 'array' then
    raise exception 'p_rows debe ser un arreglo JSON';
  end if;

  -- Supabase/PostgREST puede tener activada la protección safeupdate, que
  -- rechaza DELETE sin WHERE aun dentro de una función RPC. sistema_codigo es
  -- NOT NULL, por lo que esta condición elimina todo el catálogo de forma segura
  -- y satisface la exigencia de un predicado explícito.
  delete from public.sistemas_territorios
  where sistema_codigo is not null;

  insert into public.sistemas_territorios (
    sistema_codigo,
    sistema_nombre,
    nivel,
    provincia,
    canton,
    distrito,
    etiqueta,
    porcentaje_cobertura,
    umbral_pct,
    actualizado_en
  )
  select
    trim(x.sistema_codigo),
    trim(x.sistema_nombre),
    trim(x.nivel),
    trim(x.provincia),
    trim(x.canton),
    coalesce(trim(x.distrito), ''),
    trim(x.etiqueta),
    x.porcentaje_cobertura,
    coalesce(x.umbral_pct, 10.000),
    now()
  from jsonb_to_recordset(p_rows) as x(
    sistema_codigo text,
    sistema_nombre text,
    nivel text,
    provincia text,
    canton text,
    distrito text,
    etiqueta text,
    porcentaje_cobertura numeric,
    umbral_pct numeric
  )
  where nullif(trim(x.sistema_codigo), '') is not null
    and x.nivel in ('canton', 'distrito')
    and nullif(trim(x.provincia), '') is not null
    and nullif(trim(x.canton), '') is not null
    and x.porcentaje_cobertura > coalesce(x.umbral_pct, 10.000)
  on conflict (sistema_codigo, nivel, provincia, canton, distrito)
  do update set
    sistema_nombre = excluded.sistema_nombre,
    etiqueta = excluded.etiqueta,
    porcentaje_cobertura = excluded.porcentaje_cobertura,
    umbral_pct = excluded.umbral_pct,
    actualizado_en = now();
end;
$$;

create or replace view public.v_necesidades_territorios as
select
  n.id as necesidad_id,
  coalesce(
    array_agg(distinct st.provincia order by st.provincia)
      filter (where st.provincia is not null),
    array[]::text[]
  ) as provincias_asociadas,
  coalesce(
    array_agg(distinct st.etiqueta order by st.etiqueta)
      filter (where st.nivel = 'canton'),
    array[]::text[]
  ) as cantones_asociados,
  coalesce(
    array_agg(distinct st.etiqueta order by st.etiqueta)
      filter (where st.nivel = 'distrito'),
    array[]::text[]
  ) as distritos_asociados,
  coalesce(
    jsonb_agg(
      distinct jsonb_build_object(
        'sistema_codigo', st.sistema_codigo,
        'sistema_nombre', st.sistema_nombre,
        'nivel', st.nivel,
        'provincia', st.provincia,
        'canton', st.canton,
        'distrito', st.distrito,
        'etiqueta', st.etiqueta,
        'porcentaje_cobertura', st.porcentaje_cobertura,
        'umbral_pct', st.umbral_pct
      )
    ) filter (where st.sistema_codigo is not null),
    '[]'::jsonb
  ) as detalle_cobertura_territorial
from public.necesidades as n
left join public.necesidades_sistemas as ns
  on ns.necesidad_id = n.id
left join public.sistemas_territorios as st
  on st.sistema_codigo = ns.sistema_codigo
group by n.id;

grant select, insert, update, delete
  on public.sistemas_territorios
  to anon, authenticated, service_role;

grant execute
  on function public.replace_sistemas_territorios(jsonb)
  to anon, authenticated, service_role;

grant select
  on public.v_necesidades_territorios
  to anon, authenticated, service_role;

commit;

select *
from public.v_necesidades_territorios
order by necesidad_id
limit 50;
