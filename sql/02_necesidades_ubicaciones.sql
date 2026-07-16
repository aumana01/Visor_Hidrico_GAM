-- Migración segura para habilitar múltiples ubicaciones por necesidad.
-- Puede ejecutarse en Supabase SQL Editor sin modificar los registros existentes
-- de public.necesidades.

begin;

create table if not exists public.necesidades_ubicaciones (
  id bigserial primary key,
  necesidad_id bigint not null references public.necesidades(id) on delete cascade,
  tipo_ubicacion text not null check (
    tipo_ubicacion in (
      'Ubicación precisa',
      'Ubicación general',
      'Ubicación institucional',
      'No aplica'
    )
  ),
  latitud double precision,
  longitud double precision,
  nombre_ubicacion text,
  observacion text,
  created_at timestamptz default now(),
  updated_at timestamptz default now(),
  check (
    tipo_ubicacion = 'No aplica'
    or (
      latitud between 8.0 and 12.0
      and longitud between -86.5 and -82.0
    )
  )
);

create index if not exists idx_necesidades_ubicaciones_necesidad
  on public.necesidades_ubicaciones(necesidad_id);

create index if not exists idx_necesidades_ubicaciones_tipo
  on public.necesidades_ubicaciones(tipo_ubicacion);

create or replace function public.set_updated_at()
returns trigger as $$
begin
  new.updated_at = now();
  return new;
end;
$$ language plpgsql;

drop trigger if exists trg_necesidades_ubicaciones_updated_at
  on public.necesidades_ubicaciones;

create trigger trg_necesidades_ubicaciones_updated_at
before update on public.necesidades_ubicaciones
for each row execute function public.set_updated_at();

commit;
