-- Relación muchos-a-muchos entre necesidades y sistemas de abastecimiento.
-- Ejecutar una sola vez en Supabase SQL Editor.
-- Es compatible con los registros existentes y no elimina información.

begin;

create table if not exists public.necesidades_sistemas (
  id bigserial primary key,
  necesidad_id bigint not null
    references public.necesidades(id) on delete cascade,
  sistema_nombre text not null
    references public.sistemas_clusters(sistema_nombre)
    on update cascade on delete restrict,
  sistema_codigo text not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint necesidades_sistemas_necesidad_sistema_key
    unique (necesidad_id, sistema_nombre)
);

create index if not exists idx_necesidades_sistemas_necesidad
  on public.necesidades_sistemas(necesidad_id);

create index if not exists idx_necesidades_sistemas_nombre
  on public.necesidades_sistemas(sistema_nombre);

create index if not exists idx_necesidades_sistemas_codigo
  on public.necesidades_sistemas(sistema_codigo);

create or replace function public.asignar_codigo_necesidad_sistema()
returns trigger
language plpgsql
as $$
declare
  v_codigo text;
begin
  select nullif(trim(sc.sistema_codigo), '')
    into v_codigo
  from public.sistemas_clusters as sc
  where sc.sistema_nombre = new.sistema_nombre;

  if v_codigo is null then
    raise exception
      'El sistema % no existe o no tiene código en sistemas_clusters',
      new.sistema_nombre;
  end if;

  new.sistema_codigo := v_codigo;
  new.updated_at := now();
  return new;
end;
$$;

drop trigger if exists trg_asignar_codigo_necesidad_sistema
  on public.necesidades_sistemas;

create trigger trg_asignar_codigo_necesidad_sistema
before insert or update
on public.necesidades_sistemas
for each row
execute function public.asignar_codigo_necesidad_sistema();

create or replace function public.sincronizar_necesidad_sistemas_legacy(
  p_necesidad_id bigint
)
returns void
language sql
as $$
  update public.necesidades as n
  set
    sistema_de_abastecimiento = (
      select string_agg(ns.sistema_nombre, '; ' order by ns.sistema_nombre)
      from public.necesidades_sistemas as ns
      where ns.necesidad_id = p_necesidad_id
    ),
    codigo_de_sistema = (
      select string_agg(ns.sistema_codigo, '; ' order by ns.sistema_nombre)
      from public.necesidades_sistemas as ns
      where ns.necesidad_id = p_necesidad_id
    ),
    updated_at = now()
  where n.id = p_necesidad_id;
$$;

create or replace function public.trg_sincronizar_necesidad_sistemas_legacy()
returns trigger
language plpgsql
as $$
begin
  if tg_op = 'DELETE' then
    perform public.sincronizar_necesidad_sistemas_legacy(old.necesidad_id);
    return old;
  end if;

  perform public.sincronizar_necesidad_sistemas_legacy(new.necesidad_id);

  if tg_op = 'UPDATE' and old.necesidad_id is distinct from new.necesidad_id then
    perform public.sincronizar_necesidad_sistemas_legacy(old.necesidad_id);
  end if;

  return new;
end;
$$;

drop trigger if exists trg_sincronizar_necesidad_sistemas_legacy
  on public.necesidades_sistemas;

create trigger trg_sincronizar_necesidad_sistemas_legacy
after insert or update or delete
on public.necesidades_sistemas
for each row
execute function public.trg_sincronizar_necesidad_sistemas_legacy();

-- Migra cada asociación simple ya almacenada en necesidades.
-- Los valores no reconocidos se conservan en las columnas antiguas para revisión.
insert into public.necesidades_sistemas (
  necesidad_id,
  sistema_nombre,
  sistema_codigo
)
select
  n.id,
  matched.sistema_nombre,
  matched.sistema_codigo
from public.necesidades as n
cross join lateral (
  select
    sc.sistema_nombre,
    sc.sistema_codigo
  from public.sistemas_clusters as sc
  where trim(sc.sistema_nombre) = trim(coalesce(n.sistema_de_abastecimiento, ''))
     or trim(sc.sistema_codigo) = trim(coalesce(n.codigo_de_sistema, ''))
  order by
    case
      when trim(sc.sistema_nombre) = trim(coalesce(n.sistema_de_abastecimiento, ''))
        then 0
      else 1
    end
  limit 1
) as matched
where n.id is not null
on conflict (necesidad_id, sistema_nombre) do nothing;

create or replace function public.set_necesidad_sistemas(
  p_necesidad_id bigint,
  p_sistemas text[]
)
returns void
language plpgsql
as $$
declare
  v_sistemas text[];
  v_desconocidos text;
begin
  if not exists (
    select 1
    from public.necesidades
    where id = p_necesidad_id
  ) then
    raise exception 'La necesidad % no existe', p_necesidad_id;
  end if;

  select coalesce(array_agg(nombre order by nombre), array[]::text[])
    into v_sistemas
  from (
    select distinct trim(valor) as nombre
    from unnest(coalesce(p_sistemas, array[]::text[])) as entrada(valor)
    where nullif(trim(valor), '') is not null
  ) as sistemas_limpios;

  select string_agg(sistema, ', ' order by sistema)
    into v_desconocidos
  from unnest(v_sistemas) as sistema
  where not exists (
    select 1
    from public.sistemas_clusters as sc
    where sc.sistema_nombre = sistema
  );

  if v_desconocidos is not null then
    raise exception
      'Los siguientes sistemas no existen en sistemas_clusters: %',
      v_desconocidos;
  end if;

  delete from public.necesidades_sistemas
  where necesidad_id = p_necesidad_id;

  insert into public.necesidades_sistemas (
    necesidad_id,
    sistema_nombre,
    sistema_codigo
  )
  select
    p_necesidad_id,
    sc.sistema_nombre,
    sc.sistema_codigo
  from unnest(v_sistemas) as seleccionado(sistema_nombre)
  join public.sistemas_clusters as sc
    on sc.sistema_nombre = seleccionado.sistema_nombre
  on conflict (necesidad_id, sistema_nombre) do nothing;

  -- También sincroniza correctamente cuando la selección queda vacía.
  perform public.sincronizar_necesidad_sistemas_legacy(p_necesidad_id);
end;
$$;

grant select, insert, update, delete
  on public.necesidades_sistemas
  to anon, authenticated, service_role;

grant usage, select
  on sequence public.necesidades_sistemas_id_seq
  to anon, authenticated, service_role;

grant execute
  on function public.set_necesidad_sistemas(bigint, text[])
  to anon, authenticated, service_role;

commit;

-- Verificación: muestra cada necesidad y todos sus sistemas asociados.
select
  n.id,
  n.objetivo_de_la_iniciativa,
  string_agg(ns.sistema_nombre, '; ' order by ns.sistema_nombre)
    as sistemas_asociados,
  string_agg(ns.sistema_codigo, '; ' order by ns.sistema_nombre)
    as codigos_asociados
from public.necesidades as n
left join public.necesidades_sistemas as ns
  on ns.necesidad_id = n.id
group by n.id, n.objetivo_de_la_iniciativa
order by n.id;
