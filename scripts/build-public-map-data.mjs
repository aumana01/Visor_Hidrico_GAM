import fs from "node:fs/promises";
import path from "node:path";
import process from "node:process";
import XLSX from "xlsx";
import simplify from "@turf/simplify";

const ROOT = path.resolve(import.meta.dirname, "..");
const SOURCE = path.resolve(
  process.env.PUBLIC_MAP_SOURCE_DIR || path.join(ROOT, ".public-map-source"),
);
const OUTPUT = path.join(ROOT, "docs", "data");
const GAM_BOUNDS = [-84.66, 9.48, -83.76, 10.19];

const FILES = {
  systems: "Sistemas_y_Zonas_de_Abastecimiento.json",
  water: "DATOS HÍDRICOS PUBLICO.xlsx",
  municipal: "Acueductos_Municipales.json",
  esph: "ESPH_AP.json",
  asadas: "ASADAS.json",
  ona: "Cobertura_ONAs_BD.json",
  protected: "Áreas_Protegidas.json",
  districts: "Distritos_GAM.json",
};

function clean(value) {
  if (value === null || value === undefined) return "";
  return String(value).trim();
}

function normalizeCode(value) {
  return clean(value).toUpperCase().replace(/[^A-Z0-9]/g, "");
}

function publicCode(value) {
  const normalized = normalizeCode(value);
  const match = normalized.match(/^MEA(\d{2})$/);
  return match ? `ME-A-${match[1]}` : clean(value);
}

