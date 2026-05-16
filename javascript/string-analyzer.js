'use strict';

// Text analysis baseline with normalization, counting, and simple ranking.
const paragraph = 'AgentScript favors explicit context. Context helps agents patch code. Explicit names reduce guessing.';

const normalizeWord = (word) => word.toLowerCase().replace(/[^a-z]/g, '');

const words = paragraph
  .split(/\s+/)
  .map(normalizeWord)
  .filter((word) => word.length > 0);

const countWords = (wordList) => wordList.reduce((counts, word) => {
  counts[word] = (counts[word] || 0) + 1;
  return counts;
}, {});

const wordCounts = countWords(words);

const topWords = Object.keys(wordCounts)
  .sort((left, right) => wordCounts[right] - wordCounts[left] || left.localeCompare(right))
  .slice(0, 5);

console.log('String Analyzer');
console.log('===============');
console.log(`text: ${paragraph}`);
console.log(`characters: ${paragraph.length}`);
console.log(`words: ${words.length}`);
console.log(`uniqueWords: ${Object.keys(wordCounts).length}`);
console.log('topWords:');

topWords.forEach((word) => {
  console.log(`  ${word}: ${wordCounts[word]}`);
});
