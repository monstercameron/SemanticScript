"""Tasks, task groups, and blocking waits for compiled programs (D-31).

Every `start` runs its task on a new OS thread with its own large stack, so
tasks run in parallel: compiled code releases the interpreter lock while it
runs, and takes it back only for runtime callbacks. A task's arguments travel
in a frame the compiled code fills before `start` and reads after `join`.

Waits that only another task can end (a `join`, `awaitSlot`, a channel send or
receive) go through `wait_until`. A thread waiting there is not *active*; a
thread blocked in the operating system (sleeping, accepting a connection,
reading a socket) still is, since the world outside can wake it. When no
thread is active and no wait has a deadline, nothing can ever change again:
that is a deadlock, and it traps instead of hanging.

Cancellation is cooperative (D-44): `cancel` marks the task (or every task of
a group) and the tasks it started, wakes every wait, and returns at once. A
marked task sees `cancelled` from its next channel wait, sleep, accept, read,
or child-process wait; pure computation runs to its end. `join` is what waits
for a task to stop, and the checker requires a `join` after every `start`,
cancelled or not, so no task outlives the operation that started it.

Recursion depth and the stack floor are kept per thread (`recursion_enter`).
"""
from __future__ import annotations

import ctypes
import threading
import time
from typing import Callable, Optional

from . import runtime as rt

TASK_STACK_BYTES = 64 * 1024 * 1024
POLL_SECONDS = 0.05
DEADLOCK_POLLS = 6  # how many quiet polls in a row it takes to call a wait a deadlock



class _Scheduler(threading.Condition):
    """The scheduler's lock and condition, counting every wake-up: a waiter that was woken by a change (a task that
    ended, a send, a cancel) has not seen a quiet poll, however briefly every thread looked idle at that moment."""

    def __init__(self):
        super().__init__()
        self.changes = 0

    def notify_all(self):
        self.changes += 1
        super().notify_all()


_sched = _Scheduler()
_stack_lock = threading.Lock()
_tls = threading.local()
_state = {"active": 0, "timed": 0}
_waiting: dict[int, str] = {}  # thread id -> what it waits for, while it waits
_tasks: dict[int, "Task"] = {}
_groups: dict[int, "Group"] = {}
_frames: dict[int, ctypes.Array] = {}
_next = [1]
STACK_HERE: Optional[Callable[[], int]] = None  # set by the engine: the address of a frame on the calling thread


class Task:
    def __init__(self, frame: ctypes.Array, group: Optional["Group"]):
        self.frame, self.group = frame, group
        self.done = False
        self.cancelled = False
        self.children: list["Task"] = []  # tasks this task started: cancelling it cancels them too
        self.thread: Optional[threading.Thread] = None


def _cancel_tree(task: "Task") -> None:
    """Mark a task and everything it started, however deep (call with the scheduler lock held)."""
    task.cancelled = True
    for child in task.children:
        _cancel_tree(child)


class Group:
    def __init__(self, limit: int):
        self.limit, self.running, self.members, self.cancelled = limit, 0, [], False
        self.error: Optional[bytes] = None  # the first failure of one of its tasks (D-48)


def _new_id() -> int:
    n = _next[0]
    _next[0] += 1
    return n


def enter_program_thread(budget: int, task: Optional[Task] = None) -> None:
    """Called first on every thread that runs compiled code."""
    _tls.floor = (STACK_HERE() - budget) if STACK_HERE is not None else 0
    _tls.depth = {}
    _tls.task = task


def start_program() -> None:
    with _sched:
        _state["active"], _state["timed"] = 1, 0


def current() -> Optional[Task]:
    return getattr(_tls, "task", None)


def cancelled() -> bool:
    t = current()
    return t is not None and t.cancelled


def notify() -> None:
    with _sched:
        _sched.notify_all()