function finite(value) {
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function findColumn(row, prefix) {
  const key = Object.keys(row).find((candidate) =>
    candidate.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase()
      .startsWith(prefix),
  );
  return key ? row[key] : null;
}

async function readGeoJSON(fileName) {
  const raw = await fs.readFile(path.join(SOURCE, fileName), "utf8");
  const parsed = JSON.parse(raw.replace(/^\uFEFF/, ""));
  if (parsed.type !== "FeatureCollection" || !Array.isArray(parsed.features)) {
    throw new Error(`${fileName} no es una colección GeoJSON válida.`);
  }
  return parsed;
}

function coordinateBounds(value, bounds = [Infinity, Infinity, -Infinity, -Infinity]) {
  if (!Array.isArray(value)) return bounds;
  if (
    value.length >= 2
    && typeof value[0] === "number"
    && typeof value[1] === "number"
  ) {
    bounds[0] = Math.min(bounds[0], value[0]);
    bounds[1] = Math.min(bounds[1], value[1]);
    bounds[2] = Math.max(bounds[2], value[0]);
    bounds[3] = Math.max(bounds[3], value[1]);
    return bounds;
  }
  for (const child of value) coordinateBounds(child, bounds);
  return bounds;
}

function intersects(feature, target = GAM_BOUNDS) {
  if (!feature?.geometry?.coordinates) return false;
  const bounds = coordinateBounds(feature.geometry.coordinates);
  return !(
    bounds[2] < target[0]
    || bounds[0] > target[2]
    || bounds[3] < target[1]
    || bounds[1] > target[3]
  );
}

function roundCoordinates(value, precision) {
  if (!Array.isArray(value)) return value;
  if (value.length >= 2 && typeof value[0] === "number" && typeof value[1] === "number") {
    const factor = 10 ** precision;
    return value.map((number) => (
      typeof number === "number" ? Math.round(number * factor) / factor : number
    ));
  }
  return value.map((child) => roundCoordinates(child, precision));
}

function mapFeatures(collection, mapper, options = {}) {
  const { withinGam = false, tolerance = 0, precision = 6 } = options;
  const features = [];
  for (const sourceFeature of collection.features) {
    if (!sourceFeature?.geometry) continue;
    if (withinGam && !intersects(sourceFeature)) continue;
    const mapped = mapper(sourceFeature);
    if (!mapped?.geometry) continue;
    const cleaned = tolerance > 0
      ? simplify(mapped, { tolerance, highQuality: true, mutate: false })
      : mapped;
    if (cleaned.geometry?.coordinates) {
      cleaned.geometry.coordinates = roundCoordinates(cleaned.geometry.coordinates, precision);
    }
    features.push(cleaned);
  }
  return { type: "FeatureCollection", features };
}

async function readWaterData() {
  const workbook = XLSX.readFile(path.join(SOURCE, FILES.water), {
    cellDates: false,
    dense: false,
  });
  const sheet = workbook.Sheets[workbook.SheetNames[0]];
  const rows = XLSX.utils.sheet_to_json(sheet, { defval: null, raw: true });
  const result = new Map();

  for (const row of rows) {
    const code = normalizeCode(row["Código del Sistema"] || row.COD);
    if (!code) continue;
    const balance = finite(findColumn(row, "balance del sistema"));
    const ich = clean(findColumn(row, "clasificacion ich"));
    const period = finite(row["Período"]);
    result.set(code, {
      code: publicCode(code),
      name: clean(row["Nombre del Sistema"]),
      balance,
      condition: balance === null ? "Sin clasificación" : balance < 0 ? "Déficit" : "Superávit",
      ich: ["I", "II", "III", "IV"].includes(ich) ? ich : "Sin clasificación",
      period,
    });
  }
  return result;
}

function feature(geometry, properties) {
  return { type: "Feature", geometry, properties };
}

async function writeJson(fileName, value) {
  await fs.writeFile(path.join(OUTPUT, fileName), `${JSON.stringify(value)}\n`, "utf8");
}

await fs.mkdir(OUTPUT, { recursive: true });
const water = await readWaterData();

const sourceSystems = await readGeoJSON(FILES.systems);
const systems = mapFeatures(
  sourceSystems,
  ({ geometry, properties: source }) => {
    const code = normalizeCode(source.Codigo_Sis);
    const current = water.get(code);
    const fallbackBalance = finite(source.Balance);
    const balance = current?.balance ?? fallbackBalance;
    return feature(geometry, {
      codigo: current?.code || publicCode(code),
      nombre: current?.name || clean(source.Nombre_Sis),
      condicion: current?.condition || (balance !== null && balance < 0 ? "Déficit" : "Superávit"),
      ich: current?.ich || clean(source.ICH) || "Sin clasificación",
    });
  },
  { tolerance: 0.000055 },
);

const municipalSource = await readGeoJSON(FILES.municipal);
const municipal = mapFeatures(
  municipalSource,
  ({ geometry, properties: source }) => feature(geometry, {
    operador: clean(source.Operador) || "Acueducto municipal",
    sistema: clean(source.Sistema) || "Sin nombre",
  }),
  { withinGam: true, tolerance: 0.00022, precision: 5 },
);

const esphSource = await readGeoJSON(FILES.esph);
const esph = mapFeatures(
  esphSource,
  ({ geometry }) => feature(geometry, {
    operador: "Empresa de Servicios Públicos de Heredia (ESPH)",
    sistema: "Cobertura de agua potable ESPH",
  }),
  { withinGam: true, tolerance: 0.00012, precision: 5 },
);

const asadaSource = await readGeoJSON(FILES.asadas);
const asadas = mapFeatures(
  asadaSource,
  ({ geometry, properties: source }) => feature(geometry, {
    codigo: clean(source.CODIGO_IDEO || source.IDEO),
    operador: clean(source.NOMBRE_DEL_OPERADOR) || clean(source.Ente_Operador) || "ASADA",
  }),
  { withinGam: true },
);

const onaSource = await readGeoJSON(FILES.ona);
const ona = mapFeatures(
  onaSource,
  ({ geometry, properties: source }) => feature(geometry, {
    operador: clean(source.Operador) || "Operador local",
    sistema: clean(source.Sistema) || "Sin nombre",
  }),
  { withinGam: true, tolerance: 0.00018, precision: 5 },
);

const protectedSource = await readGeoJSON(FILES.protected);
const protectedAreas = mapFeatures(
  protectedSource,
  ({ geometry, properties: source }) => feature(geometry, {
    codigo: clean(source.Codigo),
    nombre: clean(source.Nombre) || "Área protegida",
    categoria: clean(source.Categoria),
  }),
  { withinGam: true, tolerance: 0.0002, precision: 5 },
);

const districtSource = await readGeoJSON(FILES.districts);
const districts = mapFeatures(
  districtSource,
  ({ geometry, properties: source }) => feature(geometry, {
    provincia: clean(source.provincia),
    canton: clean(source.canton),
    distrito: clean(source.distrito),
  }),
  { withinGam: true, tolerance: 0.00012, precision: 5 },
);

await Promise.all([
  writeJson("sistemas.geojson", systems),
  writeJson("municipalidades.geojson", municipal),
  writeJson("esph.geojson", esph),
  writeJson("asadas.geojson", asadas),
  writeJson("onas.geojson", ona),
  writeJson("areas-protegidas.geojson", protectedAreas),
  writeJson("distritos.geojson", districts),
]);

const uniqueSystems = [...water.values()];
const metadata = {
  generatedAt: new Date().toISOString(),
  period: Math.max(...uniqueSystems.map((item) => item.period || 0)),
  systems: uniqueSystems.length,
  deficit: uniqueSystems.filter((item) => item.condition === "Déficit").length,
  surplus: uniqueSystems.filter((item) => item.condition === "Superávit").length,
  featureCounts: {
    systems: systems.features.length,
    municipal: municipal.features.length,
    esph: esph.features.length,
    asadas: asadas.features.length,
    ona: ona.features.length,
    protected: protectedAreas.features.length,
    districts: districts.features.length,
  },
};
await writeJson("metadata.json", metadata);

console.log(JSON.stringify(metadata, null, 2));
