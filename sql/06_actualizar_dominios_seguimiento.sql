-- Actualiza los dominios permitidos para el estado de seguimiento.
-- Ejecutar después de sql/04_seguimiento_necesidades.sql.
-- No modifica los valores actualmente almacenados.

begin;

alter table public.necesidades_seguimiento
  drop constraint if exists necesidades_seguimiento_estado_check;

alter table public.necesidades_seguimiento
  add constraint necesidades_seguimiento_estado_check
  check (
    estado_actual is null
    or estado_actual in (
      'Conceptualizado como una idea',
      'En Ejecución',
      'Incorporada al BPIP o convertida en proyecto',
      'Iniciativa enviada a la Dirección de Planificación',
      'Iniciativa trasladada a SAID',
      'Trasladado a Presidencia',
      'Trasladado a Subgerencia GAM',
      'Necesidad Resuelta',
      'La Iniciativa puede ser asumida con presupuesto operativo',
      'Descartada o no viable',
      'Suspendida o pendiente de información'
    )
  );

commit;

-- Verificación de la restricción vigente.
select
  conname as restriccion,
  pg_get_constraintdef(oid) as definicion
from pg_constraint
where conrelid = 'public.necesidades_seguimiento'::regclass
  and conname = 'necesidades_seguimiento_estado_check';
