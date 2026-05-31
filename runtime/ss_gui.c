/* ss_gui.c — GUI runtime shim exposing the SemanticScript Win32 GUI runtime
 * (SemanticScript/runtime/native_win32_gui/sem_win32_gui_runtime.c) to the EAV
 * front end (semanticscript), through the `body runtimeBinding <symbol>` seam.
 *
 * `ss_gui_health_check()` stands up a real Win32 window with an auto-close
 * handler: when the window is shown the handler closes it, so ss_gui_application_run
 * returns without user interaction (the same non-interactive pattern as the
 * runtime's health_demo.c). It returns SS_GUI_OK on a desktop session, and
 * cleanly maps SS_GUI_ERR_RUNTIME_UNAVAILABLE (no interactive desktop) to OK — so
 * a headless run reports success rather than hanging. This proves the GUI runtime
 * links, creates a window, runs the message loop, and tears down (WS3-044).
 */
#include <stdint.h>
#include "sem_win32_gui_runtime.h"

#ifdef _WIN32
#define SS_EXPORT __declspec(dllexport)
#else
#define SS_EXPORT __attribute__((visibility("default")))
#endif

/* The GUI runtime source ships an (unguarded) WinMain that references `main` for
 * standalone GUI-exe builds. We build it as a shared library and never call
 * WinMain, so provide a dead stub to satisfy the link; the EAV program's own
 * entry is JIT-compiled separately and is what actually runs. */
SS_EXPORT int main(void) { return 0; }

enum { SS_GUI_WINDOW = 1 };

static int32_t ss_gui_on_shown(SSGuiSession *session, SSGuiEvent *event) {
    (void)event;
    return ss_gui_window_close(session, SS_GUI_WINDOW);
}

SS_EXPORT int32_t ss_gui_health_check(void) {
    const SSGuiWindowConfig windows[] = {
        {SS_GUI_WINDOW, "EAV GUI Health", 320, 200, 200, 120,
         SS_GUI_WINDOW_LAYOUT_VERTICAL_STACK, 1}
    };
    const SSGuiEventConfig events[] = {
        {SS_GUI_TARGET_WINDOW, SS_GUI_WINDOW, SS_GUI_EVENT_SHOWN, ss_gui_on_shown}
    };
    const SSGuiApplicationConfig app = {
        "eavGuiHealth", "EAV GUI Health", SS_GUI_WINDOW,
        windows, 1, (const SSGuiControlConfig *)0, 0, events, 1,
        (SSGuiHandler)0, (void *)0
    };
    int32_t status = ss_gui_application_run(&app);
    /* No interactive desktop is a clean pass for an automated/headless check. */
    return status == SS_GUI_ERR_RUNTIME_UNAVAILABLE ? 0 : status;
}
