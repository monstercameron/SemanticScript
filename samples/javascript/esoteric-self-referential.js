'use strict';

const vm = require('vm');

// Generates a program that prints itself, then runs it in a sandbox to verify it.
const quote = (value) => JSON.stringify(value);

const template = (templateSource, quoteSource) => [
  "'use strict';",
  `const template = ${templateSource};`,
  `const quote = ${quoteSource};`,
  "console.log(template(template.toString(), quote.toString()));",
].join('\n');

const generatedSource = template(template.toString(), quote.toString());
const sandboxOutput = [];

vm.runInNewContext(generatedSource, {
  console: {
    log: (value) => {
      sandboxOutput.push(value);
    },
  },
});

const reproducedSource = sandboxOutput.join('\n');
const generatedLines = generatedSource.split(/\r?\n/);

console.log('Esoteric Self Referential Program');
console.log('=================================');
console.log(`reproducesItself: ${reproducedSource === generatedSource}`);
console.log(`generatedLineCount: ${generatedLines.length}`);
console.log(`generatedCharacterCount: ${generatedSource.length}`);
console.log('generatedPreview:');
generatedLines.slice(0, 4).forEach((line) => {
  console.log(line);
});
