"""Deterministic inner controller (Checkpoint A skeleton).

Calls observe()/act() from the existing agent_interface.py directly.
Guidance logic is a stub for now — filled in at Checkpoint B.
"""

from agent_interface import observe, act


def run_tick():
    state = observe()
    # TODO: PID / state-machine guidance goes here (Checkpoint B)
    return state


if __name__ == "__main__":
    run_tick()
