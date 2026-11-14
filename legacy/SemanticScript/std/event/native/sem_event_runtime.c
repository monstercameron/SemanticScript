#include "sem_event_runtime.h"

#include <stdint.h>
#include <stddef.h>
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#ifdef _WIN32
#include <windows.h>
#include <io.h>
#else
#include <fcntl.h>
#include <pthread.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <unistd.h>
#endif

#ifdef SS_EVENT_DEBUG
#define SS_EVENT_DEBUG_LOG(...) fprintf(stderr, __VA_ARGS__)
#else
#define SS_EVENT_DEBUG_LOG(...) ((void)0)
#endif

#define SS_EVENT_STREAM_MAGIC 0x53534553u
#define SS_EVENT_STREAM_HANDLE_MAGIC 0x53534844u
#define SS_EVENT_SUBSCRIPTION_MAGIC 0x53535542u
#define SS_EVENT_STORE_HEADER "SSEVENT1\n"
#define SS_EVENT_STORE_HEADER_SIZE 9U
#define SS_EVENT_STORE_MAX_FIELD_BYTES (16U * 1024U * 1024U)
#define SS_EVENT_STORE_EOF 1
#define SS_EVENT_STORE_RECORD_MAGIC 0x32525645u
#define SS_EVENT_STORE_COMMIT_MAGIC 0x4b4f5645u
#define SS_EVENT_STORE_CHECKSUM_OFFSET 2166136261u
#define SS_EVENT_STORE_CHECKSUM_PRIME 16777619u

typedef struct SSEventRecord {
    long long event_id;
    char *event_type;
    char *event_key;
    char *payload_json;
    struct SSEventRecord *next;
} SSEventRecord;

typedef struct SSEventSubscription SSEventSubscription;
typedef struct SSEventAsyncFuture SSEventAsyncFuture;
typedef struct SSEventStreamHandle SSEventStreamHandle;

typedef struct SSEventStream {
    unsigned int magic;
    char *stream_name;
    char *store_path;
    int queue_capacity;
    int retained_count;
    int durable;
    int strict_capacity;
    int open_handles;
    long long next_event_id;
    long long durable_loaded_through_event_id;
    int closed;
    SSEventRecord *head;
    SSEventRecord *tail;
    SSEventSubscription *subscriptions;
    struct SSEventStream *next_registry;
} SSEventStream;

struct SSEventStreamHandle {
    unsigned int magic;
    SSEventStream *stream;
    int closed;
};

struct SSEventSubscription {
    unsigned int magic;
    SSEventStream *stream;
    char *event_type_filter;
    char *event_key_filter;
    long long cursor_event_id;
    long long acknowledged_event_id;
    int queue_capacity;
    int closed;
    int dropped_matching_event_gap;
    SSEventAsyncFuture *pending_receives;
    SSEventAsyncFuture *pending_receives_tail;
    SSEventSubscription *next_subscription;
};

struct SSEventAsyncFuture {
    SSAsyncLoop *loop;
    int ready;
    int status;
    long long i64_result;
    int i32_result;
    void *ptr_result;
    void *cancel_token;
    SSAsyncTimer *timer;
    SSEventSubscription *pending_subscription;
    SSEventAsyncFuture *next_pending;
    char *out_event_type;
    int out_event_type_capacity;
    char *out_event_key;
    int out_event_key_capacity;
    char *out_payload_json;
    int out_payload_capacity;
};

typedef struct SSEventStoreLock {
    char *lock_path;
#ifdef _WIN32
    HANDLE handle;
#else
    int fd;
#endif
} SSEventStoreLock;

static SSEventStream *ss_event_stream_registry = NULL;

static void ss_event_free_record(SSEventRecord *record);
static int ss_event_filter_matches(const char *filter, const char *value);
static void ss_event_drop_oldest_if_needed(SSEventStream *stream);
void *ss_event_open_process_stream_await(SSAsyncLoop *loop, void *future_handle);

#ifdef _WIN32
static INIT_ONCE ss_event_mutex_once = INIT_ONCE_STATIC_INIT;
static CRITICAL_SECTION ss_event_mutex;

static BOOL CALLBACK ss_event_init_mutex_once(
    PINIT_ONCE init_once,
    PVOID parameter,
    PVOID *context
) {
    (void)init_once;
    (void)parameter;
    (void)context;
    InitializeCriticalSection(&ss_event_mutex);
    return TRUE;
}

static void ss_event_lock(void) {
    InitOnceExecuteOnce(&ss_event_mutex_once, ss_event_init_mutex_once, NULL, NULL);
    EnterCriticalSection(&ss_event_mutex);
}

static void ss_event_unlock(void) {
    LeaveCriticalSection(&ss_event_mutex);
}
#else
static pthread_mutex_t ss_event_mutex = PTHREAD_MUTEX_INITIALIZER;

static void ss_event_lock(void) {
    (void)pthread_mutex_lock(&ss_event_mutex);
}

static void ss_event_unlock(void) {
    (void)pthread_mutex_unlock(&ss_event_mutex);
}
#endif

static char *ss_event_duplicate_cstring(const char *text) {
    size_t length;
    char *copy;

    if (text == NULL) {
        text = "";
    }
    length = strlen(text);
    copy = (char *)malloc(length + 1U);
    if (copy == NULL) {
        return NULL;
    }
    memcpy(copy, text, length + 1U);
    return copy;
}

static int ss_event_safe_name_char(char ch) {
    return (ch >= 'A' && ch <= 'Z')
        || (ch >= 'a' && ch <= 'z')
        || (ch >= '0' && ch <= '9')
        || ch == '-' || ch == '_' || ch == '.';
}

static char *ss_event_store_path_for_name(const char *stream_name) {
    static const char hex_digits[] = "0123456789abcdef";
    const char *store_dir;
    const char *prefix;
    const char *suffix = ".sseventlog";
    const char *separator = "";
    size_t dir_length = 0;
    size_t name_length;
    size_t prefix_length;
    size_t suffix_length;
    size_t total_length;
    char *path;
    size_t index;
    size_t offset = 0;

    if (stream_name == NULL || stream_name[0] == '\0') {
        return NULL;
    }
    store_dir = getenv("SEM_EVENT_STORE_DIR");
    if (store_dir != NULL && store_dir[0] != '\0') {
        dir_length = strlen(store_dir);
        separator = (store_dir[dir_length - 1U] == '/' || store_dir[dir_length - 1U] == '\\') ? "" : "/";
        prefix = "sem_event_";
    } else {
        store_dir = "";
        prefix = ".sem_event_";
    }
    name_length = strlen(stream_name);
    prefix_length = strlen(prefix);
    suffix_length = strlen(suffix);
    total_length = dir_length + strlen(separator) + prefix_length + (name_length * 2U) + suffix_length;
    path = (char *)malloc(total_length + 1U);
    if (path == NULL) {
        return NULL;
    }
    if (dir_length > 0U) {
        memcpy(path + offset, store_dir, dir_length);
        offset += dir_length;
        if (separator[0] != '\0') {
            path[offset] = separator[0];
            offset += 1U;
        }
    }
    memcpy(path + offset, prefix, prefix_length);
    offset += prefix_length;
    for (index = 0; index < name_length; index += 1U) {
        unsigned char ch = (unsigned char)stream_name[index];
        path[offset + (index * 2U)] = hex_digits[(ch >> 4) & 0x0fU];
        path[offset + (index * 2U) + 1U] = hex_digits[ch & 0x0fU];
    }
    offset += name_length * 2U;
    memcpy(path + offset, suffix, suffix_length);
    offset += suffix_length;
    path[offset] = '\0';
    return path;
}

static SSEventRecord *ss_event_create_record(
    long long event_id,
    const char *event_type,
    const char *event_key,
    const char *payload_json
) {
    SSEventRecord *record = (SSEventRecord *)calloc(1, sizeof(*record));
    if (record == NULL) {
        return NULL;
    }
    record->event_type = ss_event_duplicate_cstring(event_type);
    record->event_key = ss_event_duplicate_cstring(event_key == NULL ? "" : event_key);
    record->payload_json = ss_event_duplicate_cstring(payload_json);
    if (record->event_type == NULL || record->event_key == NULL || record->payload_json == NULL) {
        ss_event_free_record(record);
        return NULL;
    }
    record->event_id = event_id;
    return record;
}

static void ss_event_free_record(SSEventRecord *record) {
    if (record == NULL) {
        return;
    }
    free(record->event_type);
    free(record->event_key);
    free(record->payload_json);
    free(record);
}

static void ss_event_encode_u32(unsigned char bytes[4], uint32_t value) {
    bytes[0] = (unsigned char)(value & 0xffU);
    bytes[1] = (unsigned char)((value >> 8) & 0xffU);
    bytes[2] = (unsigned char)((value >> 16) & 0xffU);
    bytes[3] = (unsigned char)((value >> 24) & 0xffU);
}

static uint32_t ss_event_decode_u32(const unsigned char bytes[4]) {
    return ((uint32_t)bytes[0])
        | (((uint32_t)bytes[1]) << 8)
        | (((uint32_t)bytes[2]) << 16)
        | (((uint32_t)bytes[3]) << 24);
}

static int ss_event_write_u32(FILE *file, uint32_t value) {
    unsigned char bytes[4];
    ss_event_encode_u32(bytes, value);
    return fwrite(bytes, 1U, sizeof(bytes), file) == sizeof(bytes) ? SS_EVENT_OK : SS_EVENT_ERR_ENGINE;
}

static int ss_event_write_i64(FILE *file, long long value) {
    uint64_t raw = (uint64_t)value;
    unsigned char bytes[8];
    int index;
    for (index = 0; index < 8; index += 1) {
        bytes[index] = (unsigned char)((raw >> (8U * (unsigned int)index)) & 0xffU);
    }
    return fwrite(bytes, 1U, sizeof(bytes), file) == sizeof(bytes) ? SS_EVENT_OK : SS_EVENT_ERR_ENGINE;
}

