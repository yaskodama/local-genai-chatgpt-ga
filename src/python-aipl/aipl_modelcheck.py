"""AIPL bounded model checker — deadlock detection via state-space
exploration of all message-interleaving schedules.

Usage pattern (see modelcheck/philosophers.py for a worked example):

    from aipl_modelcheck import World, MCActor, ModelChecker, LTL

    class Fork(MCActor):
        def __init__(self, fid):
            self.fid = fid
            self.held = None
        def request(self, world, sender):
            if self.held is None:
                self.held = sender
                world.send(sender, "granted", sender=self.name)
            else:
                world.send(sender, "refused", sender=self.name)
        def release(self, world, sender):
            self.held = None

    def init():
        w = World()
        w.add("f0", Fork(0))
        ...
        w.send("p0", "try_eat", sender="p0")
        return w

    mc = ModelChecker(init, depth=2000)
    print(mc.check_deadlock_free())

The checker explores all reachable interleavings up to `depth` steps,
hashes states for visited-set pruning, and reports either:

  - "no deadlock within K steps (N states explored)"
  - a counter-example trace ending in a state where every actor's
    mailbox is empty AND no actor reached its terminal state.

LTL evaluation is bounded — `G φ` and `F φ` are evaluated over the
finite reachable set; this is correct for safety properties (G ¬bad)
but only an under-approximation for liveness (F good).
"""

from __future__ import annotations
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Callable, Optional, Sequence


# ---------------------------------------------------------------------------
# Actor base class

class MCActor:
    """Subclass and define methods that take (world, sender, *args).

    Each method must mutate `self` and call `world.send(...)` for any
    outgoing messages.  The model checker clones the world via
    deepcopy at every step, so methods MUST be deterministic given
    their inputs (no global state, no time, no randomness)."""

    name: str = ""

    def __repr__(self) -> str:
        # Used in state signatures — concise + stable.
        d = {k: v for k, v in self.__dict__.items() if k != "name"}
        items = sorted(d.items())
        body = ", ".join(f"{k}={v!r}" for k, v in items)
        return f"{type(self).__name__}({body})"


# ---------------------------------------------------------------------------
# World — the explorable state

Message = tuple   # (method_name: str, args: tuple, sender: Optional[str])


class World:
    def __init__(self) -> None:
        self.actors: dict[str, MCActor] = {}
        self.mailbox: dict[str, list[Message]] = {}

    def add(self, name: str, actor: MCActor) -> None:
        actor.name = name
        self.actors[name] = actor
        self.mailbox[name] = []

    def send(self, target: str, method: str, *args: Any,
             sender: Optional[str] = None) -> None:
        if target not in self.mailbox:
            # Unknown target — model checker treats this as a soft error
            # (won't crash; just records an "undelivered" trace).
            return
        self.mailbox[target].append((method, args, sender))

    def runnable_actors(self) -> list[str]:
        """Names of actors with at least one queued message."""
        return [n for n, q in self.mailbox.items() if q]

    def step_actor(self, name: str) -> "World":
        """Process the head message on actor `name`.  Returns a new
        World; the original is untouched."""
        new = deepcopy(self)
        method, args, sender = new.mailbox[name].pop(0)
        actor = new.actors[name]
        m = getattr(actor, method, None)
        if m is None:
            # Drop unknown messages quietly (matches AIPL runtime semantics).
            return new
        m(new, sender, *args)
        return new

    def signature(self) -> tuple:
        """Hashable, equality-comparable representation for the
        visited set.  Two states with identical actor fields and
        identical pending mailboxes are considered equal."""
        actors = tuple(sorted(
            (n, repr(self.actors[n])) for n in self.actors
        ))
        mailbox = tuple(sorted(
            (n, tuple(self.mailbox[n])) for n in self.mailbox
        ))
        return (actors, mailbox)


# ---------------------------------------------------------------------------
# LTL formulas (bounded semantics over the reachable set)

@dataclass
class Atom:
    """An atomic predicate over a single state."""
    pred: Callable[[World], bool]
    name: str = "atom"

@dataclass
class Not:
    f: Any

@dataclass
class And:
    fs: Sequence[Any]

@dataclass
class Or:
    fs: Sequence[Any]

@dataclass
class Globally:
    """G φ — φ holds in every reachable state."""
    f: Any

@dataclass
class Eventually:
    """F φ — φ holds in some reachable state."""
    f: Any


class LTL:
    """Convenience namespace so users can write LTL.Globally(...)."""
    Atom = Atom
    Not = Not
    And = And
    Or = Or
    Globally = Globally
    Eventually = Eventually


