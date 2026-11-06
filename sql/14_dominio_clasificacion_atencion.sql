-- 14 · Dominio único para clasificación de la atención (Vistas 3.1 y 3.3).
-- Ejecutar una vez en Supabase SQL Editor.
-- Valores admitidos:
--   Lo puede atender GAM
--   Requiere apoyo de otras dependencias
--   Ambos
--   Sin clasificar
--
-- Conserva los datos: antes de migrar, detiene la transacción cuando existen
-- etiquetas no reconocidas (en lugar de cambiarlas silenciosamente).
-- Se puede volver a ejecutar; no recrea tablas ni elimina necesidades.

begin;

alter table public.necesidades
  add column if not exists responsabilidad_atencion text;

do $$
declare
  v_invalidos text;
begin
  select string_agg(distinct trim(responsabilidad_atencion), ', ')
    into v_invalidos
  from public.necesidades
  where nullif(trim(coalesce(responsabilidad_atencion, '')), '') is not null
    and lower(trim(responsabilidad_atencion)) not in (
      'lo puede atender gam',
      'lo puede atender el gam',
      'requiere apoyo de otras dependencias',
      'se requiere apoyo de otras dependencias',
      'ambos',
      'sin clasificar'
    );

  if v_invalidos is not null then
    raise exception
      'Clasificaciones no reconocidas: %. Revise y clasifique estos registros antes de aplicar la migración.',
      v_invalidos;
  end if;
end;
$$;

update public.necesidades
set responsabilidad_atencion = case lower(trim(coalesce(responsabilidad_atencion, '')))
  when 'lo puede atender gam' then 'Lo puede atender GAM'
  when 'lo puede atender el gam' then 'Lo puede atender GAM'
  when 'requiere apoyo de otras dependencias' then 'Requiere apoyo de otras dependencias'
  when 'se requiere apoyo de otras dependencias' then 'Requiere apoyo de otras dependencias'
  when 'ambos' then 'Ambos'
  else 'Sin clasificar'
end
where responsabilidad_atencion is distinct from case lower(trim(coalesce(responsabilidad_atencion, '')))
  when 'lo puede atender gam' then 'Lo puede atender GAM'
  when 'lo puede atender el gam' then 'Lo puede atender GAM'
  when 'requiere apoyo de otras dependencias' then 'Requiere apoyo de otras dependencias'
  when 'se requiere apoyo de otras dependencias' then 'Requiere apoyo de otras dependencias'
  when 'ambos' then 'Ambos'
  else 'Sin clasificar'
end;

alter table public.necesidades
  alter column responsabilidad_atencion set default 'Sin clasificar',
  alter column responsabilidad_atencion set not null;

alter table public.necesidades
  drop constraint if exists necesidades_responsabilidad_atencion_check;

alter table public.necesidades
  add constraint necesidades_responsabilidad_atencion_check
  check (responsabilidad_atencion in (
    'Lo puede atender GAM',
    'Requiere apoyo de otras dependencias',
    'Ambos',
    'Sin clasificar'
  ));

commit;

-- Comprobación posterior a la migración.
select responsabilidad_atencion, count(*) as cantidad
from public.necesidades
group by responsabilidad_atencion
order by responsabilidad_atencion;
