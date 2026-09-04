-- Trazabilidad del caudal revisado de los proyectos.
-- Ejecutar una vez en el SQL Editor de Supabase antes de publicar esta versión.

begin;

alter table public.proyectos
  add column if not exists caudal_revisado_lps double precision,
  add column if not exists fecha_revision_caudal timestamptz;

create table if not exists public.proyectos_caudal_historial (
  id bigserial primary key,
  proyecto_id bigint not null references public.proyectos(id) on delete cascade,
  caudal_anterior_lps double precision,
  caudal_revisado_lps double precision,
  fecha_revision timestamptz not null default now()
);

create index if not exists idx_proyectos_caudal_historial_proyecto_fecha
  on public.proyectos_caudal_historial(proyecto_id, fecha_revision desc);

create or replace function public.registrar_revision_caudal_proyecto()
returns trigger
language plpgsql
as $$
begin
  if new.caudal_revisado_lps is distinct from old.caudal_revisado_lps then
    new.fecha_revision_caudal := now();
    insert into public.proyectos_caudal_historial (
      proyecto_id,
      caudal_anterior_lps,
      caudal_revisado_lps,
      fecha_revision
    ) values (
      new.id,
      old.caudal_revisado_lps,
      new.caudal_revisado_lps,
      new.fecha_revision_caudal
    );
  else
    new.fecha_revision_caudal := old.fecha_revision_caudal;
  end if;
  return new;
end;
$$;

drop trigger if exists trg_registrar_revision_caudal_proyecto on public.proyectos;
create trigger trg_registrar_revision_caudal_proyecto
before update of caudal_revisado_lps on public.proyectos
for each row execute function public.registrar_revision_caudal_proyecto();

grant select, insert, update on public.proyectos_caudal_historial
  to anon, authenticated, service_role;
grant usage, select on sequence public.proyectos_caudal_historial_id_seq
  to anon, authenticated, service_role;

commit;
