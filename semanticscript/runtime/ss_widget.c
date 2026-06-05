/*
 * ss_widget.c — headless widget runtime for the `gui.*` intrinsics (APP-RUN-4).
 *
 * The desktop app builds a window + controls, wires control events, and runs the
 * application loop. A real Win32 toolkit cannot be driven non-interactively in
 * CI, so this is an in-memory stub: create entry points hand back monotonic
 * handles, mutators are no-ops returning a 0 status, and application_run returns
 * 0 immediately (no event is delivered headlessly). It proves the app lowers,
 * constructs its full control tree, registers handlers, runs the loop, and exits
 * cleanly — exit 0.
 *
 * Every mutator returns a status int (not void): a given gui.* is called both
 * with `discards` and with `out Int32` across the app, so the symbol needs one
 * fixed signature. Prefixed ss_widget_ (not ss_gui_) so it never collides with
 * the real Win32 runtime's ss_gui_* symbols (which back gui_health_demo).
 */
#include <stdint.h>
#include "ss_runtime_export.h"

static long long ss_widget_next_handle = 1;
static long long ss_widget_new(void) { return ss_widget_next_handle++; }

SS_EXPORT long long ss_widget_application_create(void) { return ss_widget_new(); }

SS_EXPORT long long ss_widget_window_create(const char *title, int width, int height,
                                            int layout, int resizable) {
    (void)title; (void)width; (void)height; (void)layout; (void)resizable;
    return ss_widget_new();
}

SS_EXPORT long long ss_widget_text_label_create(const char *text) {
    (void)text; return ss_widget_new();
}

SS_EXPORT long long ss_widget_text_box_create(const char *placeholder, int max_length) {
    (void)placeholder; (void)max_length; return ss_widget_new();
}

SS_EXPORT long long ss_widget_button_create(const char *text, int is_default) {
    (void)text; (void)is_default; return ss_widget_new();
}

SS_EXPORT long long ss_widget_list_box_create(int selection_mode) {
    (void)selection_mode; return ss_widget_new();
}

SS_EXPORT int ss_widget_window_add_control(long long window, long long control) {
    (void)window; (void)control; return 0;
}

SS_EXPORT int ss_widget_control_on_event(long long control, int event_kind, void *handler) {
    (void)control; (void)event_kind; (void)handler;  /* registered, not fired headlessly */
    return 0;
}

SS_EXPORT int ss_widget_application_set_main_window(long long app, long long window) {
    (void)app; (void)window; return 0;
}

SS_EXPORT int ss_widget_application_run(long long app) {
    (void)app;
    return 0;  /* no interactive event loop in a headless run */
}

SS_EXPORT const char *ss_widget_text_box_text(long long session, long long text_box) {
    (void)session; (void)text_box; return "";
}

SS_EXPORT int ss_widget_list_box_append_item(long long session, long long list_box,
                                             const char *text) {
    (void)session; (void)list_box; (void)text; return 0;
}

SS_EXPORT int ss_widget_text_box_set_text(long long session, long long text_box,
                                          const char *text) {
    (void)session; (void)text_box; (void)text; return 0;
}

SS_EXPORT int ss_widget_list_box_selected_index(long long session, long long list_box) {
    (void)session; (void)list_box; return -1;
}

SS_EXPORT int ss_widget_list_box_clear(long long session, long long list_box) {
    (void)session; (void)list_box; return 0;
}

SS_EXPORT int ss_widget_text_label_set_text(long long session, long long label,
                                            const char *text) {
    (void)session; (void)label; (void)text; return 0;
}
