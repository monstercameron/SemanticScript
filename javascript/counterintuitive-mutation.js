'use strict';

// Reference and mutation behavior that surprises people expecting value copies.
const originalProfile = {
  name: 'Ada',
  tags: ['admin', 'beta'],
};

const aliasProfile = originalProfile;
const shallowCopyProfile = Object.assign({}, originalProfile);
const copiedTagsProfile = {
  name: originalProfile.name,
  tags: originalProfile.tags.slice(),
};

aliasProfile.name = 'Grace';
shallowCopyProfile.tags.push('shared-array');
copiedTagsProfile.tags.push('copied-array');

const numbers = [10, 2, 1];
const sortedSameArray = numbers.sort();
const numericSortedCopy = numbers.slice().sort((left, right) => left - right);

const constantObject = {
  status: 'open',
};

constantObject.status = 'closed';

console.log('Counterintuitive Mutation');
console.log('=========================');
console.log(`originalProfile.name => ${originalProfile.name}`);
console.log(`originalProfile.tags => ${originalProfile.tags.join(', ')}`);
console.log(`copiedTagsProfile.tags => ${copiedTagsProfile.tags.join(', ')}`);
console.log(`numbers after sort() => ${numbers.join(', ')}`);
console.log(`sortedSameArray is numbers => ${sortedSameArray === numbers}`);
console.log(`numericSortedCopy => ${numericSortedCopy.join(', ')}`);
console.log(`const object can mutate status => ${constantObject.status}`);