static int ss_event_read_exact(FILE *file, void *buffer, size_t byte_count) {
    size_t total_read = 0;

    while (total_read < byte_count) {
        size_t read_count = fread((unsigned char *)buffer + total_read, 1U, byte_count - total_read, file);
        if (read_count == 0U) {
            if (feof(file)) {
                return total_read == 0U ? SS_EVENT_STORE_EOF : SS_EVENT_ERR_ENGINE;
            }
            return SS_EVENT_ERR_ENGINE;
        }
        total_read += read_count;
    }
    return SS_EVENT_OK;
}

static int ss_event_read_u32(FILE *file, uint32_t *out_value) {
    unsigned char bytes[4];
    int status;

    status = ss_event_read_exact(file, bytes, sizeof(bytes));
    if (status != SS_EVENT_OK) {
        return status;
    }
    *out_value = ss_event_decode_u32(bytes);
    return SS_EVENT_OK;
}

static int ss_event_read_i64(FILE *file, long long *out_value) {
    unsigned char bytes[8];
    uint64_t raw = 0U;
    int index;
    int status;

    status = ss_event_read_exact(file, bytes, sizeof(bytes));
    if (status != SS_EVENT_OK) {
        return status;
    }
    for (index = 0; index < 8; index += 1) {
        raw |= ((uint64_t)bytes[index]) << (8U * (unsigned int)index);
    }
    *out_value = (long long)raw;
    return SS_EVENT_OK;
}

static uint32_t ss_event_checksum_update_bytes(
    uint32_t checksum,
    const void *bytes,
    size_t byte_count
) {
    const unsigned char *cursor = (const unsigned char *)bytes;
    size_t index;

    for (index = 0U; index < byte_count; index += 1U) {
        checksum ^= (uint32_t)cursor[index];
        checksum *= SS_EVENT_STORE_CHECKSUM_PRIME;
    }
    return checksum;
}

static uint32_t ss_event_checksum_update_u32(uint32_t checksum, uint32_t value) {
    unsigned char bytes[4];
    ss_event_encode_u32(bytes, value);
    return ss_event_checksum_update_bytes(checksum, bytes, sizeof(bytes));
}

static uint32_t ss_event_checksum_update_i64(uint32_t checksum, long long value) {
    uint64_t raw = (uint64_t)value;
    unsigned char bytes[8];
    int index;

    for (index = 0; index < 8; index += 1) {
        bytes[index] = (unsigned char)((raw >> (8U * (unsigned int)index)) & 0xffU);
    }
    return ss_event_checksum_update_bytes(checksum, bytes, sizeof(bytes));
}

static uint32_t ss_event_record_checksum(
    long long event_id,
    const char *event_type,
    uint32_t type_length,
    const char *event_key,
    uint32_t key_length,
    const char *payload_json,
    uint32_t payload_length
) {
    uint32_t checksum = SS_EVENT_STORE_CHECKSUM_OFFSET;

    checksum = ss_event_checksum_update_i64(checksum, event_id);
    checksum = ss_event_checksum_update_u32(checksum, type_length);
    checksum = ss_event_checksum_update_u32(checksum, key_length);
    checksum = ss_event_checksum_update_u32(checksum, payload_length);
    checksum = ss_event_checksum_update_bytes(checksum, event_type, type_length);
    checksum = ss_event_checksum_update_bytes(checksum, event_key, key_length);
    checksum = ss_event_checksum_update_bytes(checksum, payload_json, payload_length);
    return checksum;
}

static char *ss_event_store_lock_path_for_path(const char *path) {
    const char *suffix = ".lock";
    size_t path_length;
    size_t suffix_length;
    char *lock_path;

    if (path == NULL) {
        return NULL;
    }
    path_length = strlen(path);
    suffix_length = strlen(suffix);
    lock_path = (char *)malloc(path_length + suffix_length + 1U);
    if (lock_path == NULL) {
        return NULL;
    }
    memcpy(lock_path, path, path_length);
    memcpy(lock_path + path_length, suffix, suffix_length + 1U);
    return lock_path;
}

static int ss_event_store_lock_acquire(const char *path, SSEventStoreLock *lock) {
    if (path == NULL || lock == NULL) {
        return SS_EVENT_ERR_CONFIG;
    }
    memset(lock, 0, sizeof(*lock));
    lock->lock_path = ss_event_store_lock_path_for_path(path);
    if (lock->lock_path == NULL) {
        return SS_EVENT_ERR_ENGINE;
    }
#ifdef _WIN32
    lock->handle = CreateFileA(
        lock->lock_path,
        GENERIC_READ | GENERIC_WRITE,
        FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE,
        NULL,
        OPEN_ALWAYS,
        FILE_ATTRIBUTE_NORMAL,
        NULL
    );
    if (lock->handle == INVALID_HANDLE_VALUE) {
        free(lock->lock_path);
        lock->lock_path = NULL;
        return SS_EVENT_ERR_ENGINE;
    }
    {
        OVERLAPPED overlapped;
        memset(&overlapped, 0, sizeof(overlapped));
        if (!LockFileEx(lock->handle, LOCKFILE_EXCLUSIVE_LOCK, 0, 1, 0, &overlapped)) {
            CloseHandle(lock->handle);
            lock->handle = INVALID_HANDLE_VALUE;
            free(lock->lock_path);
            lock->lock_path = NULL;
            return SS_EVENT_ERR_ENGINE;
        }
    }
#else
    lock->fd = open(lock->lock_path, O_CREAT | O_RDWR, 0666);
    if (lock->fd < 0) {
        free(lock->lock_path);
        lock->lock_path = NULL;
        return SS_EVENT_ERR_ENGINE;
    }
    while (1) {
        struct flock lock_spec;
        memset(&lock_spec, 0, sizeof(lock_spec));
        lock_spec.l_type = F_WRLCK;
        lock_spec.l_whence = SEEK_SET;
        lock_spec.l_start = 0;
        lock_spec.l_len = 1;
        if (fcntl(lock->fd, F_SETLKW, &lock_spec) == 0) {
            break;
        }
        if (errno != EINTR) {
            close(lock->fd);
            lock->fd = -1;
            free(lock->lock_path);
            lock->lock_path = NULL;
            return SS_EVENT_ERR_ENGINE;
        }
    }
#endif
    return SS_EVENT_OK;
}

static void ss_event_store_lock_release(SSEventStoreLock *lock) {
    if (lock == NULL || lock->lock_path == NULL) {
        return;
    }
#ifdef _WIN32
    if (lock->handle != INVALID_HANDLE_VALUE) {
        OVERLAPPED overlapped;
        memset(&overlapped, 0, sizeof(overlapped));
        UnlockFileEx(lock->handle, 0, 1, 0, &overlapped);
        CloseHandle(lock->handle);
        lock->handle = INVALID_HANDLE_VALUE;
    }
#else
    if (lock->fd >= 0) {
        struct flock lock_spec;
        memset(&lock_spec, 0, sizeof(lock_spec));
        lock_spec.l_type = F_UNLCK;
        lock_spec.l_whence = SEEK_SET;
        lock_spec.l_start = 0;
        lock_spec.l_len = 1;
        (void)fcntl(lock->fd, F_SETLK, &lock_spec);
        close(lock->fd);
        lock->fd = -1;
    }
#endif
    free(lock->lock_path);
    lock->lock_path = NULL;
}

static int ss_event_store_sync_file(FILE *file) {
    if (file == NULL || fflush(file) != 0) {
        return SS_EVENT_ERR_ENGINE;
    }
#ifdef _WIN32
    if (_commit(_fileno(file)) != 0) {
        return SS_EVENT_ERR_ENGINE;
    }
#else
    if (fsync(fileno(file)) != 0) {
        return SS_EVENT_ERR_ENGINE;
    }
#endif
    return SS_EVENT_OK;
}

static int ss_event_store_truncate_file(FILE *file, long offset) {
    if (file == NULL || fflush(file) != 0) {
        return SS_EVENT_ERR_ENGINE;
    }
#ifdef _WIN32
    if (_chsize_s(_fileno(file), (__int64)offset) != 0) {
        return SS_EVENT_ERR_ENGINE;
    }
#else
    if (ftruncate(fileno(file), (off_t)offset) != 0) {
        return SS_EVENT_ERR_ENGINE;
    }
#endif
    if (fseek(file, offset, SEEK_SET) != 0) {
        return SS_EVENT_ERR_ENGINE;
    }
    return ss_event_store_sync_file(file);
}

static int ss_event_store_ensure_header(FILE *file, int recover_tail) {
    char header[SS_EVENT_STORE_HEADER_SIZE];
    long file_size;

    if (file == NULL) {
        return SS_EVENT_ERR_CONFIG;
    }
    if (fseek(file, 0L, SEEK_END) != 0) {
        return SS_EVENT_ERR_ENGINE;
    }
    file_size = ftell(file);
    if (file_size < 0L || fseek(file, 0L, SEEK_SET) != 0) {
        return SS_EVENT_ERR_ENGINE;
    }
    if (file_size == 0L) {
        return fwrite(SS_EVENT_STORE_HEADER, 1U, SS_EVENT_STORE_HEADER_SIZE, file) == SS_EVENT_STORE_HEADER_SIZE
            ? SS_EVENT_OK
            : SS_EVENT_ERR_ENGINE;
    }
    if (file_size < (long)SS_EVENT_STORE_HEADER_SIZE) {
        if (!recover_tail) {
            return SS_EVENT_ERR_ENGINE;
        }
        if (ss_event_store_truncate_file(file, 0L) != SS_EVENT_OK) {
            return SS_EVENT_ERR_ENGINE;
        }
        return fwrite(SS_EVENT_STORE_HEADER, 1U, SS_EVENT_STORE_HEADER_SIZE, file) == SS_EVENT_STORE_HEADER_SIZE
            ? ss_event_store_sync_file(file)
            : SS_EVENT_ERR_ENGINE;
    }
    if (fread(header, 1U, SS_EVENT_STORE_HEADER_SIZE, file) != SS_EVENT_STORE_HEADER_SIZE) {
        return SS_EVENT_ERR_ENGINE;
    }
    if (memcmp(header, SS_EVENT_STORE_HEADER, SS_EVENT_STORE_HEADER_SIZE) != 0) {
        return SS_EVENT_ERR_ENGINE;
    }
    return SS_EVENT_OK;
}

