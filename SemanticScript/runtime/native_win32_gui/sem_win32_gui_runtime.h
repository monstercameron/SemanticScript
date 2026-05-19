#ifndef SEM_WIN32_GUI_RUNTIME_H
#define SEM_WIN32_GUI_RUNTIME_H

/*
 * SemanticScript-owned C ABI for declarative desktop GUI applications.
 *
 * The ABI is intentionally backend-neutral: compiler or standard-library
 * lowering passes numeric window/control ids plus opaque SSGuiSession /
 * SSGuiEvent pointers. The Win32 implementation maps those ids to HWND values
 * internally; future Linux/macOS adapters can keep the same header and provide
 * their own implementation.
 *
 * String convention:
 *   - All inbound strings are UTF-8, null-terminated C strings.
 *   - ss_gui_text_box_text() returns UTF-8 owned by the session. The pointer
 *     is valid until the next ss_gui_text_box_text() call on the same session
 *     or until ss_gui_application_run() returns.
 *
 * Threading convention:
 *   - GUI runtime calls that touch live state must be made from the GUI thread
 *     while an event handler is running. Cross-thread dispatch helpers are a
 *     later ABI addition.
 */

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct SSGuiSession SSGuiSession;
typedef struct SSGuiEvent SSGuiEvent;

typedef uint32_t SSGuiWindowId;
typedef uint32_t SSGuiControlId;

typedef int32_t (*SSGuiHandler)(SSGuiSession *session, SSGuiEvent *event);

enum {
    SS_GUI_OK = 0,
    SS_GUI_ERR_CONFIG = 1,
    SS_GUI_ERR_RUNTIME_UNAVAILABLE = 2,
    SS_GUI_ERR_ALLOCATION = 3,
    SS_GUI_ERR_PLATFORM = 4,
    SS_GUI_ERR_NOT_FOUND = 5,
    SS_GUI_ERR_WRONG_KIND = 6,
    SS_GUI_ERR_HANDLER = 7,
    SS_GUI_ERR_UNSUPPORTED = 8,
    SS_GUI_ERR_THREAD = 9
};

enum {
    SS_GUI_TARGET_WINDOW = 1,
    SS_GUI_TARGET_CONTROL = 2
};

enum {
    SS_GUI_WINDOW_LAYOUT_DEFAULT = 0,
    SS_GUI_WINDOW_LAYOUT_VERTICAL_STACK = 1,
    SS_GUI_WINDOW_LAYOUT_HORIZONTAL_STACK = 2,
    SS_GUI_WINDOW_LAYOUT_GRID = 3,
    SS_GUI_WINDOW_LAYOUT_ABSOLUTE = 4
};

enum {
    SS_GUI_CONTROL_BUTTON = 1,
    SS_GUI_CONTROL_TEXT_BOX = 2,
    SS_GUI_CONTROL_LIST_BOX = 3,
    SS_GUI_CONTROL_CHECK_BOX = 4,
    SS_GUI_CONTROL_MENU_ITEM = 5,
    SS_GUI_CONTROL_STATUS_BAR = 6,
    SS_GUI_CONTROL_TEXT_LABEL = 7
};

enum {
    SS_GUI_LIST_BOX_SELECTION_DEFAULT = 0,
    SS_GUI_LIST_BOX_SELECTION_SINGLE = 1,
    SS_GUI_LIST_BOX_SELECTION_MULTIPLE = 2
};

enum {
    SS_GUI_EVENT_CLICK = 1,
    SS_GUI_EVENT_VALUE_CHANGED = 2,
    SS_GUI_EVENT_SELECTION_CHANGED = 3,
    SS_GUI_EVENT_ENTER_PRESSED = 4,
    SS_GUI_EVENT_KEY_PRESSED = 5,
    SS_GUI_EVENT_FOCUS_GAINED = 6,
    SS_GUI_EVENT_FOCUS_LOST = 7,
    SS_GUI_EVENT_CLOSE_REQUESTED = 8,
    SS_GUI_EVENT_RESIZED = 9,
    SS_GUI_EVENT_SHOWN = 10,
    SS_GUI_EVENT_HIDDEN = 11
};

enum {
    SS_GUI_INVALID_INDEX = -1
};

typedef struct SSGuiWindowConfig {
    SSGuiWindowId id;
    const char *title;
    int32_t width;
    int32_t height;
    int32_t minimum_width;
    int32_t minimum_height;
    int32_t layout;
    int32_t resizable;
} SSGuiWindowConfig;

typedef struct SSGuiControlConfig {
    SSGuiControlId id;
    SSGuiWindowId window_id;
    int32_t kind;
    const char *text;
    const char *placeholder;
    const char *accessible_name;
    int32_t x;
    int32_t y;
    int32_t width;
    int32_t height;
    int32_t enabled;
    int32_t visible;
    int32_t tab_index;
    int32_t is_default;
    int32_t max_length;
    int32_t selection_mode;
} SSGuiControlConfig;

typedef struct SSGuiEventConfig {
    int32_t target_kind;
    uint32_t target_id;
    int32_t event_kind;
    SSGuiHandler handler;
} SSGuiEventConfig;

typedef struct SSGuiApplicationConfig {
    const char *application_name;
    const char *title;
    SSGuiWindowId main_window_id;
    const SSGuiWindowConfig *windows;
    size_t window_count;
    const SSGuiControlConfig *controls;
    size_t control_count;
    const SSGuiEventConfig *events;
    size_t event_count;
    SSGuiHandler on_exit;
    void *user_data;
} SSGuiApplicationConfig;

int32_t ss_gui_run_window(const char *title, int32_t width, int32_t height);
int32_t ss_gui_application_run(const SSGuiApplicationConfig *config);

const char *ss_gui_text_box_text(SSGuiSession *session, SSGuiControlId text_box_id);
int32_t ss_gui_text_box_set_text(
    SSGuiSession *session,
    SSGuiControlId text_box_id,
    const char *text
);

int32_t ss_gui_list_box_selected_index(SSGuiSession *session, SSGuiControlId list_box_id);
int32_t ss_gui_list_box_append_item(
    SSGuiSession *session,
    SSGuiControlId list_box_id,
    const char *text
);
int32_t ss_gui_list_box_clear(SSGuiSession *session, SSGuiControlId list_box_id);

int32_t ss_gui_window_close(SSGuiSession *session, SSGuiWindowId window_id);

int32_t ss_gui_event_key_code(const SSGuiEvent *event);
int32_t ss_gui_event_selected_index(const SSGuiEvent *event);
int32_t ss_gui_event_window_width(const SSGuiEvent *event);
int32_t ss_gui_event_window_height(const SSGuiEvent *event);
int32_t ss_gui_event_cancel_close(SSGuiEvent *event);

#ifdef __cplusplus
}
#endif

#endif
