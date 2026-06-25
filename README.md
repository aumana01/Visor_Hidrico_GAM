# GAM Hídrico · Streamlit + Supabase

Herramienta para la gestión, análisis y visualización de proyectos relacionados con el acueducto GAM, su impacto en capacidad hídrica y la clasificación de necesidades de inversión.

## Vistas incluidas

1. **Gestión de proyectos**
   - Lista editable tipo Microsoft Lists.
   - Alta, edición y eliminación de proyectos.
   - Campos de caudal, año de efecto, sistema, cluster, beneficios, impactos, riesgos y responsable.
   - Gráficos por sistema, cluster y acción.

2. **Capacidad hídrica GAM**
   - Tabla ajustable por cluster basada en proyectos de análisis.
   - Tablas base **SIN PAAM** y **CON PAAM** de 2024 a 2040 como información oficial no impactada.
   - Filtro por cluster.
   - Recalculo del balance hídrico por cluster: `balance base SIN PAAM + caudal esperado de proyectos según año efecto/incorporación`.

3. **Necesidades de inversión**
   - Resumen gráfico por tipo de proyecto y sistema.
   - Tabla editable de necesidades.
   - Alta y eliminación de necesidades.
   - Exportación CSV para insumos a Planificación.

## Estructura

```text
.
├── app.py
├── database.py
├── requirements.txt
├── .env.example
├── .streamlit/config.toml
├── sql/01_schema.sql
└── data/
    ├── proyectos_seed.csv
    ├── capacidad_base_seed.csv
    ├── necesidades_seed.csv
    ├── sistemas_clusters.csv
    └── catálogos auxiliares
```

## Ejecución local

```bash
python -m venv .venv
.venv\Scripts\activate  # Windows
pip install -r requirements.txt
streamlit run app.py
```

La aplicación funciona en **modo local CSV** aunque todavía no exista Supabase. Los cambios locales se guardan en `data/_local_runtime/`, carpeta excluida de Git.

## Configuración de Supabase

1. Crear un proyecto en Supabase.
2. Abrir **SQL Editor** y ejecutar `sql/01_schema.sql`.
3. Crear el archivo `.streamlit/secrets.toml` localmente:

```toml
SUPABASE_URL = "https://TU-PROYECTO.supabase.co"
SUPABASE_KEY = "TU_LLAVE"
```

Para uso institucional privado se recomienda usar `SERVICE_ROLE_KEY` únicamente como secreto de Streamlit. No debe subirse a GitHub. Si se usa una llave `anon`, deben configurarse políticas RLS en Supabase.

4. Ejecutar la app y, desde la barra lateral, usar **Cargar datos base a Supabase**.

## Publicación en GitHub y Streamlit Cloud

1. Crear repositorio en GitHub.
2. Subir todos los archivos excepto `.streamlit/secrets.toml`, `.env` y `data/_local_runtime/`.
3. En Streamlit Cloud, conectar el repositorio.
4. En **App settings > Secrets**, agregar:

```toml
SUPABASE_URL = "https://TU-PROYECTO.supabase.co"
SUPABASE_KEY = "TU_LLAVE"
```

5. Deploy con comando:

```bash
streamlit run app.py
```

## Notas de cálculo

- La población beneficiada estimada se calcula en nuevos registros con la fórmula indicada en el requerimiento: `caudal_temporal_lps * 79.6 * 3.1`, redondeada hacia arriba.
- Para el análisis de capacidad de la Vista 2, el caudal de proyecto usado es únicamente `expectativa_caudal_lps` (caudal esperado). `caudal_temporal_lps` se conserva como dato informativo, pero no impacta el balance por cluster.
- El efecto se aplica acumulativamente desde `anio_efecto` hasta 2040.
- Los subtotales de cluster no se toman como fijos: se recalculan dinámicamente para permitir validar el efecto de proyectos incorporados.


## Ajustes versión 2

