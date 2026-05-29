# desktop-window-smoke — EAV port: DEFERRED (X-045)

GUI is not specified in v0.3 and `target windowsGui` is a hard compile error
(SS0744, WS3-044). Per X-045 the app source is intentionally NOT ported; the
conversion target is recorded as the `standard.gui` `.semsig` contract
(`sigs/standard.gui.semsig`): gui entities → `gui.*` calls when a GUI module is
specified. Until then a `target windowsGui` project errors with the reserved-
target diagnostic.
