#include "sem_win32_gui_runtime.h"

#include <stdlib.h>
#include <string.h>

#ifdef _WIN32

#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <commctrl.h>

#ifndef EM_SETCUEBANNER
#define EM_SETCUEBANNER 0x1501
#endif

#ifndef DWMWA_WINDOW_CORNER_PREFERENCE
#define DWMWA_WINDOW_CORNER_PREFERENCE 33
#endif

#ifndef DWMWA_SYSTEMBACKDROP_TYPE
#define DWMWA_SYSTEMBACKDROP_TYPE 38
#endif

#ifndef DWMWCP_ROUND
#define DWMWCP_ROUND 2
#endif

#ifndef DWMSBT_MAINWINDOW
#define DWMSBT_MAINWINDOW 2
#endif

/* R-200: confine optional-DLL loads to System32 (anti-side-load). Defined since
 * the Windows 8 SDK; provide the literal value for older headers. */
#ifndef LOAD_LIBRARY_SEARCH_SYSTEM32
#define LOAD_LIBRARY_SEARCH_SYSTEM32 0x00000800
#endif

#define SS_GUI_CLASS_NAME L"SemanticScriptGuiWindow"
#define SS_GUI_DEFAULT_WINDOW_WIDTH 800
#define SS_GUI_DEFAULT_WINDOW_HEIGHT 600
#define SS_GUI_PADDING 16
#define SS_GUI_GAP 10

typedef HRESULT (WINAPI *SSGuiDwmSetWindowAttributeFn)(HWND, DWORD, LPCVOID, DWORD);
typedef UINT (WINAPI *SSGuiGetDpiForWindowFn)(HWND);

typedef struct SSGuiWindowState SSGuiWindowState;
typedef struct SSGuiControlState SSGuiControlState;
typedef struct SSGuiApplicationBuilder SSGuiApplicationBuilder;
typedef struct SSGuiWindowBuilder SSGuiWindowBuilder;
typedef struct SSGuiControlBuilder SSGuiControlBuilder;

struct SSGuiWindowState {
    const SSGuiWindowConfig *config;
    SSGuiSession *session;
    HWND hwnd;
};

struct SSGuiControlState {
    const SSGuiControlConfig *config;
    SSGuiWindowState *window;
    HWND hwnd;
    WNDPROC original_proc;
    int suppress_change_events;
    /* R-265: per-control UTF-8 buffer backing ss_gui_text_box_text. A SHARED
     * session buffer meant reading any text box realloc'd it, invalidating the
     * pointer a prior read of a DIFFERENT box had returned (use-after-free). Each
     * control owns its buffer (freed with the control array), so a returned
     * pointer stays valid until that same box is read again. */
    char *text_buffer;
    size_t text_buffer_capacity;
};

struct SSGuiSession {
    const SSGuiApplicationConfig *config;
    DWORD gui_thread_id;
    HINSTANCE instance;
    SSGuiWindowState *windows;
    size_t window_count;
    SSGuiControlState *controls;
    size_t control_count;
    HFONT control_font;
    int owns_control_font;
    int32_t run_status;
};

struct SSGuiEvent {
    int32_t kind;
    int32_t target_kind;
    uint32_t target_id;
    SSGuiWindowId window_id;
    SSGuiControlId control_id;
    int32_t key_code;
    int32_t selected_index;
    int32_t window_width;
    int32_t window_height;
    int32_t cancel_close;
};

struct SSGuiControlBuilder {
    SSGuiControlConfig config;
    SSGuiEventConfig *events;
    size_t event_count;
    size_t event_capacity;
};

struct SSGuiWindowBuilder {
    SSGuiWindowConfig config;
    SSGuiControlBuilder **controls;
    size_t control_count;
    size_t control_capacity;
};

struct SSGuiApplicationBuilder {
    char *title;
    SSGuiWindowBuilder *main_window;
};

static LRESULT CALLBACK ss_gui_window_proc(HWND hwnd, UINT message, WPARAM wparam, LPARAM lparam);
static LRESULT CALLBACK ss_gui_control_subclass_proc(HWND hwnd, UINT message, WPARAM wparam, LPARAM lparam);

static char *ss_gui_strdup(const char *text) {
    const char *source = text != NULL ? text : "";
    size_t length = strlen(source);
    char *copy = (char *)malloc(length + 1);
    if (copy == NULL) {
        return NULL;
    }
    memcpy(copy, source, length + 1);
    return copy;
}

static int32_t normalize_layout(int32_t layout) {
    return layout == SS_GUI_WINDOW_LAYOUT_DEFAULT
        ? SS_GUI_WINDOW_LAYOUT_VERTICAL_STACK
        : layout;
}

static int32_t normalize_selection_mode(int32_t selection_mode) {
    return selection_mode == SS_GUI_LIST_BOX_SELECTION_DEFAULT
        ? SS_GUI_LIST_BOX_SELECTION_SINGLE
        : selection_mode;
}

static int is_supported_control_kind(int32_t kind) {
    return kind == SS_GUI_CONTROL_BUTTON
        || kind == SS_GUI_CONTROL_TEXT_BOX
        || kind == SS_GUI_CONTROL_LIST_BOX
        || kind == SS_GUI_CONTROL_CHECK_BOX
        || kind == SS_GUI_CONTROL_TEXT_LABEL;
}

static int is_window_layout_supported(int32_t layout) {
    int32_t normalized = normalize_layout(layout);
    return normalized == SS_GUI_WINDOW_LAYOUT_VERTICAL_STACK
        || normalized == SS_GUI_WINDOW_LAYOUT_HORIZONTAL_STACK;
}

static int is_interactive_control(int32_t kind) {
    return kind == SS_GUI_CONTROL_BUTTON
        || kind == SS_GUI_CONTROL_TEXT_BOX
        || kind == SS_GUI_CONTROL_LIST_BOX
        || kind == SS_GUI_CONTROL_CHECK_BOX;
}

static int32_t configured_width(const SSGuiWindowConfig *config) {
    return config->width > 0 ? config->width : SS_GUI_DEFAULT_WINDOW_WIDTH;
}

static int32_t configured_height(const SSGuiWindowConfig *config) {
    return config->height > 0 ? config->height : SS_GUI_DEFAULT_WINDOW_HEIGHT;
}

static int window_config_exists(const SSGuiApplicationConfig *config, SSGuiWindowId id) {
    size_t index;

    for (index = 0; index < config->window_count; ++index) {
        if (config->windows[index].id == id) {
            return 1;
        }
    }
    return 0;
}

static int control_config_exists(const SSGuiApplicationConfig *config, SSGuiControlId id) {
    size_t index;

    for (index = 0; index < config->control_count; ++index) {
        if (config->controls[index].id == id) {
            return 1;
        }
    }
    return 0;
}

static int32_t validate_application_config(const SSGuiApplicationConfig *config) {
    size_t index;
    size_t other;

    if (config == NULL || config->windows == NULL || config->window_count == 0) {
        return SS_GUI_ERR_CONFIG;
    }
    if (config->control_count > 0 && config->controls == NULL) {
        return SS_GUI_ERR_CONFIG;
    }
    if (config->event_count > 0 && config->events == NULL) {
        return SS_GUI_ERR_CONFIG;
    }
    if (config->main_window_id == 0 || !window_config_exists(config, config->main_window_id)) {
        return SS_GUI_ERR_CONFIG;
    }

    for (index = 0; index < config->window_count; ++index) {
        const SSGuiWindowConfig *window = &config->windows[index];
        if (window->id == 0 || window->width < 0 || window->height < 0 ||
                window->minimum_width < 0 || window->minimum_height < 0) {
            return SS_GUI_ERR_CONFIG;
        }
        if (!is_window_layout_supported(window->layout)) {
            return SS_GUI_ERR_UNSUPPORTED;
        }
        for (other = index + 1; other < config->window_count; ++other) {
            if (config->windows[other].id == window->id) {
                return SS_GUI_ERR_CONFIG;
            }
        }
    }

    for (index = 0; index < config->control_count; ++index) {
        const SSGuiControlConfig *control = &config->controls[index];
        if (control->id == 0 || control->window_id == 0 ||
                control->width < 0 || control->height < 0 ||
                control->max_length < 0) {
            return SS_GUI_ERR_CONFIG;
        }
        if (!window_config_exists(config, control->window_id)) {
            return SS_GUI_ERR_CONFIG;
        }
        if (!is_supported_control_kind(control->kind)) {
            return SS_GUI_ERR_UNSUPPORTED;
        }
        if (control->kind == SS_GUI_CONTROL_LIST_BOX) {
            int32_t selection_mode = normalize_selection_mode(control->selection_mode);
            if (selection_mode != SS_GUI_LIST_BOX_SELECTION_SINGLE &&
                    selection_mode != SS_GUI_LIST_BOX_SELECTION_MULTIPLE) {
                return SS_GUI_ERR_CONFIG;
            }
        }
        for (other = index + 1; other < config->control_count; ++other) {
            if (config->controls[other].id == control->id) {
                return SS_GUI_ERR_CONFIG;
            }
        }
    }

    for (index = 0; index < config->event_count; ++index) {
        const SSGuiEventConfig *event_config = &config->events[index];
        if (event_config->handler == NULL) {
            return SS_GUI_ERR_CONFIG;
        }
        if (event_config->target_kind == SS_GUI_TARGET_WINDOW) {
            if (!window_config_exists(config, event_config->target_id)) {
                return SS_GUI_ERR_CONFIG;
            }
        } else if (event_config->target_kind == SS_GUI_TARGET_CONTROL) {
            if (!control_config_exists(config, event_config->target_id)) {
                return SS_GUI_ERR_CONFIG;
            }
        } else {
            return SS_GUI_ERR_CONFIG;
        }
    }

    return SS_GUI_OK;
}