static char *ss_event_read_blob(FILE *file, uint32_t length) {
    char *text;
    if (length > SS_EVENT_STORE_MAX_FIELD_BYTES) {
        return NULL;
    }
    text = (char *)malloc((size_t)length + 1U);
    if (text == NULL) {
        return NULL;
    }
    if (length > 0U && fread(text, 1U, length, file) != length) {
        free(text);
        return NULL;
    }
    text[length] = '\0';
    return text;
}

static int ss_event_store_read_legacy_record(
    FILE *file,
    uint32_t low_event_id,
    SSEventRecord **out_record
) {
    uint32_t high_event_id;
    uint32_t type_length;
    uint32_t key_length;
    uint32_t payload_length;
    uint64_t raw_event_id;
    char *event_type = NULL;
    char *event_key = NULL;
    char *payload_json = NULL;
    SSEventRecord *record;
    int status;

    status = ss_event_read_u32(file, &high_event_id);
    if (status != SS_EVENT_OK) {
        return SS_EVENT_ERR_ENGINE;
    }
    status = ss_event_read_u32(file, &type_length);
    if (status == SS_EVENT_OK) {
        status = ss_event_read_u32(file, &key_length);
    }
    if (status == SS_EVENT_OK) {
        status = ss_event_read_u32(file, &payload_length);
    }
    if (status != SS_EVENT_OK
            || type_length > SS_EVENT_STORE_MAX_FIELD_BYTES
            || key_length > SS_EVENT_STORE_MAX_FIELD_BYTES
            || payload_length > SS_EVENT_STORE_MAX_FIELD_BYTES) {
        return SS_EVENT_ERR_ENGINE;
    }
    event_type = ss_event_read_blob(file, type_length);
    event_key = ss_event_read_blob(file, key_length);
    payload_json = ss_event_read_blob(file, payload_length);
    if (event_type == NULL || event_key == NULL || payload_json == NULL) {
        free(event_type);
        free(event_key);
        free(payload_json);
        return SS_EVENT_ERR_ENGINE;
    }
    raw_event_id = ((uint64_t)low_event_id) | (((uint64_t)high_event_id) << 32);
    record = ss_event_create_record((long long)raw_event_id, event_type, event_key, payload_json);
    free(event_type);
    free(event_key);
    free(payload_json);
    if (record == NULL) {
        return SS_EVENT_ERR_ENGINE;
    }
    *out_record = record;
    return SS_EVENT_OK;
}

static int ss_event_store_read_v2_record(FILE *file, SSEventRecord **out_record) {
    long long event_id;
    uint32_t type_length;
    uint32_t key_length;
    uint32_t payload_length;
    uint32_t stored_checksum;
    uint32_t computed_checksum;
    uint32_t commit_magic;
    char *event_type = NULL;
    char *event_key = NULL;
    char *payload_json = NULL;
    SSEventRecord *record;
    int status;

    status = ss_event_read_i64(file, &event_id);
    if (status == SS_EVENT_OK) {
        status = ss_event_read_u32(file, &type_length);
    }
    if (status == SS_EVENT_OK) {
        status = ss_event_read_u32(file, &key_length);
    }
    if (status == SS_EVENT_OK) {
        status = ss_event_read_u32(file, &payload_length);
    }
    if (status == SS_EVENT_OK) {
        status = ss_event_read_u32(file, &stored_checksum);
    }
    if (status != SS_EVENT_OK
            || type_length > SS_EVENT_STORE_MAX_FIELD_BYTES
            || key_length > SS_EVENT_STORE_MAX_FIELD_BYTES
            || payload_length > SS_EVENT_STORE_MAX_FIELD_BYTES) {
        return SS_EVENT_ERR_ENGINE;
    }
    event_type = ss_event_read_blob(file, type_length);
    event_key = ss_event_read_blob(file, key_length);
    payload_json = ss_event_read_blob(file, payload_length);
    if (event_type == NULL || event_key == NULL || payload_json == NULL) {
        free(event_type);
        free(event_key);
        free(payload_json);
        return SS_EVENT_ERR_ENGINE;
    }
    status = ss_event_read_u32(file, &commit_magic);
    if (status != SS_EVENT_OK || commit_magic != SS_EVENT_STORE_COMMIT_MAGIC) {
        free(event_type);
        free(event_key);
        free(payload_json);
        return SS_EVENT_ERR_ENGINE;
    }
    computed_checksum = ss_event_record_checksum(
        event_id,
        event_type,
        type_length,
        event_key,
        key_length,
        payload_json,
        payload_length
    );
    if (computed_checksum != stored_checksum) {
        free(event_type);
        free(event_key);
        free(payload_json);
        return SS_EVENT_ERR_ENGINE;
    }
    record = ss_event_create_record(event_id, event_type, event_key, payload_json);
    free(event_type);
    free(event_key);
    free(payload_json);
    if (record == NULL) {
        return SS_EVENT_ERR_ENGINE;
    }
    *out_record = record;
    return SS_EVENT_OK;
}

static int ss_event_store_read_next_record(FILE *file, SSEventRecord **out_record) {
    uint32_t first_word;
    int status;

    *out_record = NULL;
    status = ss_event_read_u32(file, &first_word);
    if (status != SS_EVENT_OK) {
        return status;
    }
    if (first_word == SS_EVENT_STORE_RECORD_MAGIC) {
        return ss_event_store_read_v2_record(file, out_record);
    }
    return ss_event_store_read_legacy_record(file, first_word, out_record);
}

typedef int (*SSEventStoreRecordVisitor)(SSEventRecord *record, void *context);

static int ss_event_store_scan_file_records(
    FILE *file,
    int recover_tail,
    SSEventStoreRecordVisitor visitor,
    void *context
) {
    long last_good_offset;
    int status = SS_EVENT_OK;

    if (file == NULL) {
        return SS_EVENT_ERR_CONFIG;
    }
    last_good_offset = ftell(file);
    if (last_good_offset < 0L) {
        return SS_EVENT_ERR_ENGINE;
    }
    while (status == SS_EVENT_OK) {
        SSEventRecord *record = NULL;
        status = ss_event_store_read_next_record(file, &record);
        if (status == SS_EVENT_STORE_EOF) {
            status = SS_EVENT_OK;
            break;
        }
        if (status != SS_EVENT_OK) {
            if (recover_tail) {
                status = ss_event_store_truncate_file(file, last_good_offset);
            }
            break;
        }
        last_good_offset = ftell(file);
        if (last_good_offset < 0L) {
            ss_event_free_record(record);
            status = SS_EVENT_ERR_ENGINE;
            break;
        }
        if (visitor != NULL) {
            status = visitor(record, context);
        } else {
            ss_event_free_record(record);
        }
    }
    return status;
}

static int ss_event_store_write_record_v2(FILE *file, const SSEventRecord *record) {
    size_t type_length;
    size_t key_length;
    size_t payload_length;
    uint32_t checksum;
    int status;

    if (file == NULL || record == NULL) {
        return SS_EVENT_ERR_CONFIG;
    }
    type_length = strlen(record->event_type);
    key_length = strlen(record->event_key);
    payload_length = strlen(record->payload_json);
    if (type_length > SS_EVENT_STORE_MAX_FIELD_BYTES
            || key_length > SS_EVENT_STORE_MAX_FIELD_BYTES
            || payload_length > SS_EVENT_STORE_MAX_FIELD_BYTES) {
        return SS_EVENT_ERR_CONFIG;
    }
    checksum = ss_event_record_checksum(
        record->event_id,
        record->event_type,
        (uint32_t)type_length,
        record->event_key,
        (uint32_t)key_length,
        record->payload_json,
        (uint32_t)payload_length
    );
    status = ss_event_write_u32(file, SS_EVENT_STORE_RECORD_MAGIC);
    if (status == SS_EVENT_OK) {
        status = ss_event_write_i64(file, record->event_id);
    }
    if (status == SS_EVENT_OK) {
        status = ss_event_write_u32(file, (uint32_t)type_length);
    }
    if (status == SS_EVENT_OK) {
        status = ss_event_write_u32(file, (uint32_t)key_length);
    }
    if (status == SS_EVENT_OK) {
        status = ss_event_write_u32(file, (uint32_t)payload_length);
    }
    if (status == SS_EVENT_OK) {
        status = ss_event_write_u32(file, checksum);
    }
    if (status == SS_EVENT_OK && fwrite(record->event_type, 1U, type_length, file) != type_length) {
        status = SS_EVENT_ERR_ENGINE;
    }
    if (status == SS_EVENT_OK && fwrite(record->event_key, 1U, key_length, file) != key_length) {
        status = SS_EVENT_ERR_ENGINE;
    }
    if (status == SS_EVENT_OK && fwrite(record->payload_json, 1U, payload_length, file) != payload_length) {
        status = SS_EVENT_ERR_ENGINE;
    }
    if (status == SS_EVENT_OK) {
        status = ss_event_write_u32(file, SS_EVENT_STORE_COMMIT_MAGIC);
    }
    return status;
}

static int ss_event_copy_output(char *out_buffer, int out_capacity, const char *text) {
    size_t length;

    if (out_capacity == 0) {
        return SS_EVENT_OK;
    }
    if (out_buffer == NULL || out_capacity <= 0 || text == NULL) {
        return SS_EVENT_ERR_CONFIG;
    }
    length = strlen(text);
    if (length + 1U > (size_t)out_capacity) {
        return SS_EVENT_ERR_OUTPUT_TOO_SMALL;
    }
    memcpy(out_buffer, text, length + 1U);
    return SS_EVENT_OK;
}

