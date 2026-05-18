'use strict';

// Tiny concatenative stack language inspired by Forth.
// The program defines words, then executes them with a data stack.
const source = `
: square dup * ;
: cube dup dup * * ;
: average + 2 / ;
5 square print
3 cube print
9 3 average print
7 4 swap - print
`;

const tokenize = (text) => text.trim().split(/\s+/);

const parseProgram = (tokens) => {
  const definitions = {};
  const mainTokens = [];

  for (let index = 0; index < tokens.length; index += 1) {
    const token = tokens[index];

    if (token !== ':') {
      mainTokens.push(token);
      continue;
    }

    const wordName = tokens[index + 1];
    const bodyTokens = [];
    index += 2;

    while (index < tokens.length && tokens[index] !== ';') {
      bodyTokens.push(tokens[index]);
      index += 1;
    }

    definitions[wordName] = bodyTokens;
  }

  return {
    definitions,
    mainTokens,
  };
};

const popNumber = (stack, operationName) => {
  if (stack.length === 0) {
    throw new Error(`${operationName} expected a number`);
  }

  return stack.pop();
};

const executeToken = (token, runtime) => {
  const stack = runtime.stack;

  if (/^-?\d+$/.test(token)) {
    stack.push(Number(token));
    return;
  }

  if (runtime.definitions[token]) {
    executeTokens(runtime.definitions[token], runtime);
    return;
  }

  if (token === '+') {
    stack.push(popNumber(stack, '+') + popNumber(stack, '+'));
    return;
  }

  if (token === '-') {
    const right = popNumber(stack, '-');
    const left = popNumber(stack, '-');
    stack.push(left - right);
    return;
  }

  if (token === '*') {
    stack.push(popNumber(stack, '*') * popNumber(stack, '*'));
    return;
  }

  if (token === '/') {
    const right = popNumber(stack, '/');
    const left = popNumber(stack, '/');
    stack.push(left / right);
    return;
  }

  if (token === 'dup') {
    const value = popNumber(stack, 'dup');
    stack.push(value);
    stack.push(value);
    return;
  }

  if (token === 'swap') {
    const right = popNumber(stack, 'swap');
    const left = popNumber(stack, 'swap');
    stack.push(right);
    stack.push(left);
    return;
  }

  if (token === 'print') {
    runtime.output.push(popNumber(stack, 'print'));
    return;
  }

  throw new Error(`Unknown token: ${token}`);
};

const executeTokens = (tokens, runtime) => {
  tokens.forEach((token) => {
    executeToken(token, runtime);
  });
};

const parsedProgram = parseProgram(tokenize(source));
const runtime = {
  definitions: parsedProgram.definitions,
  output: [],
  stack: [],
};

executeTokens(parsedProgram.mainTokens, runtime);

console.log('Esoteric Stack Language');
console.log('=======================');
console.log('source:');
console.log(source.trim());
console.log('output:');
runtime.output.forEach((value) => {
  console.log(value);
});
console.log(`finalStackDepth: ${runtime.stack.length}`);
