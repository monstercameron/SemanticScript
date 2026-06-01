#ifndef SS_RUNTIME_EXPORT_H
#define SS_RUNTIME_EXPORT_H

/* Shared export decoration for runtime shim entry points.
 *
 * The current build compiles these sources into shared runtime libraries and
 * expects exported ss_* symbols by default. Static/import-side modes are opt-in
 * so existing builds keep their previous dllexport/default-visibility behavior.
 */
#if defined(_WIN32)
#  if defined(SS_RUNTIME_STATIC)
#    define SS_EXPORT
#  elif defined(SS_RUNTIME_IMPORT_DLL)
#    define SS_EXPORT __declspec(dllimport)
#  else
#    define SS_EXPORT __declspec(dllexport)
#  endif
#  define SS_LOCAL
#elif defined(__GNUC__) || defined(__clang__)
#  define SS_EXPORT __attribute__((visibility("default")))
#  define SS_LOCAL __attribute__((visibility("hidden")))
#else
#  define SS_EXPORT
#  define SS_LOCAL
#endif

#endif /* SS_RUNTIME_EXPORT_H */