static int ss_event_filter_matches(const char *filter, const char *value) {
    if (filter == NULL || filter[0] == '\0') {
        return 1;
    }
    if (value == NULL) {
        return 0;
    }
    return strcmp(filter, value) == 0;
}

static void ss_event_append_record_to_stream_locked(SSEventStream *stream, SSEventRecord *record) {
    if (stream->tail != NULL) {
        stream->tail->next = record;
    } else {
        stream->head = record;
    }
    stream->tail = record;
    stream->retained_count += 1;
    if (record->event_id >= stream->next_event_id) {
        stream->next_event_id = record->event_id + 1;
    }
}

typedef struct SSEventStoreLoadContext {
    SSEventStream *stream;
    long long after_event_id;
} SSEventStoreLoadContext;

static int ss_event_store_load_record_visitor(SSEventRecord *record, void *context) {
    SSEventStoreLoadContext *load_context = (SSEventStoreLoadContext *)context;
    SSEventStream *stream;

    if (record == NULL || load_context == NULL || load_context->stream == NULL) {
        ss_event_free_record(record);
        return SS_EVENT_ERR_CONFIG;
    }
    stream = load_context->stream;
    if (record->event_id > stream->durable_loaded_through_event_id) {
        stream->durable_loaded_through_event_id = record->event_id;
    }
    if (record->event_id >= stream->next_event_id) {
        stream->next_event_id = record->event_id + 1;
    }
    if (record->event_id > load_context->after_event_id) {
        ss_event_append_record_to_stream_locked(stream, record);
        ss_event_drop_oldest_if_needed(stream);
    } else {
        ss_event_free_record(record);
    }
    return SS_EVENT_OK;
}

static int ss_event_store_scan_path(
    const char *path,
    int create_if_missing,
    int recover_tail,
    SSEventStoreRecordVisitor visitor,
    void *context
) {
    SSEventStoreLock store_lock;
    FILE *file;
    int status;

    status = ss_event_store_lock_acquire(path, &store_lock);
    if (status != SS_EVENT_OK) {
        return status;
    }
    file = fopen(path, "r+b");
    if (file == NULL && create_if_missing) {
        file = fopen(path, "w+b");
    }
    if (file == NULL) {
        ss_event_store_lock_release(&store_lock);
        return create_if_missing ? SS_EVENT_ERR_ENGINE : SS_EVENT_OK;
    }
    status = ss_event_store_ensure_header(file, recover_tail);
    if (status == SS_EVENT_OK) {
        status = ss_event_store_scan_file_records(file, recover_tail, visitor, context);
    }
    if (fclose(file) != 0 && status == SS_EVENT_OK) {
        status = SS_EVENT_ERR_ENGINE;
    }
    ss_event_store_lock_release(&store_lock);
    return status;
}

static int ss_event_store_load_records_after(SSEventStream *stream, long long after_event_id) {
    SSEventStoreLoadContext context;

    if (stream == NULL || stream->store_path == NULL) {
        return SS_EVENT_ERR_CONFIG;
    }
    context.stream = stream;
    context.after_event_id = after_event_id;
    return ss_event_store_scan_path(
        stream->store_path,
        0,
        1,
        ss_event_store_load_record_visitor,
        &context
    );
}

static int ss_event_store_load_records(SSEventStream *stream) {
    return ss_event_store_load_records_after(stream, 0);
}

typedef struct SSEventStoreNextIdContext {
    long long next_event_id;
} SSEventStoreNextIdContext;

static int ss_event_store_next_id_visitor(SSEventRecord *record, void *context) {
    SSEventStoreNextIdContext *next_context = (SSEventStoreNextIdContext *)context;

    if (record != NULL && next_context != NULL && record->event_id >= next_context->next_event_id) {
        next_context->next_event_id = record->event_id + 1;
    }
    ss_event_free_record(record);
    return SS_EVENT_OK;
}

static int ss_event_store_append_new_record(
    const char *path,
    const char *event_type,
    const char *event_key,
    const char *payload_json,
    long long *out_event_id
) {
    SSEventStoreLock store_lock;
    SSEventStoreNextIdContext next_context;
    SSEventRecord *record = NULL;
    FILE *file;
    int status;

    if (path == NULL || event_type == NULL || event_type[0] == '\0' || payload_json == NULL || out_event_id == NULL) {
        return SS_EVENT_ERR_CONFIG;
    }
    *out_event_id = 0;
    status = ss_event_store_lock_acquire(path, &store_lock);
    if (status != SS_EVENT_OK) {
        return status;
    }
    file = fopen(path, "r+b");
    if (file == NULL) {
        file = fopen(path, "w+b");
    }
    if (file == NULL) {
        ss_event_store_lock_release(&store_lock);
        return SS_EVENT_ERR_ENGINE;
    }
    status = ss_event_store_ensure_header(file, 1);
    next_context.next_event_id = 1;
    if (status == SS_EVENT_OK) {
        status = ss_event_store_scan_file_records(file, 1, ss_event_store_next_id_visitor, &next_context);
    }
    if (status == SS_EVENT_OK && fseek(file, 0L, SEEK_END) != 0) {
        status = SS_EVENT_ERR_ENGINE;
    }
    if (status == SS_EVENT_OK) {
        record = ss_event_create_record(next_context.next_event_id, event_type, event_key, payload_json);
        if (record == NULL) {
            status = SS_EVENT_ERR_ENGINE;
        }
    }
    if (status == SS_EVENT_OK) {
        status = ss_event_store_write_record_v2(file, record);
    }
    if (status == SS_EVENT_OK) {
        status = ss_event_store_sync_file(file);
    }
    if (status == SS_EVENT_OK) {
        *out_event_id = record->event_id;
    }
    ss_event_free_record(record);
    if (fclose(file) != 0 && status == SS_EVENT_OK) {
        status = SS_EVENT_ERR_ENGINE;
    }
    ss_event_store_lock_release(&store_lock);
    return status;
}

typedef struct SSEventStoreMatchContext {
    long long after_event_id;
    long long before_event_id;
    const char *event_type_filter;
    const char *event_key_filter;
    int found;
} SSEventStoreMatchContext;

static int ss_event_store_match_visitor(SSEventRecord *record, void *context) {
    SSEventStoreMatchContext *match_context = (SSEventStoreMatchContext *)context;

    if (record != NULL && match_context != NULL
            && record->event_id > match_context->after_event_id
            && record->event_id < match_context->before_event_id
            && ss_event_filter_matches(match_context->event_type_filter, record->event_type)
            && ss_event_filter_matches(match_context->event_key_filter, record->event_key)) {
        match_context->found = 1;
    }
    ss_event_free_record(record);
    return SS_EVENT_OK;
}

static int ss_event_store_has_matching_record_before(
    const char *path,
    long long after_event_id,
    long long before_event_id,
    const char *event_type_filter,
    const char *event_key_filter,
    int *out_found
) {
    SSEventStoreMatchContext context;
    int status;

    if (path == NULL || out_found == NULL) {
        return SS_EVENT_ERR_CONFIG;
    }
    *out_found = 0;
    context.after_event_id = after_event_id;
    context.before_event_id = before_event_id;
    context.event_type_filter = event_type_filter;
    context.event_key_filter = event_key_filter;
    context.found = 0;
    status = ss_event_store_scan_path(path, 0, 1, ss_event_store_match_visitor, &context);
    if (status != SS_EVENT_OK) {
        return status;
    }
    *out_found = context.found;
    return SS_EVENT_OK;
}

static SSEventAsyncFuture *ss_event_future_create(SSAsyncLoop *loop) {
    SSEventAsyncFuture *future;

    if (loop == NULL) {
        return NULL;
    }
    future = (SSEventAsyncFuture *)calloc(1, sizeof(*future));
    if (future == NULL) {
        return NULL;
    }
    future->loop = loop;
    future->status = SS_EVENT_OK;
    return future;
}

static void ss_event_unlink_pending_receive(SSEventAsyncFuture *future) {
    SSEventSubscription *subscription;
    SSEventAsyncFuture **cursor;
    SSEventAsyncFuture *previous = NULL;

    if (future == NULL || future->pending_subscription == NULL) {
        return;
    }
    subscription = future->pending_subscription;
    cursor = &subscription->pending_receives;
    while (*cursor != NULL) {
        if (*cursor == future) {
            *cursor = future->next_pending;
            if (subscription->pending_receives_tail == future) {
                subscription->pending_receives_tail = previous;
            }
            break;
        }
        previous = *cursor;
        cursor = &(*cursor)->next_pending;
    }
    future->pending_subscription = NULL;
    future->next_pending = NULL;
}

static void ss_event_future_complete_cancelled(SSEventAsyncFuture *future) {
    if (future == NULL || future->ready) {
        return;
    }
    ss_event_unlink_pending_receive(future);
    future->i64_result = SS_EVENT_ERR_CANCELLED;
    future->i32_result = SS_EVENT_ERR_CANCELLED;
    future->ptr_result = NULL;
    future->status = SS_EVENT_ERR_CANCELLED;
    future->ready = 1;
}

static int ss_event_future_cancel_requested(SSEventAsyncFuture *future) {
    return future != NULL && ss_async_cancel_token_is_cancelled(future->cancel_token);
}

static void ss_event_future_set_cancel_token(SSEventAsyncFuture *future, void *cancel_token) {
    if (future == NULL || cancel_token == NULL) {
        return;
    }
    if (ss_async_cancel_token_retain(cancel_token)) {
        future->cancel_token = cancel_token;
    }
}

static void ss_event_future_cancel_if_requested_locked(SSEventAsyncFuture *future) {
    if (ss_event_future_cancel_requested(future)) {
        ss_event_future_complete_cancelled(future);
    }
}

static void ss_event_future_complete_i64(SSEventAsyncFuture *future, long long result) {
    if (future == NULL || future->ready) {
        return;
    }
    ss_event_unlink_pending_receive(future);
    future->i64_result = result;
    future->status = result < 0 ? (int)result : SS_EVENT_OK;
    future->ready = 1;
}

