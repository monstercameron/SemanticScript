'use strict';

const readline = require('readline');

// Raw Node console UI for benchmarking against an AgentScript equivalent.
// Data stays in memory so the program remains dependency-free and deterministic.
const initialTodos = [
  {
    id: 1,
    title: 'Write AgentScript baseline examples',
    completed: false,
  },
  {
    id: 2,
    title: 'Run the JavaScript snippets',
    completed: true,
  },
];

let todos = initialTodos.map((todo) => Object.assign({}, todo));
let nextTodoId = todos.length + 1;

const consoleInterface = readline.createInterface({
  input: process.stdin,
  output: process.stdout,
});

let pendingAnswerResolve = null;
let queuedAnswers = [];
let inputHasClosed = false;

// Queue input lines so the UI works in a real terminal and in scripted benchmarks.
consoleInterface.on('line', (line) => {
  const answer = line.trim();

  if (pendingAnswerResolve) {
    const resolve = pendingAnswerResolve;
    pendingAnswerResolve = null;

    if (!process.stdin.isTTY) {
      console.log(answer);
    }

    resolve(answer);
    return;
  }

  queuedAnswers.push(answer);
});

consoleInterface.on('close', () => {
  inputHasClosed = true;

  if (pendingAnswerResolve) {
    const resolve = pendingAnswerResolve;
    pendingAnswerResolve = null;
    resolve('7');
  }
});

const askQuestion = (promptText) => {
  process.stdout.write(promptText);

  if (queuedAnswers.length > 0) {
    const answer = queuedAnswers.shift();

    // Piped benchmark input is not echoed by a terminal, so echo it for readable logs.
    if (!process.stdin.isTTY) {
      console.log(answer);
    }

    return Promise.resolve(answer);
  }

  if (inputHasClosed) {
    console.log('7');
    return Promise.resolve('7');
  }

  return new Promise((resolve) => {
    pendingAnswerResolve = resolve;
  });
};

const printHeader = (title) => {
  console.log('');
  console.log(title);
  console.log('-'.repeat(title.length));
};

const formatTodoStatus = (todo) => (todo.completed ? 'done' : 'open');

const printTodo = (todo) => {
  console.log(`${todo.id}. [${formatTodoStatus(todo)}] ${todo.title}`);
};

const findTodoById = (id) => todos.find((todo) => todo.id === id);

const askTodoId = async (promptText) => {
  const rawTodoId = await askQuestion(promptText);
  const todoId = Number(rawTodoId);

  if (!Number.isInteger(todoId) || todoId < 1) {
    console.log('Please enter a valid todo id.');
    return null;
  }

  const todo = findTodoById(todoId);

  if (!todo) {
    console.log(`Todo ${todoId} was not found.`);
    return null;
  }

  return todoId;
};

const listTodos = () => {
  printHeader('Todos');

  if (todos.length === 0) {
    console.log('No todos yet.');
    return;
  }

  todos.forEach(printTodo);
};

const viewTodo = async () => {
  const todoId = await askTodoId('Todo id to view: ');

  if (todoId === null) {
    return;
  }

  const todo = findTodoById(todoId);

  printHeader(`Todo ${todo.id}`);
  console.log(`Title: ${todo.title}`);
  console.log(`Status: ${formatTodoStatus(todo)}`);
};

const createTodo = async () => {
  const title = await askQuestion('New todo title: ');

  if (title.length === 0) {
    console.log('Title is required.');
    return;
  }

  const todo = {
    id: nextTodoId,
    title,
    completed: false,
  };

  todos.push(todo);
  nextTodoId += 1;

  console.log(`Created todo ${todo.id}.`);
};

const updateTodoTitle = async () => {
  const todoId = await askTodoId('Todo id to update: ');

  if (todoId === null) {
    return;
  }

  const nextTitle = await askQuestion('Updated title: ');

  if (nextTitle.length === 0) {
    console.log('Title is required.');
    return;
  }

  todos = todos.map((todo) => (
    todo.id === todoId ? Object.assign({}, todo, { title: nextTitle }) : todo
  ));

  console.log(`Updated todo ${todoId}.`);
};

const toggleTodoStatus = async () => {
  const todoId = await askTodoId('Todo id to toggle: ');

  if (todoId === null) {
    return;
  }

  const todo = findTodoById(todoId);
  const nextCompleted = !todo.completed;

  todos = todos.map((currentTodo) => (
    currentTodo.id === todoId
      ? Object.assign({}, currentTodo, { completed: nextCompleted })
      : currentTodo
  ));

  console.log(`Marked todo ${todoId} as ${nextCompleted ? 'done' : 'open'}.`);
};

const deleteTodo = async () => {
  const todoId = await askTodoId('Todo id to delete: ');

  if (todoId === null) {
    return;
  }

  todos = todos.filter((todo) => todo.id !== todoId);
  console.log(`Deleted todo ${todoId}.`);
};

const printMenu = () => {
  console.log('');
  console.log('Todo Console');
  console.log('============');
  console.log('1. List todos');
  console.log('2. View todo');
  console.log('3. Add todo');
  console.log('4. Update todo title');
  console.log('5. Toggle todo complete');
  console.log('6. Delete todo');
  console.log('7. Quit');
  console.log('');
};

const handleMenuChoice = async (choice) => {
  if (choice === '1') {
    listTodos();
    return true;
  }

  if (choice === '2') {
    await viewTodo();
    return true;
  }

  if (choice === '3') {
    await createTodo();
    return true;
  }

  if (choice === '4') {
    await updateTodoTitle();
    return true;
  }

  if (choice === '5') {
    await toggleTodoStatus();
    return true;
  }

  if (choice === '6') {
    await deleteTodo();
    return true;
  }

  if (choice === '7' || choice.toLowerCase() === 'q') {
    return false;
  }

  console.log('Choose a number from 1 to 7.');
  return true;
};

const runTodoConsole = async () => {
  console.log('Raw Node Todo Console');

  let shouldContinue = true;

  while (shouldContinue) {
    printMenu();
    const choice = await askQuestion('Choose an action: ');
    shouldContinue = await handleMenuChoice(choice);
  }

  console.log('Goodbye.');
  consoleInterface.close();
};

consoleInterface.on('SIGINT', () => {
  console.log('');
  console.log('Goodbye.');
  consoleInterface.close();
});

runTodoConsole().catch((error) => {
  console.error(error);
  consoleInterface.close();
  process.exitCode = 1;
});
