-- Reparación de persistencia territorial para Vista 3.2 y consumo en Vista 3.3
-- Ejecutar UNA VEZ en Supabase SQL Editor si ya se había ejecutado sql/08.
--
-- Corrige el error:
--   DELETE requires a WHERE clause
-- generado por la protección safeupdate de Supabase/PostgREST.
--
-- No elimina necesidades, ubicaciones, seguimiento ni asociaciones de sistemas.
-- Solo redefine la función que reemplaza el catálogo derivado sistema-territorio.

begin;

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

  -- sistema_codigo es NOT NULL: este predicado equivale a vaciar la tabla,
  -- pero cumple con la exigencia de WHERE de safeupdate.
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

grant execute
  on function public.replace_sistemas_territorios(jsonb)
  to anon, authenticated, service_role;

-- Reafirma permisos de lectura/escritura del catálogo derivado.
grant select, insert, update, delete
  on public.sistemas_territorios
  to anon, authenticated, service_role;

grant select
  on public.v_necesidades_territorios
  to anon, authenticated, service_role;

commit;

-- Solicita a PostgREST refrescar el esquema expuesto.
notify pgrst, 'reload schema';

-- Diagnóstico inicial. Antes de volver a abrir 3.2 puede mostrar 0 filas;
-- la app poblará la tabla al ejecutar nuevamente el geoproceso.
select
  count(*) as relaciones_territoriales,
  count(distinct sistema_codigo) as sistemas_con_territorio
from public.sistemas_territorios;

select
  necesidad_id,
  provincias_asociadas,
  cantones_asociados,
  distritos_asociados
from public.v_necesidades_territorios
order by necesidad_id
limit 20;
