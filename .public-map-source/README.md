# Fuentes locales del visor público

Esta carpeta está excluida de Git para evitar publicar atributos internos de los
archivos originales. Para actualizar el visor, copie aquí los siguientes archivos
con sus nombres exactos y ejecute `npm run public-map:update`:

- `Sistemas_y_Zonas_de_Abastecimiento.json`
- `DATOS HÍDRICOS PUBLICO.xlsx`
- `Acueductos_Municipales.json`
- `ESPH_AP.json`
- `ASADAS.json`
- `Cobertura_ONAs_BD.json`
- `Áreas_Protegidas.json`
- `Distritos_GAM.json`

El proceso genera archivos GeoJSON depurados en `docs/data/`. Esos son los únicos
archivos geográficos que deben publicarse. Después de generarlos, revise el visor,
confirme los cambios y suba a Git únicamente `docs/data/` y el código que corresponda.