static wchar_t *utf8_to_wide(const char *text) {
    const char *source = text != NULL ? text : "";
    int needed = MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS, source, -1, NULL, 0);
    wchar_t *result;

    if (needed == 0) {
        needed = MultiByteToWideChar(CP_UTF8, 0, source, -1, NULL, 0);
        if (needed == 0) {
            return NULL;
        }
    }

    result = (wchar_t *)malloc((size_t)needed * sizeof(wchar_t));
    if (result == NULL) {
        return NULL;
    }

    if (MultiByteToWideChar(CP_UTF8, 0, source, -1, result, needed) == 0) {
        free(result);
        return NULL;
    }

    return result;
}

static int32_t initialize_common_controls(void) {
    INITCOMMONCONTROLSEX controls;

    memset(&controls, 0, sizeof(controls));
    controls.dwSize = sizeof(controls);
    controls.dwICC = ICC_STANDARD_CLASSES | ICC_WIN95_CLASSES;

    return InitCommonControlsEx(&controls) ? SS_GUI_OK : SS_GUI_ERR_PLATFORM;
}

static UINT dpi_for_window(HWND hwnd) {
    HMODULE user32 = GetModuleHandleW(L"user32.dll");
    HWND dc_owner = hwnd;
    HDC dc;
    int dpi;

    if (user32 != NULL && hwnd != NULL) {
        SSGuiGetDpiForWindowFn get_dpi_for_window =
            (SSGuiGetDpiForWindowFn)GetProcAddress(user32, "GetDpiForWindow");
        if (get_dpi_for_window != NULL) {
            UINT window_dpi = get_dpi_for_window(hwnd);
            if (window_dpi > 0) {
                return window_dpi;
            }
        }
    }

    dc = GetDC(hwnd);
    if (dc == NULL && hwnd != NULL) {
        dc_owner = NULL;
        dc = GetDC(NULL);
    }
    if (dc == NULL) {
        return 96;
    }

    dpi = GetDeviceCaps(dc, LOGPIXELSX);
    ReleaseDC(dc_owner, dc);

    return dpi > 0 ? (UINT)dpi : 96;
}

static int scale_for_window(HWND hwnd, int value) {
    if (value <= 0) {
        return value;
    }
    return MulDiv(value, (int)dpi_for_window(hwnd), 96);
}

static int32_t initialize_session_font(SSGuiSession *session) {
    NONCLIENTMETRICSW metrics;

    if (session == NULL) {
        return SS_GUI_ERR_CONFIG;
    }

    memset(&metrics, 0, sizeof(metrics));
    metrics.cbSize = sizeof(metrics);
    if (SystemParametersInfoW(SPI_GETNONCLIENTMETRICS, sizeof(metrics), &metrics, 0)) {
        session->control_font = CreateFontIndirectW(&metrics.lfMessageFont);
        if (session->control_font != NULL) {
            session->owns_control_font = 1;
            return SS_GUI_OK;
        }
    }

    session->control_font = (HFONT)GetStockObject(DEFAULT_GUI_FONT);
    session->owns_control_font = 0;
    return session->control_font != NULL ? SS_GUI_OK : SS_GUI_ERR_PLATFORM;
}

static void release_session_font(SSGuiSession *session) {
    if (session != NULL && session->owns_control_font && session->control_font != NULL) {
        DeleteObject(session->control_font);
    }
    if (session != NULL) {
        session->control_font = NULL;
        session->owns_control_font = 0;
    }
}

static void apply_modern_window_frame(HWND hwnd) {
    HMODULE dwmapi;
    SSGuiDwmSetWindowAttributeFn set_window_attribute;
    int corner_preference = DWMWCP_ROUND;
    int backdrop_type = DWMSBT_MAINWINDOW;

    if (hwnd == NULL) {
        return;
    }

    /* R-200: load the optional DWM styling DLL from System32 ONLY. A bare
     * LoadLibraryW("dwmapi.dll") honors the standard search order (including the
     * application and current directory), so a packaged app launched from a
     * writable directory containing a malicious dwmapi.dll would side-load it and
     * run attacker code before the window is drawn. LOAD_LIBRARY_SEARCH_SYSTEM32
     * pins the search to the system directory. If the flag is unsupported (very old
     * Windows) the call fails and we simply skip the optional styling — fail safe. */
    dwmapi = LoadLibraryExW(L"dwmapi.dll", NULL, LOAD_LIBRARY_SEARCH_SYSTEM32);
    if (dwmapi == NULL) {
        return;
    }

    set_window_attribute =
        (SSGuiDwmSetWindowAttributeFn)GetProcAddress(dwmapi, "DwmSetWindowAttribute");
    if (set_window_attribute != NULL) {
        (void)set_window_attribute(
            hwnd,
            DWMWA_WINDOW_CORNER_PREFERENCE,
            &corner_preference,
            sizeof(corner_preference)
        );
        (void)set_window_attribute(
            hwnd,
            DWMWA_SYSTEMBACKDROP_TYPE,
            &backdrop_type,
            sizeof(backdrop_type)
        );
    }

    FreeLibrary(dwmapi);
}

static void apply_control_font(const SSGuiSession *session, HWND hwnd) {
    if (session != NULL && session->control_font != NULL && hwnd != NULL) {
        SendMessageW(hwnd, WM_SETFONT, (WPARAM)session->control_font, TRUE);
    }
}

static SSGuiWindowState *find_window_state(SSGuiSession *session, SSGuiWindowId id) {
    size_t index;

    if (session == NULL) {
        return NULL;
    }
    for (index = 0; index < session->window_count; ++index) {
        if (session->windows[index].config->id == id) {
            return &session->windows[index];
        }
    }
    return NULL;
}

static SSGuiControlState *find_control_state(SSGuiSession *session, SSGuiControlId id) {
    size_t index;

    if (session == NULL) {
        return NULL;
    }
    for (index = 0; index < session->control_count; ++index) {
        if (session->controls[index].config->id == id) {
            return &session->controls[index];
        }
    }
    return NULL;
}

static SSGuiControlState *find_control_state_by_hwnd(SSGuiSession *session, HWND hwnd) {
    size_t index;

    if (session == NULL || hwnd == NULL) {
        return NULL;
    }
    for (index = 0; index < session->control_count; ++index) {
        if (session->controls[index].hwnd == hwnd) {
            return &session->controls[index];
        }
    }
    return NULL;
}

static SSGuiHandler find_event_handler(
    SSGuiSession *session,
    int32_t target_kind,
    uint32_t target_id,
    int32_t event_kind
) {
    size_t index;

    if (session == NULL || session->config == NULL) {
        return NULL;
    }

    for (index = 0; index < session->config->event_count; ++index) {
        const SSGuiEventConfig *event_config = &session->config->events[index];
        if (event_config->target_kind == target_kind &&
                event_config->target_id == target_id &&
                event_config->event_kind == event_kind) {
            return event_config->handler;
        }
    }

    return NULL;
}

