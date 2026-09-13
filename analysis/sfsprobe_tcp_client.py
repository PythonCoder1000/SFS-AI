"""
sfsprobe_tcp_client.py -- persistent-socket client for SFSProbe's new TCP
command path (see TCP_REWRITE_SPEC.md and sfsprobe/SFSProbe.cs's
ProbeRunner tcp* members).

This is a standalone module, deliberately NOT wired into
agent_interface.py's default path yet (that's checkpoint 4, behind an
explicit flag). It exists so the TCP path can be exercised and its
latency measured on its own, without touching the file-protocol code
that worktree-optionA-build depends on.

Protocol: plain-text, newline-delimited, over one persistent TCP
connection to 127.0.0.1:<TCP_PORT>. One line in, one line back, same
content ProbeMod.Result() already produces via the file path -- only the
transport changed. Multiple "cmd\n"-terminated lines in a single send()
are supported (Probe.Command() dispatches each line the mod's reader
thread enqueues), producing that many result lines back.
"""
import socket
import time

# Must match ProbeMod.TcpPort in sfsprobe/SFSProbe.cs.
TCP_PORT = 47821
TCP_HOST = "127.0.0.1"


class SfsProbeTcpClient:
    """Keeps one TCP connection open across many commands -- the whole
    point of this rewrite is not paying a reconnect (or a file-poll
    interval) per call. Not thread-safe: one client instance per caller
    thread, matching how _send_command() is used today."""

    def __init__(self, host: str = TCP_HOST, port: int = TCP_PORT,
                 timeout_s: float = 5.0):
        self.host = host
        self.port = port
        self.timeout_s = timeout_s
        self._sock: socket.socket | None = None
        self._buf = b""

    def _connect(self):
        s = socket.create_connection((self.host, self.port), timeout=self.timeout_s)
        s.settimeout(self.timeout_s)
        self._sock = s
        self._buf = b""

    def close(self):
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None

    def _read_line(self) -> str:
        """Blocks (up to self.timeout_s, socket-level -- no busy-poll)
        until a newline-terminated response arrives."""
        while b"\n" not in self._buf:
            chunk = self._sock.recv(4096)
            if not chunk:
                raise ConnectionError("socket closed by mod (EOF) while awaiting response")
            self._buf += chunk
        line, self._buf = self._buf.split(b"\n", 1)
        return line.decode("utf-8", errors="replace").strip()

    def send(self, command: str) -> str:
        """Send one command, return its stripped response -- same return
        contract as agent_interface._send_command(). Reconnects once on
        any socket-level failure (mod restarted, game crashed, stale
        connection after idle) before raising, rather than being
        permanently dead for the rest of the process."""
        if self._sock is None:
            self._connect()
        try:
            self._sock.sendall((command + "\n").encode("utf-8"))
            return self._read_line()
        except (OSError, ConnectionError, socket.timeout):
            self.close()
            self._connect()
            self._sock.sendall((command + "\n").encode("utf-8"))
            return self._read_line()

    def send_batch(self, commands: list[str]) -> list[str]:
        """Write multiple commands in ONE socket write, then read that
        many response lines back -- exercises the same-tick batching
        Probe.Command()'s caller already supports (checkpoint 3)."""
        if self._sock is None:
            self._connect()
        payload = "".join(c + "\n" for c in commands).encode("utf-8")
        try:
            self._sock.sendall(payload)
            return [self._read_line() for _ in commands]
        except (OSError, ConnectionError, socket.timeout):
            self.close()
            self._connect()
            self._sock.sendall(payload)
            return [self._read_line() for _ in commands]


if __name__ == "__main__":
    # Checkpoint 2 self-test: ping 10x in a row, no reconnects needed,
    # game left running throughout.
    client = SfsProbeTcpClient()
    times = []
    for i in range(10):
        t0 = time.time()
        resp = client.send("ping")
        dt = time.time() - t0
        times.append(dt)
        print(f"[{i}] {dt*1000:.1f}ms  {resp}")
    print(f"min={min(times)*1000:.1f}ms mean={sum(times)/len(times)*1000:.1f}ms "
          f"max={max(times)*1000:.1f}ms")
