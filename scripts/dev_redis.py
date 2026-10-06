#!/usr/bin/env python3
"""Minimal Redis-compatible server for local verification and load testing.

Purpose
-------
The sandbox used to verify CORTEX has no ``redis-server`` package available, and
several behaviours can only be tested against a *real* network service:

* the event stream contract (``XADD`` by the API, ``XREADGROUP`` by the worker),
* the distributed rate limiter and idempotency store that degrade when Redis is
  unreachable,
* end-to-end latency of ingestion including the Redis round trip.

This module implements the small subset of RESP (REdis Serialization Protocol)
that CORTEX uses, over TCP, so the application connects to it exactly as it would
to Redis. It is a **development and test double**, not a production server: no
persistence, no replication, no ACLs, no eviction.

Supported commands
------------------
PING, ECHO, HELLO, AUTH, SET (EX/PX/NX/XX), GET, DEL, EXISTS, INCR, DECR,
EXPIRE, TTL, XADD, XLEN, XRANGE, XGROUP CREATE, XREADGROUP, XACK, INFO, DBSIZE,
FLUSHALL, COMMAND (returns an empty array so client libraries can probe
capabilities), CLIENT SETINFO/SETNAME/GETNAME, SELECT, QUIT.

Usage
-----
    python scripts/dev_redis.py --host 127.0.0.1 --port 6379
"""

from __future__ import annotations

import argparse
import fnmatch
import logging
import socketserver
import threading
import time
from collections import defaultdict, deque

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] dev-redis: %(message)s")
logger = logging.getLogger("dev-redis")

CRLF = b"\r\n"


class RedisError(Exception):
    pass


