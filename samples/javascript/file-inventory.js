'use strict';

const fs = require('fs');
const path = require('path');

// Uses only built-in modules to summarize the JavaScript benchmark folder.
const currentDirectory = __dirname;

const files = fs.readdirSync(currentDirectory)
  .filter((fileName) => fileName.endsWith('.js'))
  .sort();

const padLeft = (value, width) => {
  const text = String(value);
  return ' '.repeat(Math.max(width - text.length, 0)) + text;
};

const padRight = (value, width) => {
  const text = String(value);
  return text + ' '.repeat(Math.max(width - text.length, 0));
};

const fileSummaries = files.map((fileName) => {
  const filePath = path.join(currentDirectory, fileName);
  const fileContents = fs.readFileSync(filePath, 'utf8');

  return {
    fileName,
    bytes: Buffer.byteLength(fileContents, 'utf8'),
    lines: fileContents.split(/\r?\n/).length,
  };
});

console.log('JavaScript Folder Inventory');
console.log('===========================');
console.log(`directory: ${currentDirectory}`);
console.log(`scriptCount: ${fileSummaries.length}`);

fileSummaries.forEach((summary) => {
  console.log(`${padRight(summary.fileName, 26)} lines=${padLeft(summary.lines, 3)} bytes=${summary.bytes}`);
});
