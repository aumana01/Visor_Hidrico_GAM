-- Vista 3.3 · Banco de Ideas de Proyectos AyA
-- Formato EST-02-02-F4
--
-- Ejecutar una sola vez en Supabase SQL Editor, después de los scripts
-- 04_seguimiento_necesidades.sql y 06_actualizar_dominios_seguimiento.sql.
--
-- Este script NO elimina información previa. Amplía public.necesidades_seguimiento
-- con los campos editables del formato institucional. Los datos territoriales,
-- población, servicios, condición hídrica y balance hídrico se calculan en la app
-- a partir de las relaciones de sistemas y de la Vista 3.2.

begin;

alter table public.necesidades_seguimiento
  add column if not exists codigo_interno text not null default '',
  add column if not exists unidad_solicitante text not null default 'GAM',
  add column if not exists unidad_formula_idea text not null default '',
  add column if not exists posible_fuente_financiamiento text not null default 'Pendiente',
  add column if not exists tipo_proyecto_banco text not null default 'Abastecimiento Agua Potable',
  add column if not exists memo_formulario_necesidad text not null default '',
  add column if not exists acuerdo_cdp text not null default 'NO',
  add column if not exists region_aya text not null default 'GAM',
  add column if not exists comunidades text not null default '',
  add column if not exists estado_actual_aya text not null default 'En lista de espera',
  add column if not exists mandato_asociado text not null default 'No',
  add column if not exists fecha_recurso_amparo date,
  add column if not exists propuesta_solucion text not null default 'NO',
  add column if not exists orden_desacato text not null default 'NO',
  add column if not exists compromiso_social text not null default 'NO',
  add column if not exists estudios_terrenos text not null default 'NO',
  add column if not exists proyecto_avance text not null default 'NO',
  add column if not exists descripcion_avance text not null default '',
  add column if not exists priorizacion_region numeric,
  add column if not exists estado_sistema_ba numeric;

alter table public.necesidades_seguimiento
  drop constraint if exists necesidades_seguimiento_acuerdo_cdp_check,
  drop constraint if exists necesidades_seguimiento_estado_actual_aya_check,
  drop constraint if exists necesidades_seguimiento_mandato_asociado_check,
  drop constraint if exists necesidades_seguimiento_propuesta_solucion_check,
  drop constraint if exists necesidades_seguimiento_orden_desacato_check,
  drop constraint if exists necesidades_seguimiento_compromiso_social_check,
  drop constraint if exists necesidades_seguimiento_estudios_terrenos_check,
  drop constraint if exists necesidades_seguimiento_proyecto_avance_check;

alter table public.necesidades_seguimiento
  add constraint necesidades_seguimiento_acuerdo_cdp_check
    check (acuerdo_cdp in ('SI', 'NO')),
  add constraint necesidades_seguimiento_estado_actual_aya_check
    check (estado_actual_aya in ('En lista de espera', 'Formulación de Iniciativa')),
  add constraint necesidades_seguimiento_mandato_asociado_check
    check (
      mandato_asociado in (
        'No',
        'Recurso de amparo',
        'Decreto de emergencia',
        'Orden Sanitaria',
        'Recurso de Amparo y Orden Sanitaria'
      )
    ),
  add constraint necesidades_seguimiento_propuesta_solucion_check
    check (propuesta_solucion in ('SI', 'NO')),
  add constraint necesidades_seguimiento_orden_desacato_check
    check (orden_desacato in ('SI', 'NO')),
  add constraint necesidades_seguimiento_compromiso_social_check
    check (compromiso_social in ('SI', 'NO')),
  add constraint necesidades_seguimiento_estudios_terrenos_check
    check (estudios_terrenos in ('SI', 'NO')),
  add constraint necesidades_seguimiento_proyecto_avance_check
    check (proyecto_avance in ('SI', 'NO'));

insert into public.necesidades_seguimiento (necesidad_id)
select n.id
from public.necesidades as n
on conflict (necesidad_id) do nothing;

update public.necesidades_seguimiento as s
set codigo_interno = trim(n.id_origen)
from public.necesidades as n
where n.id = s.necesidad_id
  and nullif(trim(s.codigo_interno), '') is null
  and nullif(trim(n.id_origen), '') is not null;

update public.necesidades_seguimiento as s
set codigo_interno = coalesce(
  nullif(trim(s.codigo_interno), ''),
  substring(
    s.detalle_accion
    from '(GAM-[A-Z]-[0-9]+|SD-GAM-[A-Z]-[0-9]+|AB[[:space:]]*[0-9]+)'
  ),
  ''
)
where nullif(trim(s.codigo_interno), '') is null
  and nullif(trim(s.detalle_accion), '') is not null;

update public.necesidades_seguimiento as s
set memo_formulario_necesidad = coalesce(
  nullif(trim(s.memo_formulario_necesidad), ''),
  substring(
    upper(s.detalle_accion)
    from '(UEN-[A-Z0-9-]*GAM-[0-9]{4}-[0-9]{5})'
  ),
  ''
)
where nullif(trim(s.memo_formulario_necesidad), '') is null
  and nullif(trim(s.detalle_accion), '') is not null;

update public.necesidades_seguimiento
set unidad_formula_idea = 'SAID (PyC)'
where nullif(trim(unidad_formula_idea), '') is null
  and (
    detalle_accion ~* 'SAID como unidad responsable de formulaci[oó]n'
    or detalle_accion ~* 'Responsable:[[:space:]]*SAID'
  );

update public.necesidades_seguimiento
set estado_actual_aya = case
  when estado_actual in (
    'En Ejecución',
    'Incorporada al BPIP o convertida en proyecto',
    'Iniciativa enviada a la Dirección de Planificación',
    'Iniciativa trasladada a SAID',
    'Trasladado a Presidencia',
    'Trasladado a Subgerencia GAM',
    'Necesidad Resuelta'
  )
    then 'Formulación de Iniciativa'
  else 'En lista de espera'
end;

create index if not exists idx_necesidades_seguimiento_estado_aya
  on public.necesidades_seguimiento(estado_actual_aya);

create index if not exists idx_necesidades_seguimiento_codigo_interno
  on public.necesidades_seguimiento(codigo_interno);

comment on column public.necesidades_seguimiento.estado_actual_aya is
  'Estado institucional simplificado para Banco de Ideas: En lista de espera o Formulación de Iniciativa.';

comment on column public.necesidades_seguimiento.memo_formulario_necesidad is
  'Memorando u oficio con el que se trasladó la necesidad a Planificación, cuando existe evidencia.';

comment on column public.necesidades_seguimiento.priorizacion_region is
  'Valor numérico de priorización regional; permanece vacío hasta que la Región lo defina.';

grant select, insert, update, delete
  on public.necesidades_seguimiento
  to anon, authenticated, service_role;

commit;

select
  n.id,
  s.codigo_interno,
  s.estado_actual_aya,
  s.memo_formulario_necesidad,
  s.unidad_formula_idea,
  s.region_aya
from public.necesidades as n
left join public.necesidades_seguimiento as s
  on s.necesidad_id = n.id
order by n.id
limit 100;