class Store:
    """Thread-safe in-memory keyspace with Redis-compatible semantics."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._strings: dict[str, str] = {}
        self._expires: dict[str, float] = {}
        self._streams: dict[str, list[tuple[str, dict[str, str]]]] = defaultdict(list)
        self._groups: dict[tuple[str, str], int] = {}  # (stream, group) -> last delivered index
        self._pending: dict[tuple[str, str], deque] = defaultdict(deque)
        self._last_id = 0

    # ── helpers ─────────────────────────────────────────────────────────────
    def _expire_if_needed(self, key: str) -> None:
        deadline = self._expires.get(key)
        if deadline is not None and deadline <= time.time():
            self._strings.pop(key, None)
            self._expires.pop(key, None)

    def _next_id(self) -> str:
        self._last_id += 1
        return f"{int(time.time() * 1000)}-{self._last_id}"

    # ── commands ────────────────────────────────────────────────────────────
    def ping(self) -> str:
        return "PONG"

    def set(self, key: str, value: str, ex: int | None = None, nx: bool = False, xx: bool = False) -> str | None:
        with self._lock:
            self._expire_if_needed(key)
            exists = key in self._strings
            if nx and exists:
                return None
            if xx and not exists:
                return None
            self._strings[key] = value
            if ex:
                self._expires[key] = time.time() + ex
            else:
                self._expires.pop(key, None)
            return "OK"

    def get(self, key: str) -> str | None:
        with self._lock:
            self._expire_if_needed(key)
            return self._strings.get(key)

    def delete(self, *keys: str) -> int:
        with self._lock:
            removed = 0
            for key in keys:
                self._expire_if_needed(key)
                removed += 1 if self._strings.pop(key, None) is not None else 0
            return removed

    def exists(self, *keys: str) -> int:
        with self._lock:
            return sum(1 for key in keys if self.get(key) is not None)

    def incrby(self, key: str, amount: int) -> int:
        with self._lock:
            self._expire_if_needed(key)
            current = int(self._strings.get(key, "0"))
            current += amount
            self._strings[key] = str(current)
            return current

    def expire(self, key: str, seconds: int) -> int:
        with self._lock:
            self._expire_if_needed(key)
            if key not in self._strings:
                return 0
            self._expires[key] = time.time() + seconds
            return 1

    def ttl(self, key: str) -> int:
        with self._lock:
            self._expire_if_needed(key)
            if key not in self._strings:
                return -2
            if key not in self._expires:
                return -1
            return max(int(self._expires[key] - time.time()), 0)

    def keys(self, pattern: str) -> list[str]:
        with self._lock:
            for key in list(self._strings):
                self._expire_if_needed(key)
            return [key for key in self._strings if fnmatch.fnmatch(key, pattern)]

    def xadd(self, stream: str, fields: dict[str, str]) -> str:
        with self._lock:
            entry_id = self._next_id()
            self._streams[stream].append((entry_id, fields))
            return entry_id

    def xlen(self, stream: str) -> int:
        with self._lock:
            return len(self._streams[stream])

    def xrange(self, stream: str, count: int | None) -> list[tuple[str, dict[str, str]]]:
        with self._lock:
            entries = list(self._streams[stream])
            return entries[:count] if count else entries

    def xgroup_create(self, stream: str, group: str, mkstream: bool) -> str:
        with self._lock:
            key = (stream, group)
            if key in self._groups:
                raise RedisError("BUSYGROUP Consumer Group name already exists")
            if mkstream and stream not in self._streams:
                self._streams[stream] = []
            self._groups[key] = 0
            return "OK"

    def xreadgroup(self, group: str, consumer: str, stream: str, count: int, block_ms: int | None):
        deadline = time.time() + (block_ms / 1000.0) if block_ms else None
        while True:
            with self._lock:
                key = (stream, group)
                if key not in self._groups:
                    raise RedisError("NOGROUP No such consumer group")
                index = self._groups[key]
                entries = self._streams[stream]
                batch = entries[index : index + count]
                if batch:
                    self._groups[key] = index + len(batch)
                    self._pending[key].extend(batch)
                    return [(stream, batch)]
            if deadline is None or time.time() >= deadline:
                return []
            time.sleep(0.01)

    def xack(self, stream: str, group: str, entry_id: str) -> int:
        with self._lock:
            key = (stream, group)
            queue = self._pending.get(key)
            if not queue:
                return 0
            remaining = deque(item for item in queue if item[0] != entry_id)
            removed = len(queue) - len(remaining)
            self._pending[key] = remaining
            return removed

    def clear(self) -> None:
        with self._lock:
            self._strings.clear()
            self._expires.clear()
            self._streams.clear()
            self._groups.clear()
            self._pending.clear()

    def stats(self) -> dict[str, int]:
        with self._lock:
            return {
                "keys": len(self._strings),
                "streams": len(self._streams),
                "stream_entries": sum(len(v) for v in self._streams.values()),
                "groups": len(self._groups),
            }


STORE = Store()


class RespHandler(socketserver.StreamRequestHandler):
    """One connection: parse RESP arrays of bulk strings, reply in RESP."""

    def handle(self) -> None:  # noqa: C901 - protocol dispatch is intentionally explicit
        self.server: RedisTCPServer
        try:
            self._serve()
        except (ConnectionResetError, BrokenPipeError):
            # Port scanners and health probes open and drop connections mid-reply; that is
            # normal on a listening socket and must not spray tracebacks into the log.
            return

    def _serve(self) -> None:
        while True:
            try:
                command = self._read_command()
            except (ConnectionResetError, BrokenPipeError, EOFError):
                return
            if command is None:
                return
            name = command[0].decode(errors="replace").upper()
            args = command[1:]
            try:
                reply = self._dispatch(name, args)
            except RedisError as exc:
                logger.debug("rejected command %s: %s", name, exc)
                self._write_error(str(exc))
                continue
            except Exception as exc:  # pragma: no cover - defensive
                logger.exception("command failed: %s", name)
                self._write_error(f"ERR {exc}")
                continue
            if reply is QUIT:
                return
            self._write(reply)

    # ── protocol ────────────────────────────────────────────────────────────
    def _read_exact(self, size: int) -> bytes | None:
        data = self.rfile.read(size)
        if not data or len(data) < size:
            return None
        return data

    def _read_command(self):
        line = self.rfile.readline()
        if not line:
            return None
        if not line.startswith(b"*"):
            # Inline command (e.g. "PING\r\n")
            return line.strip().split()
        count = int(line[1:].strip())
        if count <= 0:
            return None
        parts = []
        for _ in range(count):
            header = self.rfile.readline()
            if not header.startswith(b"$"):
                raise EOFError("expected bulk string")
            length = int(header[1:].strip())
            if length < 0:
                parts.append(b"")
                continue
            payload = self._read_exact(length + 2)
            if payload is None:
                raise EOFError("truncated bulk string")
            parts.append(payload[:-2])
        return parts

    def _write(self, value) -> None:
        self.wfile.write(self._encode(value))
        self.wfile.flush()

    def _encode(self, value) -> bytes:
        if isinstance(value, SimpleString):
            return b"+" + value.text.encode() + CRLF
        if isinstance(value, ErrorString):
            return b"-" + value.text.encode() + CRLF
        if value is None:
            return b"$-1" + CRLF
        if isinstance(value, int):
            return b":" + str(value).encode() + CRLF
        if isinstance(value, bytes):
            return b"$" + str(len(value)).encode() + CRLF + value + CRLF
        if isinstance(value, str):
            payload = value.encode()
            return b"$" + str(len(payload)).encode() + CRLF + payload + CRLF
        if isinstance(value, list):
            out = b"*" + str(len(value)).encode() + CRLF
            for item in value:
                out += self._encode(item)
            return out
        raise TypeError(f"cannot encode {type(value)!r}")

    def _write_error(self, text: str) -> None:
        self.wfile.write(self._encode(ErrorString(text)))
        self.wfile.flush()

    def _dispatch(self, name: str, args: list[bytes]):  # noqa: C901 - command table
        decoded = [a.decode() for a in args]
        if name in {"PING", "PONG"}:
            return SimpleString("PONG")
        if name == "AUTH":
            return SimpleString("OK")
        if name == "HELLO":
            # Advertise a modern protocol version so redis-py's handshake
            # succeeds; RESP2 encoding is used regardless.
            return [
                "server",
                "redis",
                "version",
                "7.0.0-dev-double",
                "proto",
                2,
                "id",
                1,
                "mode",
                "standalone",
                "role",
                "master",
                "modules",
                [],
            ]
        if name == "ECHO":
            return decoded[0] if decoded else ""
        if name == "QUIT":
            return QUIT
        if name == "SELECT":
            return SimpleString("OK")
        if name == "CLIENT":
            sub = decoded[0].upper() if decoded else ""
            if sub == "GETNAME":
                return ""
            return SimpleString("OK")
        if name == "COMMAND":
            return []
        if name == "INFO":
            stats = STORE.stats()
            body = "\r\n".join(f"{k}:{v}" for k, v in stats.items())
            return f"# Server\r\nredis_version:7.0.0-dev-double\r\n{body}\r\n"
        if name == "DBSIZE":
            return STORE.stats()["keys"]
        if name == "FLUSHALL":
            STORE.clear()
            return SimpleString("OK")
        if name == "SET":
            key, value = decoded[0], decoded[1]
            ex = None
            nx = xx = False
            i = 2
            while i < len(decoded):
                token = decoded[i].upper()
                if token == "EX":
                    ex = int(decoded[i + 1])
                    i += 2
                elif token == "PX":
                    ex = max(int(decoded[i + 1]) // 1000, 1)
                    i += 2
                elif token == "NX":
                    nx = True
                    i += 1
                elif token == "XX":
                    xx = True
                    i += 1
                else:
                    i += 1
            result = STORE.set(key, value, ex=ex, nx=nx, xx=xx)
            return SimpleString("OK") if result else None
        if name == "GET":
            return STORE.get(decoded[0])
        if name in {"DEL", "UNLINK"}:
            return STORE.delete(*decoded)
        if name in {"EXISTS", "TOUCH"}:
            return STORE.exists(*decoded)
        if name in {"INCR", "DECR", "INCRBY", "DECRBY"}:
            key = decoded[0]
            if name in {"INCR", "DECR"}:
                amount = 1 if name == "INCR" else -1
            else:
                amount = int(decoded[1])
                if name == "DECRBY":
                    amount = -amount
            return STORE.incrby(key, amount)
        if name in {"EXPIRE", "PEXPIRE"}:
            seconds = int(decoded[1])
            if name == "PEXPIRE":
                seconds = max(seconds // 1000, 1)
            return STORE.expire(decoded[0], seconds)
        if name == "TTL":
            return STORE.ttl(decoded[0])
        if name == "KEYS":
            return STORE.keys(decoded[0])
        if name == "XADD":
            stream = decoded[0]
            # tolerate the explicit "*" id token
            rest = decoded[1:]
            if rest and rest[0] == "*":
                rest = rest[1:]
            fields = {rest[i]: rest[i + 1] for i in range(0, len(rest) - 1, 2)}
            return STORE.xadd(stream, fields)
        if name == "XLEN":
            return STORE.xlen(decoded[0])
        if name == "XRANGE":
            count = None
            if "COUNT" in [d.upper() for d in decoded]:
                index = [d.upper() for d in decoded].index("COUNT")
                count = int(decoded[index + 1])
            entries = STORE.xrange(decoded[0], count)
            return [[entry_id, self._flat(fields)] for entry_id, fields in entries]
        if name == "XGROUP" and decoded and decoded[0].upper() == "CREATE":
            stream, group = decoded[1], decoded[2]
            mkstream = any(token.upper() == "MKSTREAM" for token in decoded[3:])
            return SimpleString(STORE.xgroup_create(stream, group, mkstream))
        if name == "XREADGROUP":
            group = consumer = stream = None
            count = 10
            block = None
            i = 0
            while i < len(decoded):
                token = decoded[i].upper()
                if token == "GROUP":
                    group, consumer = decoded[i + 1], decoded[i + 2]
                    i += 3
                elif token == "COUNT":
                    count = int(decoded[i + 1])
                    i += 2
                elif token == "BLOCK":
                    block = int(decoded[i + 1])
                    i += 2
                elif token == "STREAMS":
                    stream = decoded[i + 1]
                    i += 2
                else:
                    i += 1
            result = STORE.xreadgroup(group, consumer, stream, count, block)
            return [
                [entry_stream, [[entry_id, self._flat(fields)] for entry_id, fields in entries]]
                for entry_stream, entries in result
            ]
        if name == "XACK":
            return STORE.xack(decoded[0], decoded[1], decoded[2])
        raise RedisError(f"ERR unknown command '{name}'")

    @staticmethod
    def _flat(fields: dict[str, str]) -> list[str]:
        flat: list[str] = []
        for key, value in fields.items():
            flat.extend([key, value])
        return flat


class SimpleString:
    def __init__(self, text: str) -> None:
        self.text = text


class ErrorString:
    def __init__(self, text: str) -> None:
        self.text = text if text.startswith(("ERR", "BUSYGROUP", "NOGROUP", "WRONGTYPE")) else f"ERR {text}"


QUIT = object()


class RedisTCPServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


def main() -> None:
    parser = argparse.ArgumentParser(description="Minimal Redis-compatible server for CORTEX verification")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=6379)
    args = parser.parse_args()

    with RedisTCPServer((args.host, args.port), RespHandler) as server:
        logger.info("dev Redis listening on %s:%d (development double — not for production)", args.host, args.port)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            logger.info("shutting down")


if __name__ == "__main__":
    main()