static int32_t dispatch_event(SSGuiSession *session, SSGuiEvent *event) {
    SSGuiHandler handler;
    int32_t status;

    if (session == NULL || event == NULL) {
        return SS_GUI_ERR_CONFIG;
    }

    handler = find_event_handler(session, event->target_kind, event->target_id, event->kind);
    if (handler == NULL) {
        return SS_GUI_OK;
    }

    status = handler(session, event);
    if (status != SS_GUI_OK && session->run_status == SS_GUI_OK) {
        session->run_status = SS_GUI_ERR_HANDLER;
    }
    return status;
}

static int32_t dispatch_window_event(
    SSGuiWindowState *window,
    int32_t event_kind,
    int32_t width,
    int32_t height
) {
    SSGuiEvent event;

    if (window == NULL || window->session == NULL || window->config == NULL) {
        return SS_GUI_ERR_CONFIG;
    }

    memset(&event, 0, sizeof(event));
    event.kind = event_kind;
    event.target_kind = SS_GUI_TARGET_WINDOW;
    event.target_id = window->config->id;
    event.window_id = window->config->id;
    event.window_width = width;
    event.window_height = height;

    return dispatch_event(window->session, &event);
}

static int32_t dispatch_control_event(
    SSGuiControlState *control,
    int32_t event_kind,
    int32_t key_code,
    int32_t selected_index
) {
    SSGuiEvent event;

    if (control == NULL || control->window == NULL || control->window->session == NULL ||
            control->config == NULL) {
        return SS_GUI_ERR_CONFIG;
    }

    memset(&event, 0, sizeof(event));
    event.kind = event_kind;
    event.target_kind = SS_GUI_TARGET_CONTROL;
    event.target_id = control->config->id;
    event.window_id = control->window->config->id;
    event.control_id = control->config->id;
    event.key_code = key_code;
    event.selected_index = selected_index;

    return dispatch_event(control->window->session, &event);
}

static int control_preferred_height(const SSGuiControlState *control) {
    HWND hwnd = control != NULL && control->window != NULL ? control->window->hwnd : NULL;
    int base_height;

    switch (control->config->kind) {
        case SS_GUI_CONTROL_TEXT_LABEL:
            base_height = 24;
            break;
        case SS_GUI_CONTROL_TEXT_BOX:
            base_height = 32;
            break;
        case SS_GUI_CONTROL_BUTTON:
        case SS_GUI_CONTROL_CHECK_BOX:
            base_height = 36;
            break;
        case SS_GUI_CONTROL_LIST_BOX:
            base_height = 144;
            break;
        default:
            base_height = 32;
            break;
    }

    return scale_for_window(hwnd, base_height);
}

static int count_visible_controls(const SSGuiWindowState *window) {
    SSGuiSession *session = window->session;
    size_t index;
    int count = 0;

    for (index = 0; index < session->control_count; ++index) {
        const SSGuiControlState *control = &session->controls[index];
        if (control->window == window && control->hwnd != NULL && control->config->visible) {
            ++count;
        }
    }

    return count;
}

static void layout_vertical_stack(SSGuiWindowState *window, const RECT *client_rect) {
    SSGuiSession *session = window->session;
    int visible_count = count_visible_controls(window);
    int client_width = client_rect->right - client_rect->left;
    int client_height = client_rect->bottom - client_rect->top;
    int padding = scale_for_window(window->hwnd, SS_GUI_PADDING);
    int gap = scale_for_window(window->hwnd, SS_GUI_GAP);
    int content_width = client_width - (padding * 2);
    int available_height;
    int fixed_total = 0;
    int flexible_count = 0;
    int flexible_height = 0;
    int y = padding;
    size_t index;

    if (visible_count <= 0 || content_width <= 0 || client_height <= 0) {
        return;
    }

    available_height = client_height - (padding * 2) - (gap * (visible_count - 1));
    if (available_height < 0) {
        available_height = client_height;
    }

    for (index = 0; index < session->control_count; ++index) {
        const SSGuiControlState *control = &session->controls[index];
        if (control->window != window || control->hwnd == NULL || !control->config->visible) {
            continue;
        }
        if (control->config->kind == SS_GUI_CONTROL_LIST_BOX) {
            ++flexible_count;
        } else {
            fixed_total += control_preferred_height(control);
        }
    }

    if (flexible_count > 0) {
        int minimum_list_height = scale_for_window(window->hwnd, 88);
        flexible_height = (available_height - fixed_total) / flexible_count;
        if (flexible_height < minimum_list_height) {
            flexible_height = minimum_list_height;
        }
    }

    for (index = 0; index < session->control_count; ++index) {
        SSGuiControlState *control = &session->controls[index];
        int height;

        if (control->window != window || control->hwnd == NULL || !control->config->visible) {
            continue;
        }

        height = control->config->kind == SS_GUI_CONTROL_LIST_BOX
            ? flexible_height
            : control_preferred_height(control);
        MoveWindow(control->hwnd, padding, y, content_width, height, TRUE);
        y += height + gap;
    }
}

static void layout_horizontal_stack(SSGuiWindowState *window, const RECT *client_rect) {
    SSGuiSession *session = window->session;
    int visible_count = count_visible_controls(window);
    int client_width = client_rect->right - client_rect->left;
    int client_height = client_rect->bottom - client_rect->top;
    int padding = scale_for_window(window->hwnd, SS_GUI_PADDING);
    int gap = scale_for_window(window->hwnd, SS_GUI_GAP);
    int content_height = client_height - (padding * 2);
    int available_width;
    int control_width;
    int x = padding;
    size_t index;

    if (visible_count <= 0 || content_height <= 0 || client_width <= 0) {
        return;
    }

    available_width = client_width - (padding * 2) - (gap * (visible_count - 1));
    control_width = available_width / visible_count;
    if (control_width < 1) {
        control_width = 1;
    }

    for (index = 0; index < session->control_count; ++index) {
        SSGuiControlState *control = &session->controls[index];
        if (control->window != window || control->hwnd == NULL || !control->config->visible) {
            continue;
        }
        MoveWindow(control->hwnd, x, padding, control_width, content_height, TRUE);
        x += control_width + gap;
    }
}

static void layout_window(SSGuiWindowState *window) {
    RECT client_rect;
    int32_t layout;

    if (window == NULL || window->hwnd == NULL || !GetClientRect(window->hwnd, &client_rect)) {
        return;
    }

    layout = normalize_layout(window->config->layout);
    if (layout == SS_GUI_WINDOW_LAYOUT_HORIZONTAL_STACK) {
        layout_horizontal_stack(window, &client_rect);
    } else {
        layout_vertical_stack(window, &client_rect);
    }
}

static ATOM register_gui_window_class(HINSTANCE instance) {
    WNDCLASSEXW window_class;
    ATOM atom;

    memset(&window_class, 0, sizeof(window_class));
    window_class.cbSize = sizeof(window_class);
    window_class.style = CS_HREDRAW | CS_VREDRAW;
    window_class.lpfnWndProc = ss_gui_window_proc;
    window_class.hInstance = instance;
    window_class.hCursor = LoadCursorW(NULL, MAKEINTRESOURCEW(32512));
    window_class.hbrBackground = (HBRUSH)(COLOR_WINDOW + 1);
    window_class.lpszClassName = SS_GUI_CLASS_NAME;

    atom = RegisterClassExW(&window_class);
    if (atom == 0 && GetLastError() == ERROR_CLASS_ALREADY_EXISTS) {
        return 1;
    }

    return atom;
}

static DWORD window_style_for_config(const SSGuiWindowConfig *config) {
    DWORD style = WS_OVERLAPPED | WS_CAPTION | WS_SYSMENU | WS_MINIMIZEBOX;

    if (config->resizable) {
        style |= WS_THICKFRAME | WS_MAXIMIZEBOX;
    }

    return style;
}