- Se corrige el error de Pandas `Styler.applymap` en la Vista 2 usando compatibilidad con `Styler.map`.
- La Vista 1 incorpora desplegables en la tabla editable y un formulario de edición detallada con campos tipo Choice/multiselección para beneficios, impacto y actividades críticas.
- La Vista 3 se limita a los campos solicitados para necesidades: objetivo, descripción, tipo de proyecto, código de sistema, sistema de abastecimiento, principal reto, observación y clasificación de atención.
- La clasificación de atención usa dos opciones: `Lo puede atender el GAM` y `Se requiere apoyo de otras dependencias`.

Si ya creó las tablas en Supabase con una versión previa, ejecute de nuevo `sql/01_schema.sql` o, como mínimo, este ajuste:

```sql
alter table if exists public.necesidades
  add column if not exists responsabilidad_atencion text;
```

## Ajustes versión 3

- La Vista 2 separa claramente las tablas oficiales informativas de la tabla de análisis:
  - **Balance de escenario base SIN incorporación de proyectos**: se muestra tal cual.
  - **Balance CON PAAM (2032 en adelante)**: se muestra tal cual.
  - **Tabla ajustable por cluster**: es la única que suma el efecto acumulado de proyectos de análisis según año de efecto/incorporación y caudal esperado.
- Se actualizó `data/capacidad_base_seed.csv` con los valores 2024–2040 indicados para SIN PAAM y CON PAAM, incluyendo la fila **ME-A-32-PAAM (RESERVA)** en CON PAAM.
- Se incorporó **ME-A-32-PAAM (RESERVA)** en `sistemas_clusters.csv` para visualización y filtros.
- En la Vista 1, los campos `beneficios`, `impacto` y `actividades_criticas` ahora tienen configuración de desplegable/Choice en la tabla editable, además del formulario de edición detallada.

Si la aplicación ya fue ejecutada en modo local CSV y no ve los cambios de capacidad, elimine el archivo local `data/_local_runtime/capacidad_base.csv` para que Streamlit use nuevamente `data/capacidad_base_seed.csv`. En Supabase, vuelva a cargar los datos base desde la barra lateral si desea sobrescribir la tabla `capacidad_base` con esta versión.

La barra lateral incluye el botón **Restablecer CSV local** para eliminar archivos de `data/_local_runtime/` y volver a usar los datos semilla incluidos en el repositorio.

## Ajustes versión 4

- La Vista 2 ahora inicia con la **Tabla ajustable con base en proyectos de análisis · Resumen por cluster**, seguida por las tablas oficiales **SIN PAAM** y **CON PAAM**.
- Se eliminó el selector **Año de referencia** y el control **Usar solo proyectos activos**.
- El cálculo ajustado por cluster usa únicamente `expectativa_caudal_lps` (**caudal esperado**). El `caudal_temporal_lps` queda solo como dato informativo y no afecta la Vista 2.
- Se eliminó la visualización operativa de **Activo en capacidad** en la Vista 1.
- La Vista 1 se reorganizó para mostrar primero **Gráficos**, luego **Lista editable**, **Editar detalle** y **Agregar proyecto**.
- Se agregó texto explicativo sobre el significado de proyecto, caudal temporal y caudal esperado.
- Todos los gráficos de barras incluyen etiquetas de valor; los gráficos de necesidades por tipo de proyecto usan colores por categoría.

> Nota: si ya ejecutó la app en modo local, use **Restablecer CSV local** en la barra lateral para que se tomen los datos y configuración actualizados. En Supabase, use la carga base con sobrescritura si desea reemplazar tablas existentes.

## Ajustes v5 · Vista 2 ejecutiva

Esta versión cambia la Vista 2 para que el resumen por cluster sea más gerencial y menos crudo visualmente:

- El primer bloque ahora muestra **brecha base, aporte esperado de proyectos y brecha remanente**.
- La brecha se presenta como valor positivo: es decir, cuánto falta por cerrar, no solo balances negativos.
- Se agrega un **semáforo ejecutivo por cluster**.
- Se agrega una tabla ejecutiva con lectura gerencial por cluster.
- Se mantiene la realidad técnica mediante las tablas oficiales SIN PAAM y CON PAAM al final de la vista.
- El caudal temporal sigue sin afectar la Vista 2; solo se usa el caudal esperado de proyectos.