static void ss_event_future_complete_i32(SSEventAsyncFuture *future, int result) {
    if (future == NULL || future->ready) {
        return;
    }
    ss_event_unlink_pending_receive(future);
    future->i32_result = result;
    future->status = result < 0 ? result : SS_EVENT_OK;
    future->ready = 1;
}

static void ss_event_future_complete_ptr(SSEventAsyncFuture *future, void *result) {
    if (future == NULL || future->ready) {
        return;
    }
    ss_event_unlink_pending_receive(future);
    future->ptr_result = result;
    future->status = result == NULL ? SS_EVENT_ERR_CONFIG : SS_EVENT_OK;
    future->ready = 1;
}

static void ss_event_receive_timeout(void *user_data) {
    SSEventAsyncFuture *future = (SSEventAsyncFuture *)user_data;
    ss_event_lock();
    ss_event_future_complete_i64(future, SS_EVENT_ERR_TIMED_OUT);
    ss_event_unlock();
}

static int ss_event_start_timer_if_needed(
    SSEventAsyncFuture *future,
    unsigned long long timeout_ms
) {
    int status;

    if (future == NULL || timeout_ms == 0) {
        return SS_EVENT_OK;
    }
    status = ss_async_timer_start(
        future->loop,
        timeout_ms,
        ss_event_receive_timeout,
        future,
        &future->timer
    );
    if (status == SS_ASYNC_OK) {
        return SS_EVENT_OK;
    }
    if (status == SS_ASYNC_ERR_RUNTIME_UNAVAILABLE) {
        return SS_EVENT_ERR_RUNTIME_UNAVAILABLE;
    }
    return SS_EVENT_ERR_ENGINE;
}

static int ss_event_wait_until_ready(SSAsyncLoop *loop, SSEventAsyncFuture *future) {
    if (loop == NULL || future == NULL) {
        return SS_EVENT_ERR_CONFIG;
    }
    while (1) {
        ss_event_lock();
        ss_event_future_cancel_if_requested_locked(future);
        if (future->ready) {
            ss_event_unlock();
            return SS_EVENT_OK;
        }
        ss_event_unlock();
        int status = ss_async_loop_run_once(loop);
        if (status == SS_ASYNC_ERR_RUNTIME_UNAVAILABLE) {
            return SS_EVENT_ERR_RUNTIME_UNAVAILABLE;
        }
        if (status != SS_ASYNC_OK) {
            return SS_EVENT_ERR_ENGINE;
        }
    }
}

static void ss_event_future_destroy(SSEventAsyncFuture *future) {
    if (future == NULL) {
        return;
    }
    ss_event_lock();
    ss_event_unlink_pending_receive(future);
    ss_event_unlock();
    if (future->cancel_token != NULL) {
        ss_async_cancel_token_release(future->cancel_token);
        future->cancel_token = NULL;
    }
    if (future->timer != NULL) {
        ss_async_timer_cancel(future->timer);
        ss_async_timer_destroy(future->timer);
        future->timer = NULL;
    }
    free(future);
}

static long long ss_event_receive_next(
    SSEventSubscription *subscription,
    char *out_event_type,
    int out_event_type_capacity,
    char *out_event_key,
    int out_event_key_capacity,
    char *out_payload_json,
    int out_payload_capacity
) {
    SSEventStream *stream;
    SSEventRecord *record;
    SSEventRecord *first_pending_match = NULL;
    int pending_match_count = 0;
    int copy_status;
    int store_status;

    if (subscription == NULL || subscription->magic != SS_EVENT_SUBSCRIPTION_MAGIC) {
        return SS_EVENT_ERR_CONFIG;
    }
    stream = subscription->stream;
    if (subscription->closed || stream == NULL || stream->magic != SS_EVENT_STREAM_MAGIC) {
        return SS_EVENT_ERR_SUBSCRIPTION_CLOSED;
    }
    if (stream->closed) {
        return SS_EVENT_ERR_SUBSCRIPTION_CLOSED;
    }
    if (stream->durable) {
        store_status = ss_event_store_load_records_after(
            stream,
            stream->durable_loaded_through_event_id
        );
        if (store_status != SS_EVENT_OK) {
            return store_status;
        }
    }
    if (subscription->dropped_matching_event_gap) {
        return SS_EVENT_ERR_QUEUE_FULL;
    }
    record = stream->head;
    if (record != NULL &&
            subscription->event_type_filter[0] == '\0' &&
            subscription->event_key_filter[0] == '\0' &&
            subscription->cursor_event_id + 1 < record->event_id) {
        return SS_EVENT_ERR_QUEUE_FULL;
    }
    while (record != NULL) {
        if (record->event_id > subscription->cursor_event_id &&
                ss_event_filter_matches(subscription->event_type_filter, record->event_type) &&
                ss_event_filter_matches(subscription->event_key_filter, record->event_key)) {
            pending_match_count += 1;
            if (first_pending_match == NULL) {
                first_pending_match = record;
            }
            if (subscription->queue_capacity > 0 && pending_match_count > subscription->queue_capacity) {
                return SS_EVENT_ERR_QUEUE_FULL;
            }
        }
        record = record->next;
    }
    if (first_pending_match == NULL) {
        return SS_EVENT_NO_EVENT;
    }
    copy_status = ss_event_copy_output(out_event_type, out_event_type_capacity, first_pending_match->event_type);
    if (copy_status != SS_EVENT_OK) {
        return copy_status;
    }
    copy_status = ss_event_copy_output(out_event_key, out_event_key_capacity, first_pending_match->event_key);
    if (copy_status != SS_EVENT_OK) {
        return copy_status;
    }
    copy_status = ss_event_copy_output(out_payload_json, out_payload_capacity, first_pending_match->payload_json);
    if (copy_status != SS_EVENT_OK) {
        return copy_status;
    }
    subscription->cursor_event_id = first_pending_match->event_id;
    return first_pending_match->event_id;
}

static int ss_event_try_complete_receive(SSEventAsyncFuture *future) {
    long long event_id;

    if (future == NULL || future->ready || future->pending_subscription == NULL) {
        return 0;
    }
    ss_event_future_cancel_if_requested_locked(future);
    if (future->ready) {
        return 1;
    }
    event_id = ss_event_receive_next(
        future->pending_subscription,
        future->out_event_type,
        future->out_event_type_capacity,
        future->out_event_key,
        future->out_event_key_capacity,
        future->out_payload_json,
        future->out_payload_capacity
    );
    if (event_id == SS_EVENT_NO_EVENT) {
        SS_EVENT_DEBUG_LOG("event.receive still pending subscription=%p\n", future->pending_subscription);
        return 0;
    }
    SS_EVENT_DEBUG_LOG("event.receive complete subscription=%p result=%lld\n", future->pending_subscription, event_id);
    ss_event_future_complete_i64(future, event_id);
    return 1;
}

static void ss_event_complete_pending_receives(SSEventStream *stream) {
    SSEventSubscription *subscription;

    if (stream == NULL) {
        return;
    }
    subscription = stream->subscriptions;
    while (subscription != NULL) {
        SS_EVENT_DEBUG_LOG("event.complete scan subscription=%p pending=%p\n", subscription, subscription->pending_receives);
        SSEventAsyncFuture *future = subscription->pending_receives;
        while (future != NULL) {
            SSEventAsyncFuture *next_future = future->next_pending;
            ss_event_try_complete_receive(future);
            future = next_future;
        }
        subscription = subscription->next_subscription;
    }
}

static void ss_event_complete_subscription_pending(
    SSEventSubscription *subscription,
    long long result
) {
    SSEventAsyncFuture *future;
    SSEventAsyncFuture *next_future;

    if (subscription == NULL) {
        return;
    }
    future = subscription->pending_receives;
    subscription->pending_receives = NULL;
    subscription->pending_receives_tail = NULL;
    while (future != NULL) {
        next_future = future->next_pending;
        future->pending_subscription = NULL;
        future->next_pending = NULL;
        ss_event_future_complete_i64(future, result);
        future = next_future;
    }
}

static void ss_event_drop_oldest_if_needed(SSEventStream *stream) {
    SSEventRecord *oldest;
    SSEventSubscription *subscription;

    if (stream == NULL || stream->strict_capacity) {
        return;
    }
    while (stream->retained_count > stream->queue_capacity && stream->head != NULL) {
        oldest = stream->head;
        subscription = stream->subscriptions;
        while (subscription != NULL) {
            if (!subscription->closed && subscription->cursor_event_id < oldest->event_id &&
                    ss_event_filter_matches(subscription->event_type_filter, oldest->event_type) &&
                    ss_event_filter_matches(subscription->event_key_filter, oldest->event_key)) {
                subscription->dropped_matching_event_gap = 1;
            }
            subscription = subscription->next_subscription;
        }
        stream->head = oldest->next;
        if (stream->tail == oldest) {
            stream->tail = NULL;
        }
        oldest->next = NULL;
        ss_event_free_record(oldest);
        stream->retained_count -= 1;
    }
}

static void ss_event_prune_acknowledged_queue_records_locked(SSEventStream *stream) {
    SSEventSubscription *subscription;
    SSEventRecord *oldest;
    long long prune_through;

    if (stream == NULL || !stream->strict_capacity || stream->head == NULL) {
        return;
    }
    subscription = stream->subscriptions;
    if (subscription == NULL) {
        return;
    }
    prune_through = subscription->acknowledged_event_id;
    subscription = subscription->next_subscription;
    while (subscription != NULL) {
        if (!subscription->closed && subscription->acknowledged_event_id < prune_through) {
            prune_through = subscription->acknowledged_event_id;
        }
        subscription = subscription->next_subscription;
    }
    while (stream->head != NULL && stream->head->event_id <= prune_through) {
        oldest = stream->head;
        stream->head = oldest->next;
        if (stream->tail == oldest) {
            stream->tail = NULL;
        }
        oldest->next = NULL;
        ss_event_free_record(oldest);
        stream->retained_count -= 1;
    }
}