static int32_t create_windows(SSGuiSession *session) {
    size_t index;

    for (index = 0; index < session->window_count; ++index) {
        SSGuiWindowState *window = &session->windows[index];
        const SSGuiWindowConfig *config = window->config;
        wchar_t *title = utf8_to_wide(config->title != NULL
            ? config->title
            : (session->config->title != NULL ? session->config->title : "SemanticScript"));
        DWORD style = window_style_for_config(config);
        RECT rect;

        if (title == NULL) {
            return SS_GUI_ERR_ALLOCATION;
        }

        rect.left = 0;
        rect.top = 0;
        rect.right = configured_width(config);
        rect.bottom = configured_height(config);
        if (!AdjustWindowRectEx(&rect, style, FALSE, 0)) {
            free(title);
            return SS_GUI_ERR_PLATFORM;
        }

        window->hwnd = CreateWindowExW(
            0,
            SS_GUI_CLASS_NAME,
            title,
            style,
            CW_USEDEFAULT,
            CW_USEDEFAULT,
            rect.right - rect.left,
            rect.bottom - rect.top,
            NULL,
            NULL,
            session->instance,
            window
        );
        free(title);

        if (window->hwnd == NULL) {
            return SS_GUI_ERR_PLATFORM;
        }

        apply_modern_window_frame(window->hwnd);
    }

    return SS_GUI_OK;
}

static const wchar_t *control_class_name(int32_t kind) {
    switch (kind) {
        case SS_GUI_CONTROL_BUTTON:
        case SS_GUI_CONTROL_CHECK_BOX:
            return L"BUTTON";
        case SS_GUI_CONTROL_TEXT_BOX:
            return L"EDIT";
        case SS_GUI_CONTROL_LIST_BOX:
            return L"LISTBOX";
        case SS_GUI_CONTROL_TEXT_LABEL:
            return L"STATIC";
        default:
            return L"STATIC";
    }
}

static DWORD control_style(const SSGuiControlConfig *config) {
    DWORD style = WS_CHILD;

    if (config->visible) {
        style |= WS_VISIBLE;
    }
    if (is_interactive_control(config->kind)) {
        style |= WS_TABSTOP;
    }

    switch (config->kind) {
        case SS_GUI_CONTROL_BUTTON:
            style |= config->is_default ? BS_DEFPUSHBUTTON : BS_PUSHBUTTON;
            break;
        case SS_GUI_CONTROL_CHECK_BOX:
            style |= BS_AUTOCHECKBOX;
            break;
        case SS_GUI_CONTROL_TEXT_BOX:
            style |= WS_BORDER | ES_AUTOHSCROLL;
            break;
        case SS_GUI_CONTROL_LIST_BOX:
            style |= WS_BORDER | WS_VSCROLL | LBS_NOTIFY;
            if (normalize_selection_mode(config->selection_mode) == SS_GUI_LIST_BOX_SELECTION_MULTIPLE) {
                style |= LBS_EXTENDEDSEL;
            }
            break;
        case SS_GUI_CONTROL_TEXT_LABEL:
            style |= SS_LEFT;
            break;
        default:
            break;
    }

    return style;
}

static int32_t create_controls(SSGuiSession *session) {
    size_t index;

    for (index = 0; index < session->control_count; ++index) {
        SSGuiControlState *control = &session->controls[index];
        const SSGuiControlConfig *config = control->config;
        SSGuiWindowState *window = find_window_state(session, config->window_id);
        wchar_t *text = utf8_to_wide(config->text);
        HWND hwnd;
        int padding;

        if (window == NULL || window->hwnd == NULL) {
            free(text);
            return SS_GUI_ERR_CONFIG;
        }
        if (text == NULL) {
            return SS_GUI_ERR_ALLOCATION;
        }

        control->window = window;
        padding = scale_for_window(window->hwnd, SS_GUI_PADDING);
        hwnd = CreateWindowExW(
            0,
            control_class_name(config->kind),
            text,
            control_style(config),
            padding,
            padding,
            config->width > 0 ? config->width : scale_for_window(window->hwnd, 160),
            config->height > 0 ? config->height : control_preferred_height(control),
            window->hwnd,
            (HMENU)(UINT_PTR)config->id,
            session->instance,
            NULL
        );
        free(text);

        if (hwnd == NULL) {
            return SS_GUI_ERR_PLATFORM;
        }

        control->hwnd = hwnd;
        SetWindowLongPtrW(hwnd, GWLP_USERDATA, (LONG_PTR)control);
        apply_control_font(session, hwnd);

        if (!config->enabled) {
            EnableWindow(hwnd, FALSE);
        }

        if (config->kind == SS_GUI_CONTROL_TEXT_BOX) {
            if (config->max_length > 0) {
                SendMessageW(hwnd, EM_SETLIMITTEXT, (WPARAM)config->max_length, 0);
            }
            if (config->placeholder != NULL && config->placeholder[0] != '\0') {
                wchar_t *placeholder = utf8_to_wide(config->placeholder);
                if (placeholder == NULL) {
                    return SS_GUI_ERR_ALLOCATION;
                }
                SendMessageW(hwnd, EM_SETCUEBANNER, TRUE, (LPARAM)placeholder);
                free(placeholder);
            }
            control->original_proc = (WNDPROC)SetWindowLongPtrW(
                hwnd,
                GWLP_WNDPROC,
                (LONG_PTR)ss_gui_control_subclass_proc
            );
        } else if (config->kind == SS_GUI_CONTROL_LIST_BOX) {
            control->original_proc = (WNDPROC)SetWindowLongPtrW(
                hwnd,
                GWLP_WNDPROC,
                (LONG_PTR)ss_gui_control_subclass_proc
            );
        }
    }

    for (index = 0; index < session->window_count; ++index) {
        layout_window(&session->windows[index]);
    }

    return SS_GUI_OK;
}

static void destroy_remaining_windows(SSGuiSession *session) {
    size_t index;

    if (session == NULL) {
        return;
    }

    for (index = 0; index < session->window_count; ++index) {
        HWND hwnd = session->windows[index].hwnd;
        if (hwnd != NULL && IsWindow(hwnd)) {
            DestroyWindow(hwnd);
        }
        session->windows[index].hwnd = NULL;
    }
}

static int32_t require_gui_thread(SSGuiSession *session) {
    if (session == NULL) {
        return SS_GUI_ERR_CONFIG;
    }
    if (GetCurrentThreadId() != session->gui_thread_id) {
        return SS_GUI_ERR_THREAD;
    }
    return SS_GUI_OK;
}

static int32_t ensure_control_kind(
    SSGuiSession *session,
    SSGuiControlId control_id,
    int32_t expected_kind,
    SSGuiControlState **out_control
) {
    int32_t status = require_gui_thread(session);
    SSGuiControlState *control;

    if (status != SS_GUI_OK) {
        return status;
    }

    control = find_control_state(session, control_id);
    if (control == NULL || control->hwnd == NULL) {
        return SS_GUI_ERR_NOT_FOUND;
    }
    if (control->config->kind != expected_kind) {
        return SS_GUI_ERR_WRONG_KIND;
    }

    *out_control = control;
    return SS_GUI_OK;
}

static int32_t replace_control_text_buffer(SSGuiControlState *control, const wchar_t *wide_text) {
    int needed = WideCharToMultiByte(CP_UTF8, 0, wide_text, -1, NULL, 0, NULL, NULL);
    char *buffer;

    if (needed <= 0) {
        return SS_GUI_ERR_PLATFORM;
    }

    /* R-265: grow THIS control's buffer only — reading another text box leaves
     * this one's buffer (and any pointer the caller holds into it) untouched. */
    if ((size_t)needed > control->text_buffer_capacity) {
        buffer = (char *)realloc(control->text_buffer, (size_t)needed);
        if (buffer == NULL) {
            return SS_GUI_ERR_ALLOCATION;
        }
        control->text_buffer = buffer;
        control->text_buffer_capacity = (size_t)needed;
    }

    if (WideCharToMultiByte(
            CP_UTF8,
            0,
            wide_text,
            -1,
            control->text_buffer,
            needed,
            NULL,
            NULL
        ) == 0) {
        return SS_GUI_ERR_PLATFORM;
    }

    return SS_GUI_OK;
}

static int32_t selected_index_for_control(SSGuiControlState *control) {
    LRESULT selected = SendMessageW(control->hwnd, LB_GETCURSEL, 0, 0);
    if (selected == LB_ERR) {
        return SS_GUI_INVALID_INDEX;
    }
    return (int32_t)selected;
}

