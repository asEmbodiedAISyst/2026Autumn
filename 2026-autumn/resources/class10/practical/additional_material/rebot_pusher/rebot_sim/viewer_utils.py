"""Helpers for the MuJoCo passive viewer."""

from __future__ import annotations

import threading


def close_viewer(viewer, timeout: float = 3.0) -> None:
    """Close a passive viewer and wait for its render thread to finish.

    ``Handle.close()`` only requests the exit. If the interpreter shuts down while the viewer thread is
    still inside GLFW, the ``glfw`` package's atexit ``terminate()`` races with it and the process
    segfaults on exit. Joining the thread first avoids that.
    """
    if viewer is None:
        return
    import mujoco.viewer

    viewer.close()
    for t in threading.enumerate():
        if t is not threading.current_thread() and getattr(t, "_target", None) is mujoco.viewer._launch_internal:
            t.join(timeout)
