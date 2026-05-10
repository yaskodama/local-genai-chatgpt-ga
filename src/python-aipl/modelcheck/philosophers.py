"""Dining philosophers — modelled for aipl_modelcheck.

Two variants:
  init_naive(N)    — every philosopher requests its own left fork
                     first; classic deadlock-prone version.
  init_ordered(N)  — every philosopher always grabs the lower-id
                     fork first; deadlock-free by construction.

Forks here use a queueing semantics: a request that can't be
satisfied immediately is appended to the fork's wait list.  When the
fork is released, the head of the wait list is granted.  This
matches a real lock and produces the classic deadlock when the
acquisition order is wrong.

Run:
  python3 modelcheck/philosophers.py             # both variants
  python3 modelcheck/philosophers.py --naive
  python3 modelcheck/philosophers.py --ordered
  python3 modelcheck/philosophers.py --N 3
"""

import argparse
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from aipl_modelcheck import World, MCActor, ModelChecker  # noqa: E402


# ---------------------------------------------------------------------------
# Actors

class Fork(MCActor):
    def __init__(self, fid: int):
        self.fid = fid
        self.held: object = None       # None or owner-philosopher name
        self.queue: tuple = ()         # FIFO of waiting philosophers (tuple
                                        # so deepcopy + repr is stable)

    def request(self, world: World, sender: str) -> None:
        if self.held is None:
            self.held = sender
            world.send(sender, "granted", sender=self.name)
        else:
            # Block the requester by queueing it.  No reply yet.
            if sender not in self.queue:
                self.queue = self.queue + (sender,)

    def release(self, world: World, sender: str) -> None:
        if self.held != sender:
            return
        if self.queue:
            next_p, *rest = self.queue
            self.queue = tuple(rest)
            self.held = next_p
            world.send(next_p, "granted", sender=self.name)
        else:
            self.held = None


class Philosopher(MCActor):
    def __init__(self, pid: int, lo_fork: str, hi_fork: str, meals: int):
        self.pid = pid
        self.lo = lo_fork
        self.hi = hi_fork
        self.meals = meals
        self.state = "idle"
        self.got_lo = False

    def try_eat(self, world: World, sender: str) -> None:
        if self.meals <= 0:
            self.state = "done"
            return
        self.state = "hungry"
        self.got_lo = False
        world.send(self.lo, "request", sender=self.name)

    def granted(self, world: World, sender: str) -> None:
        if not self.got_lo:
            self.got_lo = True
            world.send(self.hi, "request", sender=self.name)
        else:
            # both forks acquired -> eat -> release both
            self.state = "eating"
            self.meals -= 1
            self.got_lo = False
            world.send(self.lo, "release", sender=self.name)
            world.send(self.hi, "release", sender=self.name)
            if self.meals > 0:
                world.send(self.name, "try_eat", sender=self.name)
            else:
                self.state = "done"


# ---------------------------------------------------------------------------
# Initial worlds

def init_naive(N: int = 3, meals: int = 1):
    """Naive variant: philosopher i requests fork-i then fork-(i+1)%N.
    For all i simultaneously this is the classic circular wait."""
    def init():
        w = World()
        for i in range(N):
            w.add(f"f{i}", Fork(i))
        for i in range(N):
            left = f"f{i}"
            right = f"f{(i + 1) % N}"
            w.add(f"p{i}", Philosopher(i, left, right, meals=meals))
        for i in range(N):
            w.send(f"p{i}", "try_eat", sender=f"p{i}")
        return w
    return init


def init_ordered(N: int = 3, meals: int = 1):
    """Ordered variant: every philosopher requests min(left,right) first."""
    def init():
        w = World()
        for i in range(N):
            w.add(f"f{i}", Fork(i))
        for i in range(N):
            a, b = i, (i + 1) % N
            lo, hi = min(a, b), max(a, b)
            w.add(f"p{i}", Philosopher(i, f"f{lo}", f"f{hi}", meals=meals))
        for i in range(N):
            w.send(f"p{i}", "try_eat", sender=f"p{i}")
        return w
    return init


# ---------------------------------------------------------------------------
# Termination predicate (system "finished" rather than deadlocked)

def all_done(world: World) -> bool:
    for a in world.actors.values():
        if isinstance(a, Philosopher) and a.state != "done":
            return False
    return True


# ---------------------------------------------------------------------------
# CLI

def run(variant_name: str, init_fn, depth: int) -> int:
    print(f"=== {variant_name} ===")
    mc = ModelChecker(init_fn, depth=depth)
    res = mc.check_deadlock_free(is_terminal=all_done)
    print(res.render())
    return 0 if res.ok else 1


def main():
    ap = argparse.ArgumentParser(description="Model-check the dining philosophers")
    ap.add_argument("--N", type=int, default=3)
    ap.add_argument("--meals", type=int, default=1)
    ap.add_argument("--depth", type=int, default=2000)
    ap.add_argument("--naive", action="store_true")
    ap.add_argument("--ordered", action="store_true")
    args = ap.parse_args()

    do_naive = args.naive or not (args.naive or args.ordered)
    do_ordered = args.ordered or not (args.naive or args.ordered)

    rc_naive = 0
    rc_ordered = 0
    if do_naive:
        rc_naive = run(f"naive N={args.N} meals={args.meals}",
                       init_naive(args.N, args.meals), args.depth)
        print()
    if do_ordered:
        rc_ordered = run(f"ordered N={args.N} meals={args.meals}",
                         init_ordered(args.N, args.meals), args.depth)
    # Naive should fail (deadlock); ordered should succeed.
    # Exit 0 if both findings match expectation, else 1.
    if do_naive and do_ordered:
        sys.exit(0 if (rc_naive == 1 and rc_ordered == 0) else 1)
    sys.exit(rc_naive | rc_ordered)


if __name__ == "__main__":
    main()