static void handle_command_message(SSGuiWindowState *window, WPARAM wparam, LPARAM lparam) {
    SSGuiSession *session = window->session;
    HWND child_hwnd = (HWND)lparam;
    SSGuiControlState *control = find_control_state_by_hwnd(session, child_hwnd);
    int notification = HIWORD(wparam);

    if (control == NULL) {
        return;
    }

    switch (control->config->kind) {
        case SS_GUI_CONTROL_BUTTON:
            if (notification == BN_CLICKED) {
                (void)dispatch_control_event(control, SS_GUI_EVENT_CLICK, 0, SS_GUI_INVALID_INDEX);
            } else if (notification == BN_SETFOCUS) {
                (void)dispatch_control_event(control, SS_GUI_EVENT_FOCUS_GAINED, 0, SS_GUI_INVALID_INDEX);
            } else if (notification == BN_KILLFOCUS) {
                (void)dispatch_control_event(control, SS_GUI_EVENT_FOCUS_LOST, 0, SS_GUI_INVALID_INDEX);
            }
            break;

        case SS_GUI_CONTROL_CHECK_BOX:
            if (notification == BN_CLICKED) {
                (void)dispatch_control_event(control, SS_GUI_EVENT_VALUE_CHANGED, 0, SS_GUI_INVALID_INDEX);
                (void)dispatch_control_event(control, SS_GUI_EVENT_CLICK, 0, SS_GUI_INVALID_INDEX);
            } else if (notification == BN_SETFOCUS) {
                (void)dispatch_control_event(control, SS_GUI_EVENT_FOCUS_GAINED, 0, SS_GUI_INVALID_INDEX);
            } else if (notification == BN_KILLFOCUS) {
                (void)dispatch_control_event(control, SS_GUI_EVENT_FOCUS_LOST, 0, SS_GUI_INVALID_INDEX);
            }
            break;

        case SS_GUI_CONTROL_TEXT_BOX:
            if (notification == EN_CHANGE && !control->suppress_change_events) {
                (void)dispatch_control_event(control, SS_GUI_EVENT_VALUE_CHANGED, 0, SS_GUI_INVALID_INDEX);
            } else if (notification == EN_SETFOCUS) {
                (void)dispatch_control_event(control, SS_GUI_EVENT_FOCUS_GAINED, 0, SS_GUI_INVALID_INDEX);
            } else if (notification == EN_KILLFOCUS) {
                (void)dispatch_control_event(control, SS_GUI_EVENT_FOCUS_LOST, 0, SS_GUI_INVALID_INDEX);
            }
            break;

        case SS_GUI_CONTROL_LIST_BOX:
            if (notification == LBN_SELCHANGE) {
                int32_t selected_index = selected_index_for_control(control);
                (void)dispatch_control_event(
                    control,
                    SS_GUI_EVENT_SELECTION_CHANGED,
                    0,
                    selected_index
                );
            } else if (notification == LBN_SETFOCUS) {
                (void)dispatch_control_event(control, SS_GUI_EVENT_FOCUS_GAINED, 0, SS_GUI_INVALID_INDEX);
            } else if (notification == LBN_KILLFOCUS) {
                (void)dispatch_control_event(control, SS_GUI_EVENT_FOCUS_LOST, 0, SS_GUI_INVALID_INDEX);
            }
            break;

        default:
            break;
    }
}

static LRESULT CALLBACK ss_gui_control_subclass_proc(
    HWND hwnd,
    UINT message,
    WPARAM wparam,
    LPARAM lparam
) {
    SSGuiControlState *control = (SSGuiControlState *)GetWindowLongPtrW(hwnd, GWLP_USERDATA);

    if (control != NULL && message == WM_KEYDOWN) {
        (void)dispatch_control_event(
            control,
            SS_GUI_EVENT_KEY_PRESSED,
            (int32_t)wparam,
            SS_GUI_INVALID_INDEX
        );
        if (control->config->kind == SS_GUI_CONTROL_TEXT_BOX && wparam == VK_RETURN) {
            (void)dispatch_control_event(
                control,
                SS_GUI_EVENT_ENTER_PRESSED,
                (int32_t)wparam,
                SS_GUI_INVALID_INDEX
            );
            return 0;
        }
    }

    if (control != NULL && control->original_proc != NULL) {
        return CallWindowProcW(control->original_proc, hwnd, message, wparam, lparam);
    }

    return DefWindowProcW(hwnd, message, wparam, lparam);
}

static LRESULT CALLBACK ss_gui_window_proc(HWND hwnd, UINT message, WPARAM wparam, LPARAM lparam) {
    SSGuiWindowState *window = (SSGuiWindowState *)GetWindowLongPtrW(hwnd, GWLP_USERDATA);

    if (message == WM_NCCREATE) {
        CREATESTRUCTW *create_struct = (CREATESTRUCTW *)lparam;
        window = (SSGuiWindowState *)create_struct->lpCreateParams;
        if (window != NULL) {
            window->hwnd = hwnd;
            SetWindowLongPtrW(hwnd, GWLP_USERDATA, (LONG_PTR)window);
        }
        return DefWindowProcW(hwnd, message, wparam, lparam);
    }

    if (window == NULL) {
        return DefWindowProcW(hwnd, message, wparam, lparam);
    }

    switch (message) {
        case WM_COMMAND:
            handle_command_message(window, wparam, lparam);
            return 0;

        case WM_GETMINMAXINFO:
            if (window->config->minimum_width > 0 || window->config->minimum_height > 0) {
                MINMAXINFO *minmax = (MINMAXINFO *)lparam;
                if (window->config->minimum_width > 0) {
                    minmax->ptMinTrackSize.x = window->config->minimum_width;
                }
                if (window->config->minimum_height > 0) {
                    minmax->ptMinTrackSize.y = window->config->minimum_height;
                }
            }
            return 0;

        case WM_SIZE:
            if (wparam != SIZE_MINIMIZED) {
                layout_window(window);
                (void)dispatch_window_event(
                    window,
                    SS_GUI_EVENT_RESIZED,
                    LOWORD(lparam),
                    HIWORD(lparam)
                );
            }
            return 0;

        case WM_SHOWWINDOW:
            if (wparam) {
                RECT rect;
                int32_t width = 0;
                int32_t height = 0;
                if (GetClientRect(hwnd, &rect)) {
                    width = rect.right - rect.left;
                    height = rect.bottom - rect.top;
                }
                (void)dispatch_window_event(window, SS_GUI_EVENT_SHOWN, width, height);
            } else {
                (void)dispatch_window_event(window, SS_GUI_EVENT_HIDDEN, 0, 0);
            }
            return 0;

        case WM_CLOSE: {
            SSGuiEvent event;
            memset(&event, 0, sizeof(event));
            event.kind = SS_GUI_EVENT_CLOSE_REQUESTED;
            event.target_kind = SS_GUI_TARGET_WINDOW;
            event.target_id = window->config->id;
            event.window_id = window->config->id;
            (void)dispatch_event(window->session, &event);
            if (event.cancel_close) {
                return 0;
            }
            DestroyWindow(hwnd);
            return 0;
        }

        case WM_DESTROY:
            window->hwnd = NULL;
            if (window->config->id == window->session->config->main_window_id) {
                PostQuitMessage(0);
            }
            return 0;

        default:
            return DefWindowProcW(hwnd, message, wparam, lparam);
    }
}

