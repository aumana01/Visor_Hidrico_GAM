-- Seguimiento del estado actual de necesidades e iniciativas.
-- Ejecutar una sola vez en Supabase SQL Editor.
-- No modifica ni elimina datos de public.necesidades.

begin;

create table if not exists public.necesidades_seguimiento (
  necesidad_id bigint primary key
    references public.necesidades(id) on update cascade on delete cascade,
  estado_actual text,
  detalle_accion text not null default '',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint necesidades_seguimiento_estado_check
    check (
      estado_actual is null
      or estado_actual in (
        'Conceptualizado como una idea',
        'Iniciativa enviada a la Dirección de Planificación',
        'Iniciativa trasladada a SAID',
        'Necesidad Resuelta',
        'La Iniciativa puede ser asumida con presupuesto operativo'
      )
    )
);

create index if not exists idx_necesidades_seguimiento_estado
  on public.necesidades_seguimiento(estado_actual);

create or replace function public.actualizar_fecha_necesidad_seguimiento()
returns trigger
language plpgsql
as $$
begin
  new.updated_at := now();
  return new;
end;
$$;

drop trigger if exists trg_actualizar_fecha_necesidad_seguimiento
  on public.necesidades_seguimiento;

create trigger trg_actualizar_fecha_necesidad_seguimiento
before update on public.necesidades_seguimiento
for each row
execute function public.actualizar_fecha_necesidad_seguimiento();

-- Precarga conservadora a partir del contexto ya registrado.
-- Si no existe evidencia suficiente, el estado y el detalle permanecen vacíos.
with contexto as (
  select
    n.id as necesidad_id,
    concat_ws(
      ' ',
      nullif(trim(n.breve_descripcion), ''),
      nullif(trim(n.principal_reto_por_superar), ''),
      nullif(trim(n.observacion), '')
    ) as texto
  from public.necesidades as n
),
clasificacion as (
  select
    necesidad_id,
    case
      when texto ~* '(necesidad[[:space:]]+resuelta|trabajos?[[:space:]]+finalizados?|iniciativa[[:space:]]+ejecutada)'
        then 'Necesidad Resuelta'
      when texto ~* '(remitid[ao]|enviad[ao]|trasladad[ao]).{0,80}planificaci[oó]n'
        then 'Iniciativa enviada a la Dirección de Planificación'
      when texto ~* '(remitid[ao]|enviad[ao]|trasladad[ao]).{0,80}said'
        or texto ~* 'incluid[ao].{0,80}licitaci[oó]n.{0,80}said'
        then 'Iniciativa trasladada a SAID'
      when texto ~* 'no[[:space:]]+requiere[[:space:]]+solicitud[[:space:]]+de[[:space:]]+necesidad[[:space:]]+de[[:space:]]+proyecto'
        and texto ~* '(convenio[[:space:]]+marco|mantenimiento|presupuesto[[:space:]]+operativo)'
        then 'La Iniciativa puede ser asumida con presupuesto operativo'
      when texto ~* '(fase:[[:space:]]*idea[[:space:]]+de[[:space:]]+proyecto|conceptualizad[ao]|idea[[:space:]]+de[[:space:]]+proyecto)'
        then 'Conceptualizado como una idea'
      else null
    end as estado_actual,
    case
      when texto ~* '(oficio|memorando)[[:space:]]+[[:alnum:]-]+'
        then 'Referencia documental: ' ||
          substring(
            texto from '(?i)(?:oficio|memorando)[[:space:]]+([[:alnum:]-]+)'
          )
      else ''
    end as detalle_accion
  from contexto
)
insert into public.necesidades_seguimiento (
  necesidad_id,
  estado_actual,
  detalle_accion
)
select
  necesidad_id,
  estado_actual,
  detalle_accion
from clasificacion
where estado_actual is not null
   or nullif(detalle_accion, '') is not null
on conflict (necesidad_id) do nothing;

grant select, insert, update, delete
  on public.necesidades_seguimiento
  to anon, authenticated, service_role;

commit;

-- Verificación del seguimiento cargado.
select
  n.id,
  n.objetivo_de_la_iniciativa,
  s.estado_actual,
  s.detalle_accion
from public.necesidades as n
left join public.necesidades_seguimiento as s
  on s.necesidad_id = n.id
order by n.id;
