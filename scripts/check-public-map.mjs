import fs from "node:fs/promises";
import path from "node:path";
import process from "node:process";

const ROOT = path.resolve(import.meta.dirname, "..");
const DOCS = path.join(ROOT, "docs");
const DATA = path.join(DOCS, "data");

const specifications = {
  "sistemas.geojson": ["codigo", "nombre", "condicion", "ich"],
  "municipalidades.geojson": ["operador", "sistema"],
  "esph.geojson": ["operador", "sistema"],
  "asadas.geojson": ["codigo", "operador"],
  "onas.geojson": ["operador", "sistema"],
  "areas-protegidas.geojson": ["codigo", "nombre", "categoria"],
  "distritos.geojson": ["provincia", "canton", "distrito"],
};

const forbiddenKeys = /correo|tel[eé]fono|globalid|objectid|created_|edited_|servicios|balance|fuente/i;
const failures = [];

function visitCoordinates(value, fileName) {
  if (!Array.isArray(value)) return;
  if (value.length >= 2 && typeof value[0] === "number" && typeof value[1] === "number") {
    const [longitude, latitude] = value;
    if (longitude < -86.5 || longitude > -82 || latitude < 8 || latitude > 11.5) {
      failures.push(`${fileName}: coordenada fuera del ámbito esperado (${longitude}, ${latitude}).`);
    }
    return;
  }
  for (const child of value) visitCoordinates(child, fileName);
}

for (const [fileName, allowedKeys] of Object.entries(specifications)) {
  const fullPath = path.join(DATA, fileName);
  const stat = await fs.stat(fullPath).catch(() => null);
  if (!stat) {
    failures.push(`${fileName}: archivo faltante.`);
    continue;
  }
  if (stat.size > 5_000_000) failures.push(`${fileName}: supera 5 MB.`);
  const data = JSON.parse(await fs.readFile(fullPath, "utf8"));
  if (data.type !== "FeatureCollection" || !Array.isArray(data.features)) {
    failures.push(`${fileName}: estructura GeoJSON inválida.`);
    continue;
  }
  for (const item of data.features) {
    if (!item.geometry) failures.push(`${fileName}: contiene geometría nula.`);
    const keys = Object.keys(item.properties || {});
    const extra = keys.filter((key) => !allowedKeys.includes(key));
    if (extra.length) failures.push(`${fileName}: atributos no autorizados: ${extra.join(", ")}.`);
    const forbidden = keys.filter((key) => forbiddenKeys.test(key));
    if (forbidden.length) failures.push(`${fileName}: atributos sensibles: ${forbidden.join(", ")}.`);
    visitCoordinates(item.geometry?.coordinates, fileName);
  }
}

const systems = JSON.parse(await fs.readFile(path.join(DATA, "sistemas.geojson"), "utf8"));
const uniqueSystems = new Map();
for (const item of systems.features) {
  const { codigo, nombre, condicion, ich } = item.properties;
  uniqueSystems.set(codigo, item.properties);
  if (!codigo || !nombre) failures.push("sistemas.geojson: sistema sin código o nombre.");
  if (!["Déficit", "Superávit"].includes(condicion)) {
    failures.push(`${codigo}: condición pública inválida.`);
  }
  if (!["I", "II", "III", "IV"].includes(ich)) failures.push(`${codigo}: ICH inválido.`);
}
if (uniqueSystems.size !== 31) failures.push(`Se esperaban 31 sistemas y se encontraron ${uniqueSystems.size}.`);

const metadata = JSON.parse(await fs.readFile(path.join(DATA, "metadata.json"), "utf8"));
const deficit = [...uniqueSystems.values()].filter((item) => item.condicion === "Déficit").length;
const surplus = [...uniqueSystems.values()].filter((item) => item.condicion === "Superávit").length;
if (metadata.systems !== uniqueSystems.size || metadata.deficit !== deficit || metadata.surplus !== surplus) {
  failures.push("metadata.json no coincide con los sistemas publicados.");
}

const index = await fs.readFile(path.join(DOCS, "index.html"), "utf8");
const localAssets = [...index.matchAll(/(?:src|href)="([^"#]+)"/g)]
  .map((match) => match[1])
  .filter((asset) => !asset.startsWith("http") && !asset.startsWith("data:"));
for (const asset of localAssets) {
  const assetPath = path.join(DOCS, asset);
  if (!(await fs.stat(assetPath).catch(() => null))) failures.push(`index.html: falta ${asset}.`);
}

if (failures.length) {
  console.error(failures.map((failure) => `- ${failure}`).join("\n"));
  process.exit(1);
}

console.log(JSON.stringify({
  status: "ok",
  systems: uniqueSystems.size,
  deficit,
  surplus,
  assets: localAssets.length,
}, null, 2));
