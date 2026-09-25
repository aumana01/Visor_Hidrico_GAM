-- Reajuste oficial de clusters GAM (2026-09-25)
-- Idempotente: puede ejecutarse más de una vez.
-- Mantiene MEA32 como PAAM / RESERVA y alinea catálogo, proyectos y capacidad base.

with cluster_map(code, cluster) as (
  values
    ('MEA01','CLUSTER C-1'),
    ('MEA02','CLUSTER C-1'),
    ('MEA03','CLUSTER C-3'),
    ('MEA04','CLUSTER C-1'),
    ('MEA05','CLUSTER C-3'),
    ('MEA06','CLUSTER C-3'),
    ('MEA07','CLUSTER C-3'),
    ('MEA08','CLUSTER C-1'),
    ('MEA09','CLUSTER C-3'),
    ('MEA10','CLUSTER C-1'),
    ('MEA11','CLUSTER C-6'),
    ('MEA12','CLUSTER C-5'),
    ('MEA13','CLUSTER C-1'),
    ('MEA14','CLUSTER C-4'),
    ('MEA15','CLUSTER C-2'),
    ('MEA16','CLUSTER C-3'),
    ('MEA17','CLUSTER C-2'),
    ('MEA18','CLUSTER C-3'),
    ('MEA19','CLUSTER C-3'),
    ('MEA20','CLUSTER C-1'),
    ('MEA21','CLUSTER C-4'),
    ('MEA22','CLUSTER C-1'),
    ('MEA23','CLUSTER C-3'),
    ('MEA24','CLUSTER C-3'),
    ('MEA25','CLUSTER C-3'),
    ('MEA26','CLUSTER C-5'),
    ('MEA27','CLUSTER C-6'),
    ('MEA28','CLUSTER C-1'),
    ('MEA29','CLUSTER C-3'),
    ('MEA30','CLUSTER C-6'),
    ('MEA31','CLUSTER C-5'),
    ('MEA32','PAAM / RESERVA')
)
update public.sistemas_clusters as sc
set cluster = cm.cluster
from cluster_map as cm
where sc.sistema_codigo = cm.code
  and sc.cluster is distinct from cm.cluster;

with cluster_map(code, cluster) as (
  values
    ('MEA01','CLUSTER C-1'), ('MEA02','CLUSTER C-1'), ('MEA03','CLUSTER C-3'),
    ('MEA04','CLUSTER C-1'), ('MEA05','CLUSTER C-3'), ('MEA06','CLUSTER C-3'),
    ('MEA07','CLUSTER C-3'), ('MEA08','CLUSTER C-1'), ('MEA09','CLUSTER C-3'),
    ('MEA10','CLUSTER C-1'), ('MEA11','CLUSTER C-6'), ('MEA12','CLUSTER C-5'),
    ('MEA13','CLUSTER C-1'), ('MEA14','CLUSTER C-4'), ('MEA15','CLUSTER C-2'),
    ('MEA16','CLUSTER C-3'), ('MEA17','CLUSTER C-2'), ('MEA18','CLUSTER C-3'),
    ('MEA19','CLUSTER C-3'), ('MEA20','CLUSTER C-1'), ('MEA21','CLUSTER C-4'),
    ('MEA22','CLUSTER C-1'), ('MEA23','CLUSTER C-3'), ('MEA24','CLUSTER C-3'),
    ('MEA25','CLUSTER C-3'), ('MEA26','CLUSTER C-5'), ('MEA27','CLUSTER C-6'),
    ('MEA28','CLUSTER C-1'), ('MEA29','CLUSTER C-3'), ('MEA30','CLUSTER C-6'),
    ('MEA31','CLUSTER C-5'), ('MEA32','PAAM / RESERVA')
)
update public.proyectos as p
set cluster = cm.cluster,
    updated_at = now()
from cluster_map as cm
where p.sistema_codigo = cm.code
  and p.cluster is distinct from cm.cluster;

with cluster_map(code, cluster) as (
  values
    ('MEA01','CLUSTER C-1'), ('MEA02','CLUSTER C-1'), ('MEA03','CLUSTER C-3'),
    ('MEA04','CLUSTER C-1'), ('MEA05','CLUSTER C-3'), ('MEA06','CLUSTER C-3'),
    ('MEA07','CLUSTER C-3'), ('MEA08','CLUSTER C-1'), ('MEA09','CLUSTER C-3'),
    ('MEA10','CLUSTER C-1'), ('MEA11','CLUSTER C-6'), ('MEA12','CLUSTER C-5'),
    ('MEA13','CLUSTER C-1'), ('MEA14','CLUSTER C-4'), ('MEA15','CLUSTER C-2'),
    ('MEA16','CLUSTER C-3'), ('MEA17','CLUSTER C-2'), ('MEA18','CLUSTER C-3'),
    ('MEA19','CLUSTER C-3'), ('MEA20','CLUSTER C-1'), ('MEA21','CLUSTER C-4'),
    ('MEA22','CLUSTER C-1'), ('MEA23','CLUSTER C-3'), ('MEA24','CLUSTER C-3'),
    ('MEA25','CLUSTER C-3'), ('MEA26','CLUSTER C-5'), ('MEA27','CLUSTER C-6'),
    ('MEA28','CLUSTER C-1'), ('MEA29','CLUSTER C-3'), ('MEA30','CLUSTER C-6'),
    ('MEA31','CLUSTER C-5'), ('MEA32','PAAM / RESERVA')
)
update public.capacidad_base as cb
set cluster = cm.cluster
from cluster_map as cm
where cb.cod = cm.code
  and cb.cluster is distinct from cm.cluster;
