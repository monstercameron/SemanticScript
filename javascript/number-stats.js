'use strict';

// Computes common statistics over a fixed data set for easy console checking.
const values = [42, 7, 19, 7, 100, 13, 42, 58, 7, 31];

const sortNumbers = (numbers) => numbers.slice().sort((left, right) => left - right);

const sumNumbers = (numbers) => numbers.reduce((sum, value) => sum + value, 0);

const calculateMean = (numbers) => sumNumbers(numbers) / numbers.length;

const calculateMedian = (numbers) => {
  const sortedNumbers = sortNumbers(numbers);
  const middleIndex = Math.floor(sortedNumbers.length / 2);

  if (sortedNumbers.length % 2 === 1) {
    return sortedNumbers[middleIndex];
  }

  return (sortedNumbers[middleIndex - 1] + sortedNumbers[middleIndex]) / 2;
};

const calculateMode = (numbers) => {
  const countsByValue = numbers.reduce((counts, value) => {
    counts[value] = (counts[value] || 0) + 1;
    return counts;
  }, {});

  return Object.keys(countsByValue)
    .map(Number)
    .sort((left, right) => countsByValue[right] - countsByValue[left] || left - right)[0];
};

const calculatePopulationStandardDeviation = (numbers) => {
  const mean = calculateMean(numbers);
  const variance = numbers.reduce((sum, value) => {
    const difference = value - mean;
    return sum + (difference * difference);
  }, 0) / numbers.length;

  return Math.sqrt(variance);
};

console.log('Number Statistics');
console.log('=================');
console.log(`values: ${values.join(', ')}`);
console.log(`sorted: ${sortNumbers(values).join(', ')}`);
console.log(`count: ${values.length}`);
console.log(`sum: ${sumNumbers(values)}`);
console.log(`min: ${Math.min.apply(null, values)}`);
console.log(`max: ${Math.max.apply(null, values)}`);
console.log(`mean: ${calculateMean(values).toFixed(2)}`);
console.log(`median: ${calculateMedian(values)}`);
console.log(`mode: ${calculateMode(values)}`);
console.log(`populationStdDev: ${calculatePopulationStandardDeviation(values).toFixed(2)}`);