int32_t ss_gui_application_run(const SSGuiApplicationConfig *config) {
    SSGuiSession session;
    SSGuiWindowState *main_window;
    MSG message;
    BOOL message_result;
    int32_t status;
    size_t index;

    status = validate_application_config(config);
    if (status != SS_GUI_OK) {
        return status;
    }

    memset(&session, 0, sizeof(session));
    session.config = config;
    session.instance = GetModuleHandleW(NULL);
    session.gui_thread_id = GetCurrentThreadId();
    session.window_count = config->window_count;
    session.control_count = config->control_count;
    session.run_status = SS_GUI_OK;

    status = initialize_common_controls();
    if (status != SS_GUI_OK) {
        return status;
    }

    if (register_gui_window_class(session.instance) == 0) {
        return SS_GUI_ERR_PLATFORM;
    }

    session.windows = (SSGuiWindowState *)calloc(session.window_count, sizeof(SSGuiWindowState));
    if (session.windows == NULL) {
        return SS_GUI_ERR_ALLOCATION;
    }

    if (session.control_count > 0) {
        session.controls = (SSGuiControlState *)calloc(
            session.control_count,
            sizeof(SSGuiControlState)
        );
        if (session.controls == NULL) {
            free(session.windows);
            return SS_GUI_ERR_ALLOCATION;
        }
    }

    for (index = 0; index < session.window_count; ++index) {
        session.windows[index].config = &config->windows[index];
        session.windows[index].session = &session;
    }
    for (index = 0; index < session.control_count; ++index) {
        session.controls[index].config = &config->controls[index];
    }

    status = initialize_session_font(&session);
    if (status != SS_GUI_OK) {
        free(session.controls);
        free(session.windows);
        return status;
    }

    status = create_windows(&session);
    if (status == SS_GUI_OK) {
        status = create_controls(&session);
    }
    if (status != SS_GUI_OK) {
        destroy_remaining_windows(&session);
        release_session_font(&session);
        free(session.controls);
        free(session.windows);
        return status;
    }

    main_window = find_window_state(&session, config->main_window_id);
    if (main_window == NULL || main_window->hwnd == NULL) {
        destroy_remaining_windows(&session);
        release_session_font(&session);
        free(session.controls);
        free(session.windows);
        return SS_GUI_ERR_CONFIG;
    }

    ShowWindow(main_window->hwnd, SW_SHOWNORMAL);
    UpdateWindow(main_window->hwnd);

    while ((message_result = GetMessageW(&message, NULL, 0, 0)) > 0) {
        TranslateMessage(&message);
        DispatchMessageW(&message);
    }

    if (message_result == -1 && session.run_status == SS_GUI_OK) {
        session.run_status = SS_GUI_ERR_PLATFORM;
    }

    if (config->on_exit != NULL) {
        SSGuiEvent exit_event;
        int32_t exit_status;

        memset(&exit_event, 0, sizeof(exit_event));
        exit_event.target_kind = SS_GUI_TARGET_WINDOW;
        exit_event.target_id = config->main_window_id;
        exit_event.window_id = config->main_window_id;
        exit_status = config->on_exit(&session, &exit_event);
        if (exit_status != SS_GUI_OK && session.run_status == SS_GUI_OK) {
            session.run_status = SS_GUI_ERR_HANDLER;
        }
    }

    destroy_remaining_windows(&session);
    release_session_font(&session);
    /* R-265: free each control's owned text buffer before the array block. calloc
     * zeroed the array, and an unread text box keeps a NULL buffer, so free() is a
     * no-op there; a read box's buffer is freed exactly once here. */
    for (size_t control_index = 0; control_index < session.control_count; ++control_index) {
        free(session.controls[control_index].text_buffer);
    }
    free(session.controls);
    free(session.windows);

    return session.run_status;
}

const char *ss_gui_text_box_text(SSGuiSession *session, SSGuiControlId text_box_id) {
    SSGuiControlState *control = NULL;
    int32_t status = ensure_control_kind(
        session,
        text_box_id,
        SS_GUI_CONTROL_TEXT_BOX,
        &control
    );
    int length;
    wchar_t *wide_text;

    if (status != SS_GUI_OK) {
        return NULL;
    }

    length = GetWindowTextLengthW(control->hwnd);
    if (length < 0) {
        return NULL;
    }

    wide_text = (wchar_t *)malloc((size_t)(length + 1) * sizeof(wchar_t));
    if (wide_text == NULL) {
        return NULL;
    }

    if (GetWindowTextW(control->hwnd, wide_text, length + 1) < 0) {
        free(wide_text);
        return NULL;
    }

    status = replace_control_text_buffer(control, wide_text);
    free(wide_text);
    if (status != SS_GUI_OK) {
        return NULL;
    }

    return control->text_buffer;
}

int32_t ss_gui_text_box_set_text(
    SSGuiSession *session,
    SSGuiControlId text_box_id,
    const char *text
) {
    SSGuiControlState *control = NULL;
    int32_t status = ensure_control_kind(
        session,
        text_box_id,
        SS_GUI_CONTROL_TEXT_BOX,
        &control
    );
    wchar_t *wide_text;

    if (status != SS_GUI_OK) {
        return status;
    }

    wide_text = utf8_to_wide(text);
    if (wide_text == NULL) {
        return SS_GUI_ERR_ALLOCATION;
    }

    control->suppress_change_events = 1;
    status = SetWindowTextW(control->hwnd, wide_text) ? SS_GUI_OK : SS_GUI_ERR_PLATFORM;
    control->suppress_change_events = 0;
    free(wide_text);

    return status;
}

int32_t ss_gui_list_box_selected_index(SSGuiSession *session, SSGuiControlId list_box_id) {
    SSGuiControlState *control = NULL;
    int32_t status = ensure_control_kind(
        session,
        list_box_id,
        SS_GUI_CONTROL_LIST_BOX,
        &control
    );

    if (status != SS_GUI_OK) {
        return SS_GUI_INVALID_INDEX;
    }

    return selected_index_for_control(control);
}

int32_t ss_gui_list_box_append_item(
    SSGuiSession *session,
    SSGuiControlId list_box_id,
    const char *text
) {
    SSGuiControlState *control = NULL;
    int32_t status = ensure_control_kind(
        session,
        list_box_id,
        SS_GUI_CONTROL_LIST_BOX,
        &control
    );
    wchar_t *wide_text;
    LRESULT item_index;

    if (status != SS_GUI_OK) {
        return status;
    }

    wide_text = utf8_to_wide(text);
    if (wide_text == NULL) {
        return SS_GUI_ERR_ALLOCATION;
    }

    item_index = SendMessageW(control->hwnd, LB_ADDSTRING, 0, (LPARAM)wide_text);
    free(wide_text);

    if (item_index == LB_ERR || item_index == LB_ERRSPACE) {
        return SS_GUI_ERR_PLATFORM;
    }

    return SS_GUI_OK;
}

int32_t ss_gui_list_box_clear(SSGuiSession *session, SSGuiControlId list_box_id) {
    SSGuiControlState *control = NULL;
    int32_t status = ensure_control_kind(
        session,
        list_box_id,
        SS_GUI_CONTROL_LIST_BOX,
        &control
    );

    if (status != SS_GUI_OK) {
        return status;
    }

    SendMessageW(control->hwnd, LB_RESETCONTENT, 0, 0);
    return SS_GUI_OK;
}

static SSGuiControlId ss_gui_control_id_from_handle(void *control_handle) {
    SSGuiControlBuilder *control = (SSGuiControlBuilder *)control_handle;
    return control != NULL ? control->config.id : 0;
}

static SSGuiWindowId ss_gui_window_id_from_handle(void *window_handle) {
    SSGuiWindowBuilder *window = (SSGuiWindowBuilder *)window_handle;
    return window != NULL ? window->config.id : 0;
}

const char *ss_gui_text_box_text_by_handle(SSGuiSession *session, void *text_box) {
    return ss_gui_text_box_text(session, ss_gui_control_id_from_handle(text_box));
}

int32_t ss_gui_text_box_set_text_by_handle(
    SSGuiSession *session,
    void *text_box,
    const char *text
) {
    return ss_gui_text_box_set_text(session, ss_gui_control_id_from_handle(text_box), text);
}

int32_t ss_gui_list_box_selected_index_by_handle(SSGuiSession *session, void *list_box) {
    return ss_gui_list_box_selected_index(session, ss_gui_control_id_from_handle(list_box));
}

int32_t ss_gui_list_box_append_item_by_handle(
    SSGuiSession *session,
    void *list_box,
    const char *text
) {
    return ss_gui_list_box_append_item(session, ss_gui_control_id_from_handle(list_box), text);
}

int32_t ss_gui_list_box_clear_by_handle(SSGuiSession *session, void *list_box) {
    return ss_gui_list_box_clear(session, ss_gui_control_id_from_handle(list_box));
}

int32_t ss_gui_text_label_set_text_by_handle(
    SSGuiSession *session,
    void *text_label,
    const char *text
) {
    SSGuiControlState *control = NULL;
    int32_t status = ensure_control_kind(
        session,
        ss_gui_control_id_from_handle(text_label),
        SS_GUI_CONTROL_TEXT_LABEL,
        &control
    );
    wchar_t *wide_text;

    if (status != SS_GUI_OK) {
        return status;
    }
    wide_text = utf8_to_wide(text);
    if (wide_text == NULL) {
        return SS_GUI_ERR_ALLOCATION;
    }
    status = SetWindowTextW(control->hwnd, wide_text) ? SS_GUI_OK : SS_GUI_ERR_PLATFORM;
    free(wide_text);
    return status;
}

