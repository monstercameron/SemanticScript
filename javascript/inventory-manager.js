'use strict';

// In-memory inventory workflow with create, update, transfer-like sales, and deletion.
let inventoryItems = [];
let nextInventoryItemId = 1;
const auditLog = [];

const recordAudit = (message) => {
  auditLog.push(message);
};

const addItem = (name, stockCount, reorderPoint) => {
  const item = {
    id: nextInventoryItemId,
    name,
    stockCount,
    reorderPoint,
  };

  nextInventoryItemId += 1;
  inventoryItems.push(item);
  recordAudit(`added ${name}`);
  return item;
};

const receiveStock = (itemId, quantity) => {
  inventoryItems = inventoryItems.map((item) => (
    item.id === itemId
      ? Object.assign({}, item, { stockCount: item.stockCount + quantity })
      : item
  ));

  recordAudit(`received ${quantity} for item ${itemId}`);
};

const sellStock = (itemId, quantity) => {
  const item = inventoryItems.find((currentItem) => currentItem.id === itemId);

  if (!item || item.stockCount < quantity) {
    recordAudit(`rejected sale ${quantity} for item ${itemId}`);
    return false;
  }

  inventoryItems = inventoryItems.map((currentItem) => (
    currentItem.id === itemId
      ? Object.assign({}, currentItem, { stockCount: currentItem.stockCount - quantity })
      : currentItem
  ));

  recordAudit(`sold ${quantity} for item ${itemId}`);
  return true;
};

const removeDiscontinuedItem = (itemId) => {
  inventoryItems = inventoryItems.filter((item) => item.id !== itemId);
  recordAudit(`removed item ${itemId}`);
};

const printInventory = () => {
  console.log('Current Inventory');
  console.log('-----------------');

  inventoryItems.forEach((item) => {
    const status = item.stockCount <= item.reorderPoint ? 'reorder' : 'ok';
    console.log(`${item.id}. ${item.name} stock=${item.stockCount} reorderPoint=${item.reorderPoint} status=${status}`);
  });
};

const notebook = addItem('Notebook', 10, 3);
const pencil = addItem('Pencil', 25, 10);
const marker = addItem('Marker', 4, 5);

sellStock(notebook.id, 3);
sellStock(pencil.id, 30);
receiveStock(marker.id, 12);
removeDiscontinuedItem(pencil.id);

console.log('Inventory Manager');
console.log('=================');
printInventory();
console.log('');
console.log('Audit Log');
console.log('---------');
auditLog.forEach((entry) => console.log(entry));