static SSEventStream *ss_event_find_open_stream_locked(
    const char *stream_name,
    int durable,
    int strict_capacity
) {
    SSEventStream *stream = ss_event_stream_registry;
    while (stream != NULL) {
        if (stream->magic == SS_EVENT_STREAM_MAGIC
                && !stream->closed
                && stream->durable == durable
                && stream->strict_capacity == strict_capacity
                && strcmp(stream->stream_name, stream_name) == 0) {
            return stream;
        }
        stream = stream->next_registry;
    }
    return NULL;
}

static void ss_event_register_stream_locked(SSEventStream *stream) {
    stream->next_registry = ss_event_stream_registry;
    ss_event_stream_registry = stream;
}

static void ss_event_unregister_stream_locked(SSEventStream *stream) {
    SSEventStream **cursor = &ss_event_stream_registry;
    while (*cursor != NULL) {
        if (*cursor == stream) {
            *cursor = stream->next_registry;
            stream->next_registry = NULL;
            return;
        }
        cursor = &(*cursor)->next_registry;
    }
}

static SSEventStreamHandle *ss_event_create_stream_handle_locked(SSEventStream *stream) {
    SSEventStreamHandle *handle;

    if (stream == NULL || stream->magic != SS_EVENT_STREAM_MAGIC || stream->closed) {
        return NULL;
    }
    handle = (SSEventStreamHandle *)calloc(1, sizeof(*handle));
    if (handle == NULL) {
        return NULL;
    }
    handle->magic = SS_EVENT_STREAM_HANDLE_MAGIC;
    handle->stream = stream;
    stream->open_handles += 1;
    return handle;
}

static SSEventStream *ss_event_stream_from_handle_locked(void *stream_handle) {
    SSEventStreamHandle *handle = (SSEventStreamHandle *)stream_handle;
    if (handle == NULL || handle->magic != SS_EVENT_STREAM_HANDLE_MAGIC || handle->closed) {
        return NULL;
    }
    if (handle->stream == NULL || handle->stream->magic != SS_EVENT_STREAM_MAGIC || handle->stream->closed) {
        return NULL;
    }
    return handle->stream;
}

static void *ss_event_open_stream_locked(
    const char *stream_name,
    int queue_capacity,
    int durable,
    int strict_capacity
) {
    SSEventStream *stream;
    int load_status;

    if (stream_name == NULL || stream_name[0] == '\0' || queue_capacity <= 0) {
        return NULL;
    }
    stream = ss_event_find_open_stream_locked(stream_name, durable, strict_capacity);
    if (stream != NULL) {
        if (queue_capacity > stream->queue_capacity) {
            stream->queue_capacity = queue_capacity;
        }
        if (stream->durable) {
            load_status = ss_event_store_load_records_after(
                stream,
                stream->durable_loaded_through_event_id
            );
            if (load_status != SS_EVENT_OK) {
                return NULL;
            }
        }
        return ss_event_create_stream_handle_locked(stream);
    }
    stream = (SSEventStream *)calloc(1, sizeof(*stream));
    if (stream == NULL) {
        return NULL;
    }
    stream->stream_name = ss_event_duplicate_cstring(stream_name);
    if (stream->stream_name == NULL) {
        free(stream);
        return NULL;
    }
    if (durable) {
        stream->store_path = ss_event_store_path_for_name(stream_name);
        if (stream->store_path == NULL) {
            free(stream->stream_name);
            free(stream);
            return NULL;
        }
    }
    stream->magic = SS_EVENT_STREAM_MAGIC;
    stream->queue_capacity = queue_capacity;
    stream->durable = durable;
    stream->strict_capacity = strict_capacity;
    stream->open_handles = 0;
    stream->next_event_id = 1;
    if (durable) {
        load_status = ss_event_store_load_records(stream);
        if (load_status != SS_EVENT_OK) {
            SSEventRecord *record = stream->head;
            while (record != NULL) {
                SSEventRecord *next_record = record->next;
                ss_event_free_record(record);
                record = next_record;
            }
            free(stream->store_path);
            free(stream->stream_name);
            free(stream);
            return NULL;
        }
    }
    ss_event_register_stream_locked(stream);
    return ss_event_create_stream_handle_locked(stream);
}

void *ss_event_open_process_stream(const char *stream_name, int queue_capacity) {
    void *stream;
    ss_event_lock();
    stream = ss_event_open_stream_locked(stream_name, queue_capacity, 0, 0);
    ss_event_unlock();
    return stream;
}

void *ss_event_open_process_queue(const char *stream_name, int queue_capacity) {
    void *stream;
    ss_event_lock();
    stream = ss_event_open_stream_locked(stream_name, queue_capacity, 0, 1);
    ss_event_unlock();
    return stream;
}

void *ss_event_open_durable_stream(const char *stream_name, int queue_capacity) {
    void *stream;
    ss_event_lock();
    stream = ss_event_open_stream_locked(stream_name, queue_capacity, 1, 0);
    ss_event_unlock();
    return stream;
}

int ss_event_close_stream(void *stream_handle) {
    SSEventStreamHandle *handle = (SSEventStreamHandle *)stream_handle;
    SSEventStream *stream;
    SSEventRecord *record;
    SSEventRecord *next_record;
    SSEventSubscription *subscription;
    int result = SS_EVENT_OK;

    ss_event_lock();
    if (handle == NULL || handle->magic != SS_EVENT_STREAM_HANDLE_MAGIC || handle->closed) {
        ss_event_unlock();
        return SS_EVENT_ERR_CONFIG;
    }
    stream = handle->stream;
    handle->closed = 1;
    handle->magic = 0;
    handle->stream = NULL;
    if (stream == NULL || stream->magic != SS_EVENT_STREAM_MAGIC || stream->closed) {
        ss_event_unlock();
        return SS_EVENT_ERR_CONFIG;
    }
    if (stream->open_handles > 0) {
        stream->open_handles -= 1;
    }
    if (stream->open_handles > 0) {
        ss_event_unlock();
        return SS_EVENT_OK;
    }
    ss_event_unregister_stream_locked(stream);
    stream->closed = 1;
    subscription = stream->subscriptions;
    while (subscription != NULL) {
        ss_event_complete_subscription_pending(subscription, SS_EVENT_ERR_SUBSCRIPTION_CLOSED);
        subscription->closed = 1;
        subscription->stream = NULL;
        subscription = subscription->next_subscription;
    }
    stream->subscriptions = NULL;
    record = stream->head;
    stream->head = NULL;
    stream->tail = NULL;
    stream->retained_count = 0;
    stream->magic = 0;

    while (record != NULL) {
        next_record = record->next;
        ss_event_free_record(record);
        record = next_record;
    }
    free(stream->stream_name);
    stream->stream_name = NULL;
    free(stream->store_path);
    stream->store_path = NULL;
    /*
     * Keep a tombstone allocation so already-started async operations fail
     * cleanly instead of racing a freed stream pointer. Reference-counted
     * handle reclamation belongs in the future loop-owned runtime.
     */
    ss_event_unlock();
    return result;
}

long long ss_event_append(
    void *stream_handle,
    const char *event_type,
    const char *event_key,
    const char *payload_json
) {
    SSEventStream *stream;
    SSEventRecord *record = NULL;
    long long assigned_event_id = 0;
    int store_status;

    ss_event_lock();
    stream = ss_event_stream_from_handle_locked(stream_handle);
    if (stream == NULL || stream->magic != SS_EVENT_STREAM_MAGIC || event_type == NULL || event_type[0] == '\0' || payload_json == NULL) {
        ss_event_unlock();
        return SS_EVENT_ERR_CONFIG;
    }
    if (stream->closed) {
        ss_event_unlock();
        return SS_EVENT_ERR_CONFIG;
    }
    if (stream->strict_capacity && stream->retained_count >= stream->queue_capacity) {
        ss_event_unlock();
        return SS_EVENT_ERR_QUEUE_FULL;
    }
    if (stream->durable) {
        store_status = ss_event_store_append_new_record(
            stream->store_path,
            event_type,
            event_key,
            payload_json,
            &assigned_event_id
        );
        if (store_status != SS_EVENT_OK) {
            ss_event_unlock();
            return store_status;
        }
        store_status = ss_event_store_load_records_after(
            stream,
            stream->durable_loaded_through_event_id
        );
        if (store_status != SS_EVENT_OK) {
            ss_event_unlock();
            return store_status;
        }
        ss_event_complete_pending_receives(stream);
        ss_event_unlock();
        return assigned_event_id;
    }
    record = ss_event_create_record(stream->next_event_id, event_type, event_key, payload_json);
    if (record == NULL) {
        ss_event_unlock();
        return SS_EVENT_ERR_ENGINE;
    }
    stream->next_event_id += 1;
    assigned_event_id = record->event_id;
    ss_event_append_record_to_stream_locked(stream, record);
    ss_event_drop_oldest_if_needed(stream);
    ss_event_complete_pending_receives(stream);
    ss_event_unlock();
    return assigned_event_id;
}