int32_t ss_gui_window_close(SSGuiSession *session, SSGuiWindowId window_id) {
    SSGuiWindowState *window;
    int32_t status = require_gui_thread(session);

    if (status != SS_GUI_OK) {
        return status;
    }

    window = find_window_state(session, window_id);
    if (window == NULL || window->hwnd == NULL) {
        return SS_GUI_ERR_NOT_FOUND;
    }

    DestroyWindow(window->hwnd);
    return SS_GUI_OK;
}

int32_t ss_gui_window_close_by_handle(SSGuiSession *session, void *window) {
    return ss_gui_window_close(session, ss_gui_window_id_from_handle(window));
}

int32_t ss_gui_event_key_code(const SSGuiEvent *event) {
    return event != NULL ? event->key_code : 0;
}

int32_t ss_gui_event_selected_index(const SSGuiEvent *event) {
    return event != NULL ? event->selected_index : SS_GUI_INVALID_INDEX;
}

int32_t ss_gui_event_window_width(const SSGuiEvent *event) {
    return event != NULL ? event->window_width : 0;
}

int32_t ss_gui_event_window_height(const SSGuiEvent *event) {
    return event != NULL ? event->window_height : 0;
}

int32_t ss_gui_event_cancel_close(SSGuiEvent *event) {
    if (event == NULL || event->kind != SS_GUI_EVENT_CLOSE_REQUESTED) {
        return SS_GUI_ERR_CONFIG;
    }
    event->cancel_close = 1;
    return SS_GUI_OK;
}

void *ss_gui_application_create(const char *title) {
    SSGuiApplicationBuilder *application =
        (SSGuiApplicationBuilder *)calloc(1, sizeof(SSGuiApplicationBuilder));
    if (application == NULL) {
        return NULL;
    }
    application->title = ss_gui_strdup(title != NULL ? title : "SemanticScript");
    if (application->title == NULL) {
        free(application);
        return NULL;
    }
    return application;
}

void *ss_gui_window_create(
    const char *title,
    int32_t width,
    int32_t height,
    int32_t layout,
    int32_t resizable
) {
    SSGuiWindowBuilder *window =
        (SSGuiWindowBuilder *)calloc(1, sizeof(SSGuiWindowBuilder));
    if (window == NULL) {
        return NULL;
    }
    window->config.id = 1;
    window->config.title = ss_gui_strdup(title != NULL ? title : "SemanticScript");
    if (window->config.title == NULL) {
        free(window);
        return NULL;
    }
    window->config.width = width;
    window->config.height = height;
    window->config.minimum_width = width > 320 ? 320 : 0;
    window->config.minimum_height = height > 180 ? 180 : 0;
    window->config.layout = layout;
    window->config.resizable = resizable;
    return window;
}

static void *ss_gui_control_create(
    int32_t kind,
    const char *text,
    const char *placeholder,
    int32_t is_default,
    int32_t max_length,
    int32_t selection_mode
) {
    SSGuiControlBuilder *control =
        (SSGuiControlBuilder *)calloc(1, sizeof(SSGuiControlBuilder));
    if (control == NULL) {
        return NULL;
    }
    control->config.kind = kind;
    control->config.text = ss_gui_strdup(text);
    control->config.placeholder = ss_gui_strdup(placeholder);
    control->config.accessible_name = ss_gui_strdup(text != NULL && text[0] != '\0' ? text : placeholder);
    if (control->config.text == NULL ||
            control->config.placeholder == NULL ||
            control->config.accessible_name == NULL) {
        free((void *)control->config.text);
        free((void *)control->config.placeholder);
        free((void *)control->config.accessible_name);
        free(control);
        return NULL;
    }
    control->config.enabled = 1;
    control->config.visible = 1;
    control->config.is_default = is_default;
    control->config.max_length = max_length;
    control->config.selection_mode = selection_mode;
    return control;
}

void *ss_gui_text_label_create(const char *text) {
    return ss_gui_control_create(
        SS_GUI_CONTROL_TEXT_LABEL, text, "", 0, 0, SS_GUI_LIST_BOX_SELECTION_DEFAULT);
}

void *ss_gui_text_box_create(const char *placeholder, int32_t max_length) {
    return ss_gui_control_create(
        SS_GUI_CONTROL_TEXT_BOX, "", placeholder, 0, max_length, SS_GUI_LIST_BOX_SELECTION_DEFAULT);
}

void *ss_gui_button_create(const char *text, int32_t is_default) {
    return ss_gui_control_create(
        SS_GUI_CONTROL_BUTTON, text, "", is_default, 0, SS_GUI_LIST_BOX_SELECTION_DEFAULT);
}

void *ss_gui_list_box_create(int32_t selection_mode) {
    return ss_gui_control_create(
        SS_GUI_CONTROL_LIST_BOX, "", "", 0, 0, selection_mode);
}

int32_t ss_gui_window_add_control(void *window_handle, void *control_handle) {
    SSGuiWindowBuilder *window = (SSGuiWindowBuilder *)window_handle;
    SSGuiControlBuilder *control = (SSGuiControlBuilder *)control_handle;
    SSGuiControlBuilder **expanded;
    if (window == NULL || control == NULL) {
        return SS_GUI_ERR_CONFIG;
    }
    if (window->control_count == window->control_capacity) {
        /* R-143: guard the doubling and the byte multiply so a pathological
         * count can't wrap to a too-small allocation. */
        size_t cap = window->control_capacity;
        if (cap > SIZE_MAX / 2) {
            return SS_GUI_ERR_ALLOCATION;
        }
        size_t new_capacity = cap == 0 ? 4 : cap * 2;
        if (new_capacity > SIZE_MAX / sizeof(SSGuiControlBuilder *)) {
            return SS_GUI_ERR_ALLOCATION;
        }
        expanded = (SSGuiControlBuilder **)realloc(
            window->controls, new_capacity * sizeof(SSGuiControlBuilder *));
        if (expanded == NULL) {
            return SS_GUI_ERR_ALLOCATION;
        }
        window->controls = expanded;
        window->control_capacity = new_capacity;
    }
    control->config.id = (SSGuiControlId)(1000 + window->control_count);
    control->config.window_id = window->config.id;
    control->config.tab_index = (int32_t)window->control_count;
    window->controls[window->control_count++] = control;
    return SS_GUI_OK;
}

int32_t ss_gui_control_on_event(
    void *control_handle,
    int32_t event_kind,
    SSGuiHandler handler
) {
    SSGuiControlBuilder *control = (SSGuiControlBuilder *)control_handle;
    SSGuiEventConfig *expanded;
    SSGuiEventConfig *event_config;

    if (control == NULL || handler == NULL || control->config.id == 0) {
        return SS_GUI_ERR_CONFIG;
    }
    if (control->event_count == control->event_capacity) {
        /* R-143: guard the doubling and the byte multiply (see add_control). */
        size_t cap = control->event_capacity;
        if (cap > SIZE_MAX / 2) {
            return SS_GUI_ERR_ALLOCATION;
        }
        size_t new_capacity = cap == 0 ? 2 : cap * 2;
        if (new_capacity > SIZE_MAX / sizeof(SSGuiEventConfig)) {
            return SS_GUI_ERR_ALLOCATION;
        }
        expanded = (SSGuiEventConfig *)realloc(
            control->events, new_capacity * sizeof(SSGuiEventConfig));
        if (expanded == NULL) {
            return SS_GUI_ERR_ALLOCATION;
        }
        control->events = expanded;
        control->event_capacity = new_capacity;
    }

    event_config = &control->events[control->event_count++];
    event_config->target_kind = SS_GUI_TARGET_CONTROL;
    event_config->target_id = control->config.id;
    event_config->event_kind = event_kind;
    event_config->handler = handler;
    return SS_GUI_OK;
}

int32_t ss_gui_application_set_main_window(void *application_handle, void *window_handle) {
    SSGuiApplicationBuilder *application = (SSGuiApplicationBuilder *)application_handle;
    SSGuiWindowBuilder *window = (SSGuiWindowBuilder *)window_handle;
    if (application == NULL || window == NULL) {
        return SS_GUI_ERR_CONFIG;
    }
    application->main_window = window;
    return SS_GUI_OK;
}

