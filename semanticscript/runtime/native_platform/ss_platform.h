#ifndef SS_PLATFORM_H
#define SS_PLATFORM_H

/*
 * R-022: central native-platform boundary.
 *
 * Runtime modules include this header instead of pulling OS headers directly.
 * Narrower platform APIs (time, entropy, future socket/fs/sync helpers) live in
 * this directory too; this umbrella keeps host header ordering and platform
 * defines in one place while those narrower helpers continue to grow.
 */

#include <stddef.h>
#include <stdint.h>
#include <errno.h>
#include <limits.h>
#include <signal.h>
#include <time.h>

#if defined(_WIN32)
#  ifndef WIN32_LEAN_AND_MEAN
#    define WIN32_LEAN_AND_MEAN
#  endif
#  include <winsock2.h>
#  include <ws2tcpip.h>
#  include <windows.h>
#  include <conio.h>
#  include <direct.h>
#  include <io.h>
#  include <sys/stat.h>
#  include <wchar.h>
#else
#  include <arpa/inet.h>
#  include <fcntl.h>
#  include <netdb.h>
#  include <netinet/in.h>
#  include <poll.h>
#  include <pthread.h>
#  include <sys/ioctl.h>
#  include <sys/select.h>
#  include <sys/socket.h>
#  include <sys/stat.h>
#  include <sys/time.h>
#  include <sys/types.h>
#  include <termios.h>
#  include <unistd.h>
#  if defined(__APPLE__)
#    include <mach-o/dyld.h>
#  endif
#endif

#endif
