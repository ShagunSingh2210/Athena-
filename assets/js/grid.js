/**
 * grid.js
 * Day 1 deliverable: city grid definition (2km x 2km cells) + bounding box.
 * JS port of lib/grid.py from the original plan so the math stays identical.
 */
const CITY_BOUNDING_BOXES = {
  Delhi: { latMin: 28.55, latMax: 28.70, lonMin: 77.05, lonMax: 77.25 },
  Mumbai: { latMin: 19.00, latMax: 19.20, lonMin: 72.80, lonMax: 72.95 },
};

const CITY_CENTERS = {
  Delhi: [28.625, 77.15],
  Mumbai: [19.10, 72.875],
};

function kmToLatDeg(km) {
  return km / 111.0;
}
function kmToLonDeg(km, atLat) {
  return km / (111.0 * Math.cos((atLat * Math.PI) / 180));
}

function buildCityGrid(city, cellKm = 2.0) {
  const bbox = CITY_BOUNDING_BOXES[city];
  if (!bbox) throw new Error(`Unknown city '${city}'`);
  const midLat = (bbox.latMin + bbox.latMax) / 2;
  const latStep = kmToLatDeg(cellKm);
  const lonStep = kmToLonDeg(cellKm, midLat);

  const cells = [];
  let lat = bbox.latMin;
  let row = 0;
  while (lat < bbox.latMax) {
    let lon = bbox.lonMin;
    let col = 0;
    while (lon < bbox.lonMax) {
      const cellId = `${city.slice(0, 3).toUpperCase()}-R${String(row).padStart(2, '0')}C${String(col).padStart(2, '0')}`;
      const latMaxCell = Math.min(lat + latStep, bbox.latMax);
      const lonMaxCell = Math.min(lon + lonStep, bbox.lonMax);
      cells.push({
        cellId, row, col,
        latMin: lat, latMax: latMaxCell,
        lonMin: lon, lonMax: lonMaxCell,
        centroid: [(lat + latMaxCell) / 2, (lon + lonMaxCell) / 2],
      });
      lon += lonStep;
      col += 1;
    }
    lat += latStep;
    row += 1;
  }
  return cells;
}