def wait_until(ready: Callable[[], bool], deadline: Optional[float], what: str, cancellable: bool = True) -> str:
    """Wait for `ready()` (checked under the scheduler lock). `deadline` is a `time.monotonic()` value or None.
    Returns "ready", "timedOut", or "cancelled"; traps on a deadlock."""
    quiet = 0
    with _sched:
        seen = _sched.changes
        while True:
            if ready():
                return "ready"
            if cancellable and cancelled():
                return "cancelled"
            if deadline is not None and time.monotonic() >= deadline:
                return "timedOut"
            _state["active"] -= 1
            if deadline is not None:
                _state["timed"] += 1
            # a deadlock is a stretch of polls with no thread active, no deadline, and no change at all: a wait woken
            # by a change (a task that just ended, and whose joiner has not run yet) starts the count again
            if _state["active"] == 0 and _state["timed"] == 0 and _sched.changes == seen:
                quiet += 1
            else:
                quiet = 0
            seen = _sched.changes
            if quiet >= DEADLOCK_POLLS:
                _state["active"] += 1
                others = sorted(set(_waiting.values()) - {what})
                rt._trap_now("deadlock: every task is waiting on another: " + "; ".join([what] + others))
            timeout = POLL_SECONDS if deadline is None else max(0.0, min(POLL_SECONDS, deadline - time.monotonic()))
            _waiting[threading.get_ident()] = what
            _sched.wait(timeout)
            _waiting.pop(threading.get_ident(), None)
            _state["active"] += 1
            if deadline is not None:
                _state["timed"] -= 1


def sleep(seconds: float) -> None:
    """Sleep, waking early if the current task is cancelled. Counts as a wait with a deadline."""
    wait_until(lambda: False, time.monotonic() + max(0.0, seconds), "a sleep")


# ---------------------------------------------------------------- callbacks for compiled code

@ctypes.CFUNCTYPE(ctypes.c_void_p, ctypes.c_int64)
def _task_frame(size):
    buf = ctypes.create_string_buffer(max(int(size), 1))
    addr = ctypes.addressof(buf)
    _frames[addr] = buf
    return addr


def _run_task(task: Task, thunk, addr: int) -> None:
    enter_program_thread(TASK_STACK_BYTES - rt.STACK_MARGIN_BYTES, task)
    try:
        thunk(addr)
    finally:
        with _sched:
            task.done = True
            task.children = [c for c in task.children if not c.done]
            _state["active"] -= 1
            if task.group is not None:
                task.group.running -= 1
                task.frame = None  # nobody reads a group task's results
            _sched.notify_all()


@ctypes.CFUNCTYPE(ctypes.c_int64, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int64)
def _task_spawn(thunk_addr, frame_addr, group_handle):
    group = _groups.get(group_handle) if group_handle else None
    task = Task(_frames.pop(frame_addr), group)
    thunk = ctypes.CFUNCTYPE(None, ctypes.c_void_p)(thunk_addr)
    with _sched:
        if group is not None:
            if group.running >= group.limit:
                rt._trap_now(f"a task was started into a full task group (limit {group.limit}); "
                             "`awaitSlot` waits for room")
            group.running += 1
            group.members.append(task)
            task.cancelled = group.cancelled
        parent = current()
        if parent is not None:
            parent.children.append(task)
            task.cancelled = task.cancelled or parent.cancelled
        _state["active"] += 1
    handle = _new_id()
    _tasks[handle] = task
    with _stack_lock:
        previous = threading.stack_size(TASK_STACK_BYTES)
        try:
            task.thread = threading.Thread(target=_run_task, args=(task, thunk, frame_addr), daemon=True,
                                           name=f"refined-task-{handle}")
            task.thread.start()
        finally:
            threading.stack_size(previous)
    if group is not None:
        del _tasks[handle]  # a group task is reached through its group, never by handle
        return 0
    return handle


def _wait_done(tasks: list[Task], what: str) -> None:
    wait_until(lambda: all(t.done for t in tasks), None, what, cancellable=False)


@ctypes.CFUNCTYPE(None, ctypes.c_int64)
def _task_join(handle):
    task = _tasks.get(handle)
    if task is not None:
        _wait_done([task], "a `join` waits for a task")


@ctypes.CFUNCTYPE(None, ctypes.c_int64)
def _task_cancel(handle):
    task = _tasks.get(handle)
    if task is None:
        return
    with _sched:
        _cancel_tree(task)
        _sched.notify_all()


@ctypes.CFUNCTYPE(None, ctypes.c_int64)
def _task_release(handle):
    _tasks.pop(handle, None)


@ctypes.CFUNCTYPE(ctypes.c_int64, ctypes.c_int64)
def _group_new(limit):
    handle = _new_id()
    _groups[handle] = Group(int(limit))
    return handle


@ctypes.CFUNCTYPE(None, ctypes.c_int64)
def _group_await(handle):
    group = _groups[handle]
    wait_until(lambda: group.running < group.limit, None, "an `awaitSlot` waits for room in a task group",
               cancellable=False)