int32_t ss_gui_application_run_builder(void *application_handle) {
    SSGuiApplicationBuilder *application = (SSGuiApplicationBuilder *)application_handle;
    SSGuiWindowBuilder *window;
    SSGuiApplicationConfig config;
    SSGuiControlConfig *controls = NULL;
    SSGuiEventConfig *events = NULL;
    size_t event_count = 0;
    size_t event_cursor = 0;
    size_t index;
    size_t event_index;
    int32_t status;

    if (application == NULL || application->main_window == NULL) {
        return SS_GUI_ERR_CONFIG;
    }
    window = application->main_window;
    if (window->control_count > 0) {
        controls = (SSGuiControlConfig *)calloc(
            window->control_count, sizeof(SSGuiControlConfig));
        if (controls == NULL) {
            return SS_GUI_ERR_ALLOCATION;
        }
        for (index = 0; index < window->control_count; ++index) {
            controls[index] = window->controls[index]->config;
            event_count += window->controls[index]->event_count;
        }
    }
    if (event_count > 0) {
        events = (SSGuiEventConfig *)calloc(event_count, sizeof(SSGuiEventConfig));
        if (events == NULL) {
            free(controls);
            return SS_GUI_ERR_ALLOCATION;
        }
        for (index = 0; index < window->control_count; ++index) {
            SSGuiControlBuilder *control = window->controls[index];
            for (event_index = 0; event_index < control->event_count; ++event_index) {
                events[event_cursor] = control->events[event_index];
                events[event_cursor].target_id = control->config.id;
                ++event_cursor;
            }
        }
    }

    memset(&config, 0, sizeof(config));
    config.application_name = "SemanticScriptGui";
    config.title = application->title;
    config.main_window_id = window->config.id;
    config.windows = &window->config;
    config.window_count = 1;
    config.controls = controls;
    config.control_count = window->control_count;
    config.events = events;
    config.event_count = event_count;

    status = ss_gui_application_run(&config);
    free(events);
    free(controls);
    return status;
}

int32_t ss_gui_run_window(const char *title, int32_t width, int32_t height) {
    SSGuiWindowConfig window;
    SSGuiApplicationConfig config;

    memset(&window, 0, sizeof(window));
    window.id = 1;
    window.title = title;
    window.width = width;
    window.height = height;
    window.minimum_width = width > 320 ? 320 : 0;
    window.minimum_height = height > 180 ? 180 : 0;
    window.layout = SS_GUI_WINDOW_LAYOUT_VERTICAL_STACK;
    window.resizable = 1;

    memset(&config, 0, sizeof(config));
    config.application_name = "SemanticScriptGui";
    config.title = title;
    config.main_window_id = window.id;
    config.windows = &window;
    config.window_count = 1;

    return ss_gui_application_run(&config);
}

int WINAPI WinMain(HINSTANCE hInstance, HINSTANCE hPrevInstance, LPSTR commandLine, int showCommand) {
    extern int main(void);
    (void)hInstance;
    (void)hPrevInstance;
    (void)commandLine;
    (void)showCommand;
    return main();
}

#else

struct SSGuiSession {
    int unused;
};

struct SSGuiEvent {
    int unused;
};

int32_t ss_gui_application_run(const SSGuiApplicationConfig *config) {
    (void)config;
    return SS_GUI_ERR_RUNTIME_UNAVAILABLE;
}

void *ss_gui_application_create(const char *title) {
    (void)title;
    return NULL;
}

void *ss_gui_window_create(
    const char *title,
    int32_t width,
    int32_t height,
    int32_t layout,
    int32_t resizable
) {
    (void)title;
    (void)width;
    (void)height;
    (void)layout;
    (void)resizable;
    return NULL;
}

void *ss_gui_text_label_create(const char *text) {
    (void)text;
    return NULL;
}

void *ss_gui_text_box_create(const char *placeholder, int32_t max_length) {
    (void)placeholder;
    (void)max_length;
    return NULL;
}

void *ss_gui_button_create(const char *text, int32_t is_default) {
    (void)text;
    (void)is_default;
    return NULL;
}

void *ss_gui_list_box_create(int32_t selection_mode) {
    (void)selection_mode;
    return NULL;
}

int32_t ss_gui_window_add_control(void *window, void *control) {
    (void)window;
    (void)control;
    return SS_GUI_ERR_RUNTIME_UNAVAILABLE;
}

int32_t ss_gui_control_on_event(void *control, int32_t event_kind, SSGuiHandler handler) {
    (void)control;
    (void)event_kind;
    (void)handler;
    return SS_GUI_ERR_RUNTIME_UNAVAILABLE;
}

int32_t ss_gui_application_set_main_window(void *application, void *window) {
    (void)application;
    (void)window;
    return SS_GUI_ERR_RUNTIME_UNAVAILABLE;
}

int32_t ss_gui_application_run_builder(void *application) {
    (void)application;
    return SS_GUI_ERR_RUNTIME_UNAVAILABLE;
}

int32_t ss_gui_run_window(const char *title, int32_t width, int32_t height) {
    (void)title;
    (void)width;
    (void)height;
    return SS_GUI_ERR_RUNTIME_UNAVAILABLE;
}

const char *ss_gui_text_box_text(SSGuiSession *session, SSGuiControlId text_box_id) {
    (void)session;
    (void)text_box_id;
    return NULL;
}

int32_t ss_gui_text_box_set_text(
    SSGuiSession *session,
    SSGuiControlId text_box_id,
    const char *text
) {
    (void)session;
    (void)text_box_id;
    (void)text;
    return SS_GUI_ERR_RUNTIME_UNAVAILABLE;
}

const char *ss_gui_text_box_text_by_handle(SSGuiSession *session, void *text_box) {
    (void)session;
    (void)text_box;
    return NULL;
}

int32_t ss_gui_text_box_set_text_by_handle(
    SSGuiSession *session,
    void *text_box,
    const char *text
) {
    (void)session;
    (void)text_box;
    (void)text;
    return SS_GUI_ERR_RUNTIME_UNAVAILABLE;
}

int32_t ss_gui_list_box_selected_index(SSGuiSession *session, SSGuiControlId list_box_id) {
    (void)session;
    (void)list_box_id;
    return SS_GUI_INVALID_INDEX;
}

int32_t ss_gui_list_box_append_item(
    SSGuiSession *session,
    SSGuiControlId list_box_id,
    const char *text
) {
    (void)session;
    (void)list_box_id;
    (void)text;
    return SS_GUI_ERR_RUNTIME_UNAVAILABLE;
}

int32_t ss_gui_list_box_clear(SSGuiSession *session, SSGuiControlId list_box_id) {
    (void)session;
    (void)list_box_id;
    return SS_GUI_ERR_RUNTIME_UNAVAILABLE;
}

int32_t ss_gui_list_box_selected_index_by_handle(SSGuiSession *session, void *list_box) {
    (void)session;
    (void)list_box;
    return SS_GUI_INVALID_INDEX;
}

int32_t ss_gui_list_box_append_item_by_handle(
    SSGuiSession *session,
    void *list_box,
    const char *text
) {
    (void)session;
    (void)list_box;
    (void)text;
    return SS_GUI_ERR_RUNTIME_UNAVAILABLE;
}

int32_t ss_gui_list_box_clear_by_handle(SSGuiSession *session, void *list_box) {
    (void)session;
    (void)list_box;
    return SS_GUI_ERR_RUNTIME_UNAVAILABLE;
}

int32_t ss_gui_text_label_set_text_by_handle(
    SSGuiSession *session,
    void *text_label,
    const char *text
) {
    (void)session;
    (void)text_label;
    (void)text;
    return SS_GUI_ERR_RUNTIME_UNAVAILABLE;
}

int32_t ss_gui_window_close(SSGuiSession *session, SSGuiWindowId window_id) {
    (void)session;
    (void)window_id;
    return SS_GUI_ERR_RUNTIME_UNAVAILABLE;
}

int32_t ss_gui_window_close_by_handle(SSGuiSession *session, void *window) {
    (void)session;
    (void)window;
    return SS_GUI_ERR_RUNTIME_UNAVAILABLE;
}

int32_t ss_gui_event_key_code(const SSGuiEvent *event) {
    (void)event;
    return 0;
}

int32_t ss_gui_event_selected_index(const SSGuiEvent *event) {
    (void)event;
    return SS_GUI_INVALID_INDEX;
}

int32_t ss_gui_event_window_width(const SSGuiEvent *event) {
    (void)event;
    return 0;
}

int32_t ss_gui_event_window_height(const SSGuiEvent *event) {
    (void)event;
    return 0;
}

int32_t ss_gui_event_cancel_close(SSGuiEvent *event) {
    (void)event;
    return SS_GUI_ERR_RUNTIME_UNAVAILABLE;
}

#endif