void *ss_event_subscribe(
    void *stream_handle,
    const char *event_type,
    const char *event_key,
    long long after_event_id,
    int queue_capacity
) {
    SSEventStream *stream;
    SSEventSubscription *subscription;
    int store_status;
    int has_dropped_match;

    ss_event_lock();
    stream = ss_event_stream_from_handle_locked(stream_handle);
    if (stream == NULL || stream->magic != SS_EVENT_STREAM_MAGIC || after_event_id < 0 || queue_capacity <= 0) {
        ss_event_unlock();
        return NULL;
    }
    if (stream->durable) {
        store_status = ss_event_store_load_records_after(
            stream,
            stream->durable_loaded_through_event_id
        );
        if (store_status != SS_EVENT_OK) {
            ss_event_unlock();
            return NULL;
        }
    }
    subscription = (SSEventSubscription *)calloc(1, sizeof(*subscription));
    if (subscription == NULL) {
        ss_event_unlock();
        return NULL;
    }
    subscription->event_type_filter = ss_event_duplicate_cstring(event_type == NULL ? "" : event_type);
    subscription->event_key_filter = ss_event_duplicate_cstring(event_key == NULL ? "" : event_key);
    if (subscription->event_type_filter == NULL || subscription->event_key_filter == NULL) {
        free(subscription->event_type_filter);
        free(subscription->event_key_filter);
        free(subscription);
        ss_event_unlock();
        return NULL;
    }
    subscription->magic = SS_EVENT_SUBSCRIPTION_MAGIC;
    subscription->stream = stream;
    subscription->cursor_event_id = after_event_id;
    subscription->acknowledged_event_id = after_event_id;
    subscription->queue_capacity = queue_capacity;

    if (stream->closed) {
        free(subscription->event_type_filter);
        free(subscription->event_key_filter);
        free(subscription);
        ss_event_unlock();
        return NULL;
    }
    if (stream->durable && stream->head != NULL
            && after_event_id + 1 < stream->head->event_id) {
        if (subscription->event_type_filter[0] == '\0'
                && subscription->event_key_filter[0] == '\0') {
            subscription->dropped_matching_event_gap = 1;
        } else {
            store_status = ss_event_store_has_matching_record_before(
                stream->store_path,
                after_event_id,
                stream->head->event_id,
                subscription->event_type_filter,
                subscription->event_key_filter,
                &has_dropped_match
            );
            if (store_status != SS_EVENT_OK) {
                free(subscription->event_type_filter);
                free(subscription->event_key_filter);
                free(subscription);
                ss_event_unlock();
                return NULL;
            }
            if (has_dropped_match) {
                subscription->dropped_matching_event_gap = 1;
            }
        }
    }
    subscription->next_subscription = stream->subscriptions;
    stream->subscriptions = subscription;
    ss_event_unlock();
    return subscription;
}

long long ss_event_receive(
    void *subscription_handle,
    char *out_event_type,
    int out_event_type_capacity,
    char *out_event_key,
    int out_event_key_capacity,
    char *out_payload_json,
    int out_payload_capacity
) {
    SSEventSubscription *subscription = (SSEventSubscription *)subscription_handle;
    long long result;
    ss_event_lock();
    result = ss_event_receive_next(
        subscription,
        out_event_type,
        out_event_type_capacity,
        out_event_key,
        out_event_key_capacity,
        out_payload_json,
        out_payload_capacity
    );
    ss_event_unlock();
    return result;
}

int ss_event_acknowledge(void *subscription_handle, long long event_id) {
    SSEventSubscription *subscription = (SSEventSubscription *)subscription_handle;
    SSEventStream *stream;
    int result = SS_EVENT_OK;

    ss_event_lock();
    if (subscription == NULL || subscription->magic != SS_EVENT_SUBSCRIPTION_MAGIC || event_id < 0) {
        ss_event_unlock();
        return SS_EVENT_ERR_CONFIG;
    }
    stream = subscription->stream;
    if (subscription->closed || stream == NULL || stream->magic != SS_EVENT_STREAM_MAGIC) {
        ss_event_unlock();
        return SS_EVENT_ERR_SUBSCRIPTION_CLOSED;
    }
    if (event_id > subscription->acknowledged_event_id) {
        subscription->acknowledged_event_id = event_id;
    }
    if (stream != NULL && stream->magic == SS_EVENT_STREAM_MAGIC) {
        ss_event_prune_acknowledged_queue_records_locked(stream);
    }
    ss_event_unlock();
    return result;
}

int ss_event_close_subscription(void *subscription_handle) {
    SSEventSubscription *subscription = (SSEventSubscription *)subscription_handle;
    SSEventStream *stream;
    SSEventSubscription **cursor;

    ss_event_lock();
    if (subscription == NULL || subscription->magic != SS_EVENT_SUBSCRIPTION_MAGIC) {
        ss_event_unlock();
        return SS_EVENT_ERR_CONFIG;
    }
    ss_event_complete_subscription_pending(subscription, SS_EVENT_ERR_SUBSCRIPTION_CLOSED);
    stream = subscription->stream;
    if (stream != NULL && stream->magic == SS_EVENT_STREAM_MAGIC) {
        cursor = &stream->subscriptions;
        while (*cursor != NULL) {
            if (*cursor == subscription) {
                *cursor = subscription->next_subscription;
                break;
            }
            cursor = &(*cursor)->next_subscription;
        }
    }
    subscription->magic = 0;
    subscription->closed = 1;
    subscription->stream = NULL;
    free(subscription->event_type_filter);
    subscription->event_type_filter = NULL;
    free(subscription->event_key_filter);
    subscription->event_key_filter = NULL;
    /* Keep a tombstone so stale subscription handles fail magic checks. */
    ss_event_unlock();
    return SS_EVENT_OK;
}

int ss_event_open_process_stream_start(
    SSAsyncLoop *loop,
    const char *stream_name,
    int queue_capacity,
    unsigned long long timeout_ms,
    void *cancel_token,
    void **out_future
) {
    SSEventAsyncFuture *future;

    (void)timeout_ms;
    (void)cancel_token;
    if (out_future == NULL) {
        return SS_EVENT_ERR_CONFIG;
    }
    *out_future = NULL;
    future = ss_event_future_create(loop);
    if (future == NULL) {
        return loop == NULL ? SS_EVENT_ERR_CONFIG : SS_EVENT_ERR_ENGINE;
    }
    ss_event_future_set_cancel_token(future, cancel_token);
    if (ss_event_future_cancel_requested(future)) {
        ss_event_future_complete_cancelled(future);
        *out_future = future;
        return SS_EVENT_OK;
    }
    ss_event_future_complete_ptr(
        future,
        ss_event_open_process_stream(stream_name, queue_capacity)
    );
    SS_EVENT_DEBUG_LOG("event.open stream=%p\n", future->ptr_result);
    *out_future = future;
    return SS_EVENT_OK;
}

int ss_event_open_durable_stream_start(
    SSAsyncLoop *loop,
    const char *stream_name,
    int queue_capacity,
    unsigned long long timeout_ms,
    void *cancel_token,
    void **out_future
) {
    SSEventAsyncFuture *future;

    (void)timeout_ms;
    if (out_future == NULL) {
        return SS_EVENT_ERR_CONFIG;
    }
    *out_future = NULL;
    future = ss_event_future_create(loop);
    if (future == NULL) {
        return loop == NULL ? SS_EVENT_ERR_CONFIG : SS_EVENT_ERR_ENGINE;
    }
    ss_event_future_set_cancel_token(future, cancel_token);
    if (ss_event_future_cancel_requested(future)) {
        ss_event_future_complete_cancelled(future);
        *out_future = future;
        return SS_EVENT_OK;
    }
    ss_event_future_complete_ptr(
        future,
        ss_event_open_durable_stream(stream_name, queue_capacity)
    );
    *out_future = future;
    return SS_EVENT_OK;
}

void *ss_event_open_durable_stream_await(SSAsyncLoop *loop, void *future_handle) {
    return ss_event_open_process_stream_await(loop, future_handle);
}

int ss_event_open_process_queue_start(
    SSAsyncLoop *loop,
    const char *stream_name,
    int queue_capacity,
    unsigned long long timeout_ms,
    void *cancel_token,
    void **out_future
) {
    SSEventAsyncFuture *future;

    (void)timeout_ms;
    (void)cancel_token;
    if (out_future == NULL) {
        return SS_EVENT_ERR_CONFIG;
    }
    *out_future = NULL;
    future = ss_event_future_create(loop);
    if (future == NULL) {
        return loop == NULL ? SS_EVENT_ERR_CONFIG : SS_EVENT_ERR_ENGINE;
    }
    ss_event_future_set_cancel_token(future, cancel_token);
    if (ss_event_future_cancel_requested(future)) {
        ss_event_future_complete_cancelled(future);
        *out_future = future;
        return SS_EVENT_OK;
    }
    ss_event_future_complete_ptr(
        future,
        ss_event_open_process_queue(stream_name, queue_capacity)
    );
    *out_future = future;
    return SS_EVENT_OK;
}

void *ss_event_open_process_queue_await(SSAsyncLoop *loop, void *future_handle) {
    return ss_event_open_process_stream_await(loop, future_handle);
}

void *ss_event_open_process_stream_await(SSAsyncLoop *loop, void *future_handle) {
    SSEventAsyncFuture *future = (SSEventAsyncFuture *)future_handle;
    void *result;

    if (ss_event_wait_until_ready(loop, future) != SS_EVENT_OK) {
        ss_event_future_destroy(future);
        return NULL;
    }
    result = future->ptr_result;
    ss_event_future_destroy(future);
    return result;
}

int ss_event_close_stream_start(
    SSAsyncLoop *loop,
    void *stream,
    unsigned long long timeout_ms,
    void *cancel_token,
    void **out_future
) {
    SSEventAsyncFuture *future;

    (void)timeout_ms;
    (void)cancel_token;
    if (out_future == NULL) {
        return SS_EVENT_ERR_CONFIG;
    }
    *out_future = NULL;
    future = ss_event_future_create(loop);
    if (future == NULL) {
        return loop == NULL ? SS_EVENT_ERR_CONFIG : SS_EVENT_ERR_ENGINE;
    }
    ss_event_future_set_cancel_token(future, cancel_token);
    if (ss_event_future_cancel_requested(future)) {
        ss_event_future_complete_cancelled(future);
        *out_future = future;
        return SS_EVENT_OK;
    }
    ss_event_future_complete_i32(future, ss_event_close_stream(stream));
    *out_future = future;
    return SS_EVENT_OK;
}

