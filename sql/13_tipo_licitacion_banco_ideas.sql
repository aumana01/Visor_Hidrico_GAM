-- Vista 3.3 · Tipo de licitación del Banco de Ideas
--
-- Ejecutar una sola vez en Supabase SQL Editor después de
-- sql/09_formato_banco_ideas_seguimiento.sql.
--
-- La clasificación es manual: la aplicación no infiere el procedimiento a partir
-- del costo, porque el umbral aplicable debe ser definido institucionalmente.

begin;

alter table public.necesidades_seguimiento
  add column if not exists tipo_licitacion text not null default '';

alter table public.necesidades_seguimiento
  drop constraint if exists necesidades_seguimiento_tipo_licitacion_check;

alter table public.necesidades_seguimiento
  add constraint necesidades_seguimiento_tipo_licitacion_check
    check (tipo_licitacion in ('', 'Licitación menor', 'Licitación mayor'));

comment on column public.necesidades_seguimiento.tipo_licitacion is
  'Clasificación manual del tipo de licitación requerido para la necesidad: Licitación menor o Licitación mayor.';

grant select, insert, update, delete
  on public.necesidades_seguimiento
  to anon, authenticated, service_role;

commit;

select
  necesidad_id,
  tipo_licitacion
from public.necesidades_seguimiento
order by necesidad_id
limit 100;