@ctypes.CFUNCTYPE(None, ctypes.c_int64)
def _group_join(handle):
    group = _groups[handle]
    _wait_done(list(group.members), "a `join` waits for a task group")
    group.members = [t for t in group.members if not t.done]
    group.cancelled = False  # a joined group starts afresh


@ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_int64)
def _task_fail(error_addr, size):
    """D-48: the first task of a group to fail records its error there and cancels the group's other tasks, so
    `join` returns soon and delivers that error. Outside a group the failure is read from the task's frame."""
    task = current()
    group = task.group if task is not None else None
    if group is None:
        return
    with _sched:
        if group.error is None:
            group.error = ctypes.string_at(error_addr, size)
            group.cancelled = True
            for t in group.members:
                if t is not task:
                    _cancel_tree(t)
        _sched.notify_all()


@ctypes.CFUNCTYPE(ctypes.c_int32, ctypes.c_int64, ctypes.c_void_p, ctypes.c_int64)
def _group_error(handle, out_addr, size):
    group = _groups[handle]
    if group.error is None:
        return 0
    ctypes.memmove(out_addr, group.error, min(size, len(group.error)))
    group.error = None
    return 1


@ctypes.CFUNCTYPE(None, ctypes.c_int64)
def _group_cancel(handle):
    group = _groups[handle]
    with _sched:
        group.cancelled = True
        for t in group.members:
            _cancel_tree(t)
        _sched.notify_all()


@ctypes.CFUNCTYPE(None, ctypes.c_int64)
def _group_free(handle):
    _groups.pop(handle, None)


@ctypes.CFUNCTYPE(ctypes.c_int32, ctypes.c_int64, ctypes.c_int64, ctypes.c_int64)
def _recursion_enter(op_id, limit, here):
    """0: go on; 1: deeper than maxRecursion; 2: the stack is about to run out."""
    depth = getattr(_tls, "depth", None)
    if depth is None:
        _tls.depth = depth = {}
    d = depth.get(op_id, 0) + 1
    depth[op_id] = d
    if d > limit:
        return 1
    floor = getattr(_tls, "floor", 0)
    if floor and here < floor:
        return 2
    return 0


@ctypes.CFUNCTYPE(None, ctypes.c_int64)
def _recursion_leave(op_id):
    _tls.depth[op_id] -= 1


@ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_int64)
def _frame_push(ptr, length):
    frames = getattr(_tls, "frames", None)
    if frames is None:
        _tls.frames = frames = []
    frames.append((ptr, length))
    if PROFILING[0]:
        from . import instrument
        instrument.profile_push(ctypes.string_at(ptr, length).decode("utf-8", "replace"))


@ctypes.CFUNCTYPE(None)
def _frame_pop():
    _tls.frames.pop()
    if PROFILING[0]:
        from . import instrument
        instrument.profile_pop()


PROFILING = [False]


def stack_trace(limit: int = 12) -> list[str]:
    """The calling thread's operations, innermost first (the names are constants in the compiled program)."""
    frames = getattr(_tls, "frames", [])
    names = [ctypes.string_at(p, n).decode("utf-8", "replace") for p, n in reversed(frames)]
    runs: list[list] = []  # consecutive repeats (a recursion) collapse into one line with a count
    for n in names:
        if runs and runs[-1][0] == n:
            runs[-1][1] += 1
        else:
            runs.append([n, 1])
    task = current()
    lines = [f"  in {n}" + (f" ({k} calls deep)" if k > 1 else "") for n, k in runs[:limit]]
    if len(runs) > limit:
        lines.append(f"  ... and {len(runs) - limit} more")
    if task is not None:
        lines.append("  (in a task started with `start`)")
    return lines


CALLBACKS = {
    "refined_task_frame": _task_frame, "refined_task_spawn": _task_spawn, "refined_task_join": _task_join,
    "refined_task_cancel": _task_cancel, "refined_task_release": _task_release,
    "refined_group_new": _group_new, "refined_group_await": _group_await, "refined_group_join": _group_join,
    "refined_group_cancel": _group_cancel, "refined_group_free": _group_free,
    "refined_task_fail": _task_fail, "refined_group_error": _group_error,
    "refined_recursion_enter": _recursion_enter, "refined_recursion_leave": _recursion_leave,
    "refined_frame_push": _frame_push, "refined_frame_pop": _frame_pop,
}
