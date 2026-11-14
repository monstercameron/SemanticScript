#include "sem_win32_gui_runtime.h"

#include <stdio.h>

enum {
    DEMO_WINDOW = 1,
    DEMO_LABEL = 10,
    DEMO_TEXT_BOX = 11,
    DEMO_LIST_BOX = 12,
    DEMO_BUTTON = 13
};

static int32_t on_main_window_shown(SSGuiSession *session, SSGuiEvent *event) {
    const char *text;
    int32_t status;

    (void)event;

    status = ss_gui_text_box_set_text(session, DEMO_TEXT_BOX, "hello from gui runtime");
    if (status != SS_GUI_OK) {
        return status;
    }

    status = ss_gui_list_box_append_item(session, DEMO_LIST_BOX, "first list item");
    if (status != SS_GUI_OK) {
        return status;
    }

    status = ss_gui_list_box_append_item(session, DEMO_LIST_BOX, "second list item");
    if (status != SS_GUI_OK) {
        return status;
    }

    text = ss_gui_text_box_text(session, DEMO_TEXT_BOX);
    printf("sem_win32_gui_health_demo: text_box_text=\"%s\"\n", text != NULL ? text : "<NULL>");

    return ss_gui_window_close(session, DEMO_WINDOW);
}

static int32_t on_close_clicked(SSGuiSession *session, SSGuiEvent *event) {
    (void)event;
    return ss_gui_window_close(session, DEMO_WINDOW);
}

int main(void) {
    const SSGuiWindowConfig windows[] = {
        {
            DEMO_WINDOW,
            "SemanticScript GUI Health Demo",
            480,
            320,
            320,
            240,
            SS_GUI_WINDOW_LAYOUT_VERTICAL_STACK,
            1
        }
    };

    const SSGuiControlConfig controls[] = {
        {
            DEMO_LABEL,
            DEMO_WINDOW,
            SS_GUI_CONTROL_TEXT_LABEL,
            "Runtime-created Win32 controls",
            NULL,
            NULL,
            0,
            0,
            0,
            0,
            1,
            1,
            0,
            0,
            0,
            0
        },
        {
            DEMO_TEXT_BOX,
            DEMO_WINDOW,
            SS_GUI_CONTROL_TEXT_BOX,
            "",
            "Type text",
            "Demo text box",
            0,
            0,
            0,
            0,
            1,
            1,
            1,
            0,
            256,
            0
        },
        {
            DEMO_LIST_BOX,
            DEMO_WINDOW,
            SS_GUI_CONTROL_LIST_BOX,
            "",
            NULL,
            "Demo list box",
            0,
            0,
            0,
            0,
            1,
            1,
            2,
            0,
            0,
            SS_GUI_LIST_BOX_SELECTION_SINGLE
        },
        {
            DEMO_BUTTON,
            DEMO_WINDOW,
            SS_GUI_CONTROL_BUTTON,
            "Close",
            NULL,
            "Close",
            0,
            0,
            0,
            0,
            1,
            1,
            3,
            1,
            0,
            0
        }
    };

    const SSGuiEventConfig events[] = {
        {
            SS_GUI_TARGET_WINDOW,
            DEMO_WINDOW,
            SS_GUI_EVENT_SHOWN,
            on_main_window_shown
        },
        {
            SS_GUI_TARGET_CONTROL,
            DEMO_BUTTON,
            SS_GUI_EVENT_CLICK,
            on_close_clicked
        }
    };

    const SSGuiApplicationConfig app = {
        "semWin32GuiHealthDemo",
        "SemanticScript GUI Health Demo",
        DEMO_WINDOW,
        windows,
        sizeof(windows) / sizeof(windows[0]),
        controls,
        sizeof(controls) / sizeof(controls[0]),
        events,
        sizeof(events) / sizeof(events[0]),
        NULL,
        NULL
    };

    int32_t status = ss_gui_application_run(&app);
    if (status != SS_GUI_OK && status != SS_GUI_ERR_RUNTIME_UNAVAILABLE) {
        fprintf(stderr, "sem_win32_gui_health_demo: failed status=%d\n", status);
        return status;
    }

    printf("sem_win32_gui_health_demo: status=%d\n", status);
    return status == SS_GUI_ERR_RUNTIME_UNAVAILABLE ? 0 : status;
}
