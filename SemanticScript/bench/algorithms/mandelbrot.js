// mandelbrot.js - escape-time Mandelbrot over a WIDTH x HEIGHT grid.
// Mirrors mandelbrot.c exactly: same grid, same iteration cap, same order of
// floating-point operations (separate temporaries, no FMA), so the summed
// iteration-count checksum is identical across all four languages.

const width = 600;
const height = 400;
const maxIterations = 1000;

const xMin = -2.0;
const xMax = 1.0;
const yMin = -1.0;
const yMax = 1.0;
const escapeRadiusSquared = 4.0;

let totalIterations = 0;

const start = performance.now();
for (let pixelRow = 0; pixelRow < height; pixelRow++) {
  const rowFraction = pixelRow / height;
  const imaginaryC = yMin + (yMax - yMin) * rowFraction;
  for (let pixelCol = 0; pixelCol < width; pixelCol++) {
    const colFraction = pixelCol / width;
    const realC = xMin + (xMax - xMin) * colFraction;

    let realZ = 0.0;
    let imaginaryZ = 0.0;
    let iteration = 0;
    while (iteration < maxIterations) {
      const realSquared = realZ * realZ;
      const imaginarySquared = imaginaryZ * imaginaryZ;
      const magnitudeSquared = realSquared + imaginarySquared;
      if (magnitudeSquared > escapeRadiusSquared) {
        break;
      }
      const realDifference = realSquared - imaginarySquared;
      const nextRealZ = realDifference + realC;
      const realTimesImaginary = realZ * imaginaryZ;
      const doubledCrossTerm = 2.0 * realTimesImaginary;
      const nextImaginaryZ = doubledCrossTerm + imaginaryC;
      realZ = nextRealZ;
      imaginaryZ = nextImaginaryZ;
      iteration++;
    }
    totalIterations += iteration;
  }
}
const end = performance.now();

const elapsedSeconds = (end - start) / 1000;
console.log(`checksum=${totalIterations} elapsedSeconds=${elapsedSeconds.toFixed(6)}`);
