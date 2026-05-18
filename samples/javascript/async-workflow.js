'use strict';

// Promise workflow baseline that performs multiple asynchronous jobs and reports order clearly.
const wait = (milliseconds) => new Promise((resolve) => {
  setTimeout(resolve, milliseconds);
});

const runJob = (name, delayMilliseconds, shouldFail) => wait(delayMilliseconds)
  .then(() => {
    if (shouldFail) {
      return {
        name,
        status: 'failed',
        detail: `${name} failed after ${delayMilliseconds}ms`,
      };
    }

    return {
      name,
      status: 'succeeded',
      detail: `${name} completed after ${delayMilliseconds}ms`,
    };
  });

const runWorkflow = () => {
  const jobs = [
    runJob('readConfig', 10, false),
    runJob('loadCache', 5, false),
    runJob('warmSearchIndex', 15, true),
  ];

  return Promise.all(jobs).then((results) => {
    const sortedResults = results.slice().sort((left, right) => left.name.localeCompare(right.name));

    console.log('Async Workflow');
    console.log('==============');
    sortedResults.forEach((result) => {
      console.log(`${result.name}: ${result.status} - ${result.detail}`);
    });
  });
};

runWorkflow().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
