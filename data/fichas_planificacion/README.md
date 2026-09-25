# Plantillas específicas de fichas PE

La Vista 3.5 busca primero una plantilla específica para cada proyecto en esta carpeta:

- `PE-001.xls`
- `PE-002.xls`
- `PE-003.xls`
- `PE-004.xls`
- `PE-005.xls`
- `PE-006.xls`
- `PE-007.xls`
- `PE-008.xls`

Las plantillas pueden contener información de una versión anterior. El exportador localiza los campos institucionales y **sobrescribe** las respuestas administradas por la Vista 3.5 con la información vigente del aplicativo, conservando hojas, celdas combinadas, estilos y formato del archivo.

## Prioridad de plantilla

1. Archivo PE cargado por el usuario en la sesión de la Vista 3.5.
2. Archivo PE de esta carpeta.
3. Plantilla institucional general `data/Plant_Necesidad_Inversion_Acueducto.xls`, si existiera.
4. Formato de respaldo generado por el aplicativo.

La identificación de una plantilla cargada se realiza por el código `PE-001` … `PE-008` presente en el nombre del archivo.

## Exportación conjunta

La Vista 3.5 permite descargar un ZIP con las ocho fichas XLS. Cada ficha utiliza sus ajustes guardados durante la sesión; para las fichas aún no abiertas se calculan los valores vigentes a partir de la cartera de la Vista 3.4.
