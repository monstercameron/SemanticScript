// Emscripten js-library runtime adapter for standard.document.
//
// Linked into the wasm module by SemanticScript/tools/build_wasm.py via
// `--js-library`. Each `ss_dom_*` entry is the native symbol that the
// standard.document runtimeBinding operations resolve to. DOM nodes never
// cross the wasm boundary directly: they live in a JS-side handle table and
// are referenced from wasm as small integer handles (0 == no node).
//
// `ss_dom_next_event` is declared `__async` so an Asyncify- or JSPI-enabled
// build suspends the wasm stack at the await call site and resumes when the
// next DOM event fires, instead of blocking the browser's single thread.

addToLibrary({
  $SSDom__deps: ['$UTF8ToString', '$stringToUTF8', '$lengthBytesUTF8'],
  $SSDom: {
    // Index 0 is reserved as the "no node" handle.
    nodes: [null],
    // Index 0 is reserved as the "no stream" handle.
    streams: [null],
    // node -> handle, so repeated lookups of the same node reuse a handle in
    // O(1) and the table does not grow per call. WeakMap lets GC reclaim a
    // node's mapping once no DOM reference remains.
    handleByNode: typeof WeakMap !== 'undefined' ? new WeakMap() : null,

    registerNode: function (node) {
      if (!node) return 0;
      if (SSDom.handleByNode && SSDom.handleByNode.has(node)) {
        var existing = SSDom.handleByNode.get(node);
        if (SSDom.nodes[existing] === node) return existing;
      }
      SSDom.nodes.push(node);
      var handle = SSDom.nodes.length - 1;
      if (SSDom.handleByNode) SSDom.handleByNode.set(node, handle);
      return handle;
    },
    node: function (handle) {
      if (handle <= 0 || handle >= SSDom.nodes.length) return null;
      return SSDom.nodes[handle];
    },
    releaseNode: function (handle) {
      var node = SSDom.node(handle);
      if (!node) return -4;
      if (SSDom.handleByNode) SSDom.handleByNode.delete(node);
      SSDom.nodes[handle] = null;
      return 0;
    },
    // Copy a JS string into a wasm buffer as null-terminated UTF-8.
    // Returns bytes written (excluding the null) or -3 (buffer too small).
    writeString: function (str, ptr, cap) {
      if (str === null || str === undefined) str = '';
      var needed = lengthBytesUTF8(str) + 1;
      if (cap <= 0 || needed > cap) return -3;
      stringToUTF8(str, ptr, cap);
      return needed - 1;
    },
  },

  ss_dom_body: function () {
    return SSDom.registerNode(typeof document !== 'undefined' ? document.body : null);
  },
  ss_dom_body__deps: ['$SSDom'],

  ss_dom_document_element: function () {
    return SSDom.registerNode(typeof document !== 'undefined' ? document.documentElement : null);
  },
  ss_dom_document_element__deps: ['$SSDom'],

  ss_dom_get_element_by_id: function (idPtr) {
    return SSDom.registerNode(document.getElementById(UTF8ToString(idPtr)));
  },
  ss_dom_get_element_by_id__deps: ['$SSDom'],

  ss_dom_query_selector: function (selPtr) {
    try {
      return SSDom.registerNode(document.querySelector(UTF8ToString(selPtr)));
    } catch (e) {
      return 0;
    }
  },
  ss_dom_query_selector__deps: ['$SSDom'],

  ss_dom_create_element: function (tagPtr) {
    return SSDom.registerNode(document.createElement(UTF8ToString(tagPtr)));
  },
  ss_dom_create_element__deps: ['$SSDom'],

  ss_dom_create_text_node: function (textPtr) {
    return SSDom.registerNode(document.createTextNode(UTF8ToString(textPtr)));
  },
  ss_dom_create_text_node__deps: ['$SSDom'],

  ss_dom_append_child: function (parentH, childH) {
    var parent = SSDom.node(parentH), child = SSDom.node(childH);
    if (!parent || !child) return -4;
    parent.appendChild(child);
    return 0;
  },
  ss_dom_append_child__deps: ['$SSDom'],

  ss_dom_remove_child: function (parentH, childH) {
    var parent = SSDom.node(parentH), child = SSDom.node(childH);
    if (!parent || !child) return -4;
    try { parent.removeChild(child); } catch (e) { return -1; }
    return 0;
  },
  ss_dom_remove_child__deps: ['$SSDom'],

  ss_dom_set_text_content: function (nodeH, textPtr) {
    var node = SSDom.node(nodeH);
    if (!node) return -4;
    node.textContent = UTF8ToString(textPtr);
    return 0;
  },
  ss_dom_set_text_content__deps: ['$SSDom'],

  ss_dom_get_text_content: function (nodeH, outPtr, cap) {
    var node = SSDom.node(nodeH);
    if (!node) return -4;
    return SSDom.writeString(node.textContent, outPtr, cap);
  },
  ss_dom_get_text_content__deps: ['$SSDom'],

  ss_dom_set_value: function (nodeH, textPtr) {
    var node = SSDom.node(nodeH);
    if (!node) return -4;
    node.value = UTF8ToString(textPtr);
    return 0;
  },
  ss_dom_set_value__deps: ['$SSDom'],

  ss_dom_get_value: function (nodeH, outPtr, cap) {
    var node = SSDom.node(nodeH);
    if (!node) return -4;
    return SSDom.writeString(node.value, outPtr, cap);
  },
  ss_dom_get_value__deps: ['$SSDom'],

  ss_dom_set_inner_html: function (nodeH, markupPtr) {
    var node = SSDom.node(nodeH);
    if (!node) return -4;
    node.innerHTML = UTF8ToString(markupPtr);
    return 0;
  },
  ss_dom_set_inner_html__deps: ['$SSDom'],

  ss_dom_set_attribute: function (nodeH, namePtr, valuePtr) {
    var node = SSDom.node(nodeH);
    if (!node) return -4;
    node.setAttribute(UTF8ToString(namePtr), UTF8ToString(valuePtr));
    return 0;
  },
  ss_dom_set_attribute__deps: ['$SSDom'],

  ss_dom_get_attribute: function (nodeH, namePtr, outPtr, cap) {
    var node = SSDom.node(nodeH);
    if (!node) return -4;
    var value = node.getAttribute(UTF8ToString(namePtr));
    if (value === null) return -2;
    return SSDom.writeString(value, outPtr, cap);
  },
  ss_dom_get_attribute__deps: ['$SSDom'],

  ss_dom_remove_attribute: function (nodeH, namePtr) {
    var node = SSDom.node(nodeH);
    if (!node) return -4;
    node.removeAttribute(UTF8ToString(namePtr));
    return 0;
  },
  ss_dom_remove_attribute__deps: ['$SSDom'],

  ss_dom_class_list_add: function (nodeH, classPtr) {
    var node = SSDom.node(nodeH);
    if (!node) return -4;
    node.classList.add(UTF8ToString(classPtr));
    return 0;
  },
  ss_dom_class_list_add__deps: ['$SSDom'],

  ss_dom_class_list_remove: function (nodeH, classPtr) {
    var node = SSDom.node(nodeH);
    if (!node) return -4;
    node.classList.remove(UTF8ToString(classPtr));
    return 0;
  },
  ss_dom_class_list_remove__deps: ['$SSDom'],

  ss_dom_class_list_toggle: function (nodeH, classPtr) {
    var node = SSDom.node(nodeH);
    if (!node) return -4;
    return node.classList.toggle(UTF8ToString(classPtr)) ? 1 : 0;
  },
  ss_dom_class_list_toggle__deps: ['$SSDom'],

  ss_dom_set_style_property: function (nodeH, propPtr, valuePtr) {
    var node = SSDom.node(nodeH);
    if (!node || !node.style) return -4;
    node.style.setProperty(UTF8ToString(propPtr), UTF8ToString(valuePtr));
    return 0;
  },
  ss_dom_set_style_property__deps: ['$SSDom'],

  ss_dom_add_event_listener: function (nodeH, eventPtr) {
    var node = SSDom.node(nodeH);
    if (!node) return 0;
    var eventName = UTF8ToString(eventPtr);
    // `pending` holds an Asyncify wakeUp callback when a nextEvent await is
    // parked; otherwise events accumulate in `queue`. `current` is the event
    // most recently delivered by nextEvent, queried via the event accessors.
    var stream = { queue: [], closed: false, pending: null, current: null,
                   node: node, eventName: eventName };
    stream.handler = function (ev) {
      if (stream.pending) {
        var wakeUp = stream.pending;
        stream.pending = null;
        stream.current = ev;
        wakeUp(0);
      } else {
        stream.queue.push(ev);
      }
    };
    node.addEventListener(eventName, stream.handler);
    SSDom.streams.push(stream);
    return SSDom.streams.length - 1;
  },
  ss_dom_add_event_listener__deps: ['$SSDom'],

  // Suspends the wasm stack via Asyncify until the next event fires or the
  // stream is removed. `handleSleep` performs the unwind; `wakeUp(value)`
  // schedules the rewind with that DomStatus as the call's return value
  // (0 on an event, -6 when the stream is closed, -7 when a later await
  // displaces this one). `__async` marks the import as permitted to change
  // Asyncify state.
  ss_dom_next_event: function (streamH) {
    return Asyncify.handleSleep(function (wakeUp) {
      var stream = SSDom.streams[streamH];
      if (!stream || stream.closed) { wakeUp(-6); return; }
      if (stream.queue.length > 0) { stream.current = stream.queue.shift(); wakeUp(0); return; }
      // Only one await may park per stream. Cancel any prior waiter so its
      // wasm stack rewinds (with domStatusCancelled) instead of deadlocking.
      if (stream.pending) {
        var stale = stream.pending;
        stream.pending = null;
        stale(-7);
      }
      stream.pending = wakeUp;
    });
  },
  ss_dom_next_event__deps: ['$SSDom', '$Asyncify'],
  ss_dom_next_event__async: true,

  // Handle of the target of the event most recently returned by nextEvent on
  // this stream, or 0 when no event has been delivered.
  ss_dom_event_target: function (streamH) {
    var stream = SSDom.streams[streamH];
    if (!stream || !stream.current) return 0;
    return SSDom.registerNode(stream.current.target);
  },
  ss_dom_event_target__deps: ['$SSDom'],

  // Copy a string property of the current event (e.g. "type", "key",
  // "inputType", "data") into a caller buffer; -2 when the property is absent.
  ss_dom_event_detail: function (streamH, propPtr, outPtr, cap) {
    var stream = SSDom.streams[streamH];
    if (!stream || !stream.current) return -4;
    var value = stream.current[UTF8ToString(propPtr)];
    if (value === null || value === undefined) return -2;
    return SSDom.writeString(String(value), outPtr, cap);
  },
  ss_dom_event_detail__deps: ['$SSDom'],

  ss_dom_remove_event_listener: function (streamH) {
    var stream = SSDom.streams[streamH];
    if (!stream || stream.closed) return -4;
    stream.closed = true;
    try { stream.node.removeEventListener(stream.eventName, stream.handler); } catch (e) {}
    if (stream.pending) {
      var wakeUp = stream.pending;
      stream.pending = null;
      wakeUp(-6);
    }
    SSDom.streams[streamH] = null;
    return 0;
  },
  ss_dom_remove_event_listener__deps: ['$SSDom'],

  ss_dom_release: function (handle) {
    return SSDom.releaseNode(handle);
  },
  ss_dom_release__deps: ['$SSDom'],

  ss_dom_eval_script: function (scriptPtr) {
    try {
      // eslint-disable-next-line no-eval
      (0, eval)(UTF8ToString(scriptPtr));
      return 0;
    } catch (e) {
      return -1;
    }
  },
  ss_dom_eval_script__deps: ['$SSDom'],
});