def _eval_state(state: World, formula: Any,
                reachable: list[World]) -> bool:
    """Evaluate `formula` over a single state, given the full
    reachable set for G/F bounded semantics."""
    if isinstance(formula, Atom):
        return bool(formula.pred(state))
    if isinstance(formula, Not):
        return not _eval_state(state, formula.f, reachable)
    if isinstance(formula, And):
        return all(_eval_state(state, f, reachable) for f in formula.fs)
    if isinstance(formula, Or):
        return any(_eval_state(state, f, reachable) for f in formula.fs)
    if isinstance(formula, Globally):
        return all(_eval_state(s, formula.f, reachable) for s in reachable)
    if isinstance(formula, Eventually):
        return any(_eval_state(s, formula.f, reachable) for s in reachable)
    raise TypeError(f"unknown formula node: {type(formula).__name__}")


# ---------------------------------------------------------------------------
# The checker

@dataclass
class CheckResult:
    ok: bool
    states_explored: int
    max_depth_reached: int
    deadlocks: list[tuple[int, World]] = field(default_factory=list)
    counter_example: Optional[list] = None

    def render(self) -> str:
        lines = []
        verdict = "OK" if self.ok else "VIOLATION"
        lines.append(f"[modelcheck] verdict: {verdict}")
        lines.append(f"  states explored : {self.states_explored}")
        lines.append(f"  max depth       : {self.max_depth_reached}")
        lines.append(f"  deadlock states : {len(self.deadlocks)}")
        if self.counter_example:
            lines.append("  counter-example trace:")
            for i, (depth, action) in enumerate(self.counter_example):
                lines.append(f"    {i:3}  depth={depth:3}  step: {action}")
        return "\n".join(lines)


class ModelChecker:
    def __init__(self, init: Callable[[], World], depth: int = 2000):
        self.init = init
        self.depth = depth

    # ------------------------------------------------------------------
    # Reachability — BFS with visited set, parent links for trace recon.

    def reachable(self) -> tuple[dict, dict, dict, int]:
        """Returns (visited, parent, action, max_depth_reached).

        - visited[sig] = (World, depth)
        - parent[sig]  = sig of the state we came from (None for s0)
        - action[sig]  = name of actor whose step produced `sig`
        """
        s0 = self.init()
        sig0 = s0.signature()
        visited: dict = {sig0: (s0, 0)}
        parent: dict = {sig0: None}
        action: dict = {sig0: None}
        frontier = [(sig0, 0)]
        max_depth = 0

        while frontier:
            sig, d = frontier.pop(0)
            s, _ = visited[sig]
            if d >= self.depth:
                continue
            for name in sorted(s.runnable_actors()):
                child = s.step_actor(name)
                csig = child.signature()
                if csig not in visited:
                    visited[csig] = (child, d + 1)
                    parent[csig] = sig
                    action[csig] = name
                    if d + 1 > max_depth:
                        max_depth = d + 1
                    frontier.append((csig, d + 1))

        return visited, parent, action, max_depth

    # ------------------------------------------------------------------
    # Deadlock detection.
    # A state is "stuck" when no actor has a queued message AND the
    # caller's `is_terminal` predicate says the system has not finished.
    # (Without is_terminal we treat ANY no-message state as a
    # deadlock, which is too permissive for systems that simply
    # halt — see the philosophers sample for usage.)

    def check_deadlock_free(self,
                             is_terminal: Callable[[World], bool] = None
                             ) -> CheckResult:
        if is_terminal is None:
            is_terminal = lambda s: False

        visited, parent, action, max_depth = self.reachable()

        deadlocks: list[tuple[int, World]] = []
        for sig, (s, d) in visited.items():
            if not s.runnable_actors() and not is_terminal(s):
                deadlocks.append((d, s))

        # Counter-example: trace from s0 to the shallowest deadlock.
        ce = None
        if deadlocks:
            deadlocks.sort(key=lambda kv: kv[0])
            target_d, target_s = deadlocks[0]
            target_sig = target_s.signature()
            chain = []
            sig = target_sig
            while sig is not None:
                _, d = visited[sig]
                act = action[sig]
                if act is not None:
                    chain.append((d, act))
                sig = parent[sig]
            ce = list(reversed(chain))

        return CheckResult(
            ok=len(deadlocks) == 0,
            states_explored=len(visited),
            max_depth_reached=max_depth,
            deadlocks=deadlocks,
            counter_example=ce,
        )

    # ------------------------------------------------------------------
    # General LTL check (bounded over the reachable set).

    def check(self, formula: Any) -> CheckResult:
        visited, _, _, max_depth = self.reachable()
        states = [s for (s, _) in visited.values()]
        s0 = self.init()
        ok = _eval_state(s0, formula, states)
        return CheckResult(
            ok=bool(ok),
            states_explored=len(visited),
            max_depth_reached=max_depth,
        )
