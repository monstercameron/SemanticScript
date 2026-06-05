#ifndef SEM_WINUI3_GUI_RUNTIME_H
#define SEM_WINUI3_GUI_RUNTIME_H

/*
 * WinUI 3 backend contract for SemanticScript GUI.
 *
 * The WinUI 3 adapter must export the same ss_gui_* C ABI as the current
 * Win32 backend so compiler lowering and standard.gui contracts stay stable.
 * This header intentionally reuses the shared ABI definitions while the C++ /
 * WinRT implementation is developed in this directory.
 */

#include "../native_win32_gui/sem_win32_gui_runtime.h"

#endif