## Ajustes v7 · Vista 2 ejecutiva con balance firmado

- El resumen ejecutivo ahora distingue entre **balance firmado** y **brecha remanente**:
  - balance negativo = déficit del cluster;
  - balance positivo = condición favorable;
  - brecha remanente = faltante pendiente cuando el balance ajustado sigue negativo.
- La Vista 2 agrega una explicación visible sobre el significado de **brecha remanente**.
- El gráfico principal de resumen por cluster permite ver, al pasar el mouse, los **sistemas de abastecimiento asociados** al cluster y los proyectos principales.
- La tabla ejecutiva elimina columnas de excedente y columnas asociadas a 2040.
- Se agrega una tabla de **balance anual por cluster con proyectos esperados** para observar años negativos y positivos entre 2024 y 2040.

## Ajustes v8 · Importación, mapa, clusters y lecciones aprendidas

- Se habilitó la **importación masiva desde Excel (.xlsx)** en:
  - Vista 1: proyectos e iniciativas de análisis.
  - Vista 3: necesidades de inversión.
- La importación acepta encabezados similares a los usados en las tablas institucionales; si el Excel incluye `id`, actualiza registros existentes; si no incluye `id`, agrega nuevos registros.
- Se agregó una pestaña **Mapa** en la Vista 1 para visualizar proyectos con latitud y longitud válidas.
- La Vista 2 se ajustó para trabajar desde **2025 hasta 2040** en el visor ejecutivo.
- Se eliminó el bloque **Evolución técnica controlada**.
- Se normalizó el orden de clusters:
  - Cluster 1: Tres Ríos, Guadalupe, Los Sitios, Los Cuadros, Mata de Plátano, San Jerónimo de Moravia, Padre Carazo, Pizote y Vista de Mar.
  - Cluster 2: San Pablo y La Valencia.
  - Cluster 3: El Llano, San Juan de Dios, San Antonio de Escazú, Alajuelita, Potrerillos-San Antonio, Barrio España, Sur de Escazú y Puente Mulas.
  - Cluster 4: San Rafael de Coronado y Chiverrales.
  - Cluster 5: Quitirrisí, Ticufres-Quebrada Honda y Puriscal.
  - Cluster 6: Salitral, Guatuso Patarrá, Sur Alajuelita, Matinilla, El Guarco, Lajas y Jericó.
- En la tabla ejecutiva de Vista 2 se agregó la columna **Sistema Más Representativo del Cluster**.
- En Vista 3 se agregaron campos cuantitativos:
  - caudal estimado que aporta la iniciativa (L/s),
  - volumen estimado que aporta la iniciativa (m³),
  - km estimados que aporta la iniciativa (km).
- En Vista 3 se agregó una tabla resumen por sistema y tipo de proyecto:
  - Aumento de Recurso Hídrico y Mejora en trasvase suman caudal estimado.
  - Mejora en Almacenamiento suma volumen.
  - Sustitución de tuberías suma kilómetros.
  - Las demás categorías cuentan cantidad de iniciativas.
- Se agregó la **Vista 4 · Lecciones aprendidas**, con listado de archivos PDF y visualizador embebido.

Si ya tiene Supabase creado con una versión anterior, vuelva a ejecutar `sql/01_schema.sql` para incorporar las columnas nuevas de necesidades.

## Ajustes v9

- El mapa de proyectos ahora interpreta longitudes positivas de Costa Rica como negativas; por ejemplo, `84.06` se muestra como `-84.06`.
- El mapa usa Plotly/OpenStreetMap y muestra todos los proyectos con coordenadas válidas dentro de Costa Rica.
- La Vista 4 permite borrar PDF seleccionados con confirmación.
- La Vista 4 renderiza PDFs como imágenes de páginas usando PyMuPDF para evitar bloqueos del navegador con iframes PDF.