int ss_event_close_stream_await(SSAsyncLoop *loop, void *future_handle) {
    SSEventAsyncFuture *future = (SSEventAsyncFuture *)future_handle;
    int result;

    result = ss_event_wait_until_ready(loop, future);
    if (result != SS_EVENT_OK) {
        ss_event_future_destroy(future);
        return result;
    }
    result = future->i32_result;
    ss_event_future_destroy(future);
    return result;
}

int ss_event_append_start(
    SSAsyncLoop *loop,
    void *stream,
    const char *event_type,
    const char *event_key,
    const char *payload_json,
    unsigned long long timeout_ms,
    void *cancel_token,
    void **out_future
) {
    SSEventAsyncFuture *future;

    (void)timeout_ms;
    (void)cancel_token;
    if (out_future == NULL) {
        return SS_EVENT_ERR_CONFIG;
    }
    *out_future = NULL;
    future = ss_event_future_create(loop);
    if (future == NULL) {
        return loop == NULL ? SS_EVENT_ERR_CONFIG : SS_EVENT_ERR_ENGINE;
    }
    ss_event_future_set_cancel_token(future, cancel_token);
    if (ss_event_future_cancel_requested(future)) {
        ss_event_future_complete_cancelled(future);
        *out_future = future;
        return SS_EVENT_OK;
    }
    ss_event_future_complete_i64(
        future,
        ss_event_append(stream, event_type, event_key, payload_json)
    );
    SS_EVENT_DEBUG_LOG("event.append stream=%p id=%lld\n", stream, future->i64_result);
    *out_future = future;
    return SS_EVENT_OK;
}

long long ss_event_append_await(SSAsyncLoop *loop, void *future_handle) {
    SSEventAsyncFuture *future = (SSEventAsyncFuture *)future_handle;
    long long result;
    int wait_status;

    wait_status = ss_event_wait_until_ready(loop, future);
    if (wait_status != SS_EVENT_OK) {
        ss_event_future_destroy(future);
        return wait_status;
    }
    result = future->i64_result;
    ss_event_future_destroy(future);
    return result;
}

int ss_event_subscribe_start(
    SSAsyncLoop *loop,
    void *stream,
    const char *event_type,
    const char *event_key,
    long long after_event_id,
    int queue_capacity,
    unsigned long long timeout_ms,
    void *cancel_token,
    void **out_future
) {
    SSEventAsyncFuture *future;

    (void)timeout_ms;
    (void)cancel_token;
    if (out_future == NULL) {
        return SS_EVENT_ERR_CONFIG;
    }
    *out_future = NULL;
    future = ss_event_future_create(loop);
    if (future == NULL) {
        return loop == NULL ? SS_EVENT_ERR_CONFIG : SS_EVENT_ERR_ENGINE;
    }
    ss_event_future_set_cancel_token(future, cancel_token);
    if (ss_event_future_cancel_requested(future)) {
        ss_event_future_complete_cancelled(future);
        *out_future = future;
        return SS_EVENT_OK;
    }
    ss_event_future_complete_ptr(
        future,
        ss_event_subscribe(stream, event_type, event_key, after_event_id, queue_capacity)
    );
    SS_EVENT_DEBUG_LOG("event.subscribe stream=%p subscription=%p\n", stream, future->ptr_result);
    *out_future = future;
    return SS_EVENT_OK;
}

void *ss_event_subscribe_await(SSAsyncLoop *loop, void *future_handle) {
    SSEventAsyncFuture *future = (SSEventAsyncFuture *)future_handle;
    void *result;

    if (ss_event_wait_until_ready(loop, future) != SS_EVENT_OK) {
        ss_event_future_destroy(future);
        return NULL;
    }
    result = future->ptr_result;
    ss_event_future_destroy(future);
    return result;
}

int ss_event_receive_start(
    SSAsyncLoop *loop,
    void *subscription_handle,
    char *out_event_type,
    int out_event_type_capacity,
    char *out_event_key,
    int out_event_key_capacity,
    char *out_payload_json,
    int out_payload_capacity,
    unsigned long long timeout_ms,
    void *cancel_token,
    void **out_future
) {
    SSEventSubscription *subscription = (SSEventSubscription *)subscription_handle;
    SSEventAsyncFuture *future;
    long long event_id;
    int timer_status;

    (void)cancel_token;
    if (out_future == NULL) {
        return SS_EVENT_ERR_CONFIG;
    }
    *out_future = NULL;
    future = ss_event_future_create(loop);
    if (future == NULL) {
        return loop == NULL ? SS_EVENT_ERR_CONFIG : SS_EVENT_ERR_ENGINE;
    }
    ss_event_future_set_cancel_token(future, cancel_token);
    future->out_event_type = out_event_type;
    future->out_event_type_capacity = out_event_type_capacity;
    future->out_event_key = out_event_key;
    future->out_event_key_capacity = out_event_key_capacity;
    future->out_payload_json = out_payload_json;
    future->out_payload_capacity = out_payload_capacity;
    if (ss_event_future_cancel_requested(future)) {
        ss_event_future_complete_cancelled(future);
        *out_future = future;
        return SS_EVENT_OK;
    }

    ss_event_lock();
    event_id = ss_event_receive_next(
        subscription,
        out_event_type,
        out_event_type_capacity,
        out_event_key,
        out_event_key_capacity,
        out_payload_json,
        out_payload_capacity
    );
    if (event_id != SS_EVENT_NO_EVENT) {
        SS_EVENT_DEBUG_LOG("event.receive immediate subscription=%p result=%lld\n", subscription, event_id);
        ss_event_future_complete_i64(future, event_id);
        *out_future = future;
        ss_event_unlock();
        return SS_EVENT_OK;
    }
    if (subscription == NULL || subscription->magic != SS_EVENT_SUBSCRIPTION_MAGIC || subscription->closed) {
        SS_EVENT_DEBUG_LOG("event.receive invalid subscription=%p result=%d\n", subscription, SS_EVENT_ERR_SUBSCRIPTION_CLOSED);
        ss_event_future_complete_i64(future, SS_EVENT_ERR_SUBSCRIPTION_CLOSED);
        *out_future = future;
        ss_event_unlock();
        return SS_EVENT_OK;
    }

    timer_status = ss_event_start_timer_if_needed(future, timeout_ms);
    if (timer_status != SS_EVENT_OK) {
        ss_event_unlock();
        ss_event_future_destroy(future);
        return timer_status;
    }

    future->pending_subscription = subscription;
    if (subscription->pending_receives_tail != NULL) {
        subscription->pending_receives_tail->next_pending = future;
    } else {
        subscription->pending_receives = future;
    }
    subscription->pending_receives_tail = future;
    SS_EVENT_DEBUG_LOG("event.receive pending subscription=%p\n", subscription);
    *out_future = future;
    ss_event_unlock();
    return SS_EVENT_OK;
}

long long ss_event_receive_await(SSAsyncLoop *loop, void *future_handle) {
    SSEventAsyncFuture *future = (SSEventAsyncFuture *)future_handle;
    long long result;
    int wait_status;

    wait_status = ss_event_wait_until_ready(loop, future);
    if (wait_status != SS_EVENT_OK) {
        ss_event_future_destroy(future);
        return wait_status;
    }
    result = future->i64_result;
    ss_event_future_destroy(future);
    return result;
}

int ss_event_acknowledge_start(
    SSAsyncLoop *loop,
    void *subscription,
    long long event_id,
    unsigned long long timeout_ms,
    void *cancel_token,
    void **out_future
) {
    SSEventAsyncFuture *future;

    (void)timeout_ms;
    (void)cancel_token;
    if (out_future == NULL) {
        return SS_EVENT_ERR_CONFIG;
    }
    *out_future = NULL;
    future = ss_event_future_create(loop);
    if (future == NULL) {
        return loop == NULL ? SS_EVENT_ERR_CONFIG : SS_EVENT_ERR_ENGINE;
    }
    ss_event_future_set_cancel_token(future, cancel_token);
    if (ss_event_future_cancel_requested(future)) {
        ss_event_future_complete_cancelled(future);
        *out_future = future;
        return SS_EVENT_OK;
    }
    ss_event_future_complete_i32(future, ss_event_acknowledge(subscription, event_id));
    *out_future = future;
    return SS_EVENT_OK;
}

int ss_event_acknowledge_await(SSAsyncLoop *loop, void *future_handle) {
    SSEventAsyncFuture *future = (SSEventAsyncFuture *)future_handle;
    int result;

    result = ss_event_wait_until_ready(loop, future);
    if (result != SS_EVENT_OK) {
        ss_event_future_destroy(future);
        return result;
    }
    result = future->i32_result;
    ss_event_future_destroy(future);
    return result;
}

int ss_event_close_subscription_start(
    SSAsyncLoop *loop,
    void *subscription,
    unsigned long long timeout_ms,
    void *cancel_token,
    void **out_future
) {
    SSEventAsyncFuture *future;

    (void)timeout_ms;
    (void)cancel_token;
    if (out_future == NULL) {
        return SS_EVENT_ERR_CONFIG;
    }
    *out_future = NULL;
    future = ss_event_future_create(loop);
    if (future == NULL) {
        return loop == NULL ? SS_EVENT_ERR_CONFIG : SS_EVENT_ERR_ENGINE;
    }
    ss_event_future_set_cancel_token(future, cancel_token);
    if (ss_event_future_cancel_requested(future)) {
        ss_event_future_complete_cancelled(future);
        *out_future = future;
        return SS_EVENT_OK;
    }
    ss_event_future_complete_i32(future, ss_event_close_subscription(subscription));
    *out_future = future;
    return SS_EVENT_OK;
}

int ss_event_close_subscription_await(SSAsyncLoop *loop, void *future_handle) {
    SSEventAsyncFuture *future = (SSEventAsyncFuture *)future_handle;
    int result;

    result = ss_event_wait_until_ready(loop, future);
    if (result != SS_EVENT_OK) {
        ss_event_future_destroy(future);
        return result;
    }
    result = future->i32_result;
    ss_event_future_destroy(future);
    return result;
}
