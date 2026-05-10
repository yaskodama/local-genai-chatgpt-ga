---- MODULE Philosophers5Ordered ----
EXTENDS Integers, Sequences, FiniteSets, TLC

\* Actor instance sets (constants from the .abcl)
ForkSet == {"f0", "f1", "f2", "f3", "f4"}
PhilSet == {"p0", "p1", "p2", "p3", "p4"}
Actors == ForkSet \union PhilSet

VARIABLES forks, phils, mailboxes
vars == <<forks, phils, mailboxes>>

\* ===== Per-method actions =====

\* Fork.request
Fork_request(self, sender) ==
  IF (forks[self].held = 0)
  THEN (forks' = [forks EXCEPT ![self].held = 1]) /\ (UNCHANGED <<phils>>) /\ (mailboxes' = [mailboxes EXCEPT ![self] = Tail(mailboxes[self]), ![sender] = Append(mailboxes[sender], [meth |-> "granted", sender |-> self, args |-> <<>>])])
  ELSE (forks' = [forks EXCEPT ![self].queue = Append(@, sender)]) /\ (UNCHANGED <<phils>>) /\ (mailboxes' = [mailboxes EXCEPT ![self] = Tail(mailboxes[self])])

\* Fork.release
Fork_release(self, sender) ==
  IF (forks[self].qstart < Len(forks[self].queue))
  THEN (forks' = [forks EXCEPT ![self].qstart = (forks[self].qstart + 1)]) /\ (UNCHANGED <<phils>>) /\ (mailboxes' = [mailboxes EXCEPT ![self] = Tail(mailboxes[self]), ![((forks[self].queue)[forks[self].qstart + 1])] = Append(mailboxes[((forks[self].queue)[forks[self].qstart + 1])], [meth |-> "granted", sender |-> self, args |-> <<>>])])
  ELSE (forks' = [forks EXCEPT ![self].held = 0]) /\ (UNCHANGED <<phils>>) /\ (mailboxes' = [mailboxes EXCEPT ![self] = Tail(mailboxes[self])])

\* Phil.init
Phil_init(self, sender, lo_fork, hi_fork, m) ==
  (phils' = [phils EXCEPT ![self].lo = lo_fork, ![self].hi = hi_fork, ![self].meals = m]) /\ (UNCHANGED <<forks>>) /\ (mailboxes' = [mailboxes EXCEPT ![self] = Append(Tail(mailboxes[self]), [meth |-> "try_eat", sender |-> self, args |-> <<>>])])

\* Phil.try_eat
Phil_try_eat(self, sender) ==
  IF (phils[self].meals <= 0)
  THEN (phils' = [phils EXCEPT ![self].done = 1]) /\ (UNCHANGED <<forks>>) /\ (mailboxes' = [mailboxes EXCEPT ![self] = Tail(mailboxes[self])])
  ELSE (phils' = [phils EXCEPT ![self].got_lo = 0]) /\ (UNCHANGED <<forks>>) /\ (mailboxes' = [mailboxes EXCEPT ![self] = Tail(mailboxes[self]), ![phils[self].lo] = Append(mailboxes[phils[self].lo], [meth |-> "request", sender |-> self, args |-> <<>>])])

\* Phil.granted
Phil_granted(self, sender) ==
  IF (phils[self].got_lo = 0)
  THEN (phils' = [phils EXCEPT ![self].got_lo = 1]) /\ (UNCHANGED <<forks>>) /\ (mailboxes' = [mailboxes EXCEPT ![self] = Tail(mailboxes[self]), ![phils[self].hi] = Append(mailboxes[phils[self].hi], [meth |-> "request", sender |-> self, args |-> <<>>])])
  ELSE IF (phils[self].meals > 0)
  THEN (phils' = [phils EXCEPT ![self].meals = (phils[self].meals - 1), ![self].got_lo = 0]) /\ (UNCHANGED <<forks>>) /\ (mailboxes' = [mailboxes EXCEPT ![self] = Append(Tail(mailboxes[self]), [meth |-> "try_eat", sender |-> self, args |-> <<>>]), ![phils[self].lo] = Append(mailboxes[phils[self].lo], [meth |-> "release", sender |-> self, args |-> <<>>]), ![phils[self].hi] = Append(mailboxes[phils[self].hi], [meth |-> "release", sender |-> self, args |-> <<>>])])
  ELSE (phils' = [phils EXCEPT ![self].meals = (phils[self].meals - 1), ![self].got_lo = 0, ![self].done = 1]) /\ (UNCHANGED <<forks>>) /\ (mailboxes' = [mailboxes EXCEPT ![self] = Tail(mailboxes[self]), ![phils[self].lo] = Append(mailboxes[phils[self].lo], [meth |-> "release", sender |-> self, args |-> <<>>]), ![phils[self].hi] = Append(mailboxes[phils[self].hi], [meth |-> "release", sender |-> self, args |-> <<>>])])


\* ===== Step / Next =====

StepActor(a) ==
  /\ Len(mailboxes[a]) > 0
  /\ LET msg == Head(mailboxes[a])
     IN ( \/ FALSE
       \/ ( a \in ForkSet /\ msg.meth = "request"
            /\ Fork_request(a, msg.sender) )
       \/ ( a \in ForkSet /\ msg.meth = "release"
            /\ Fork_release(a, msg.sender) )
       \/ ( a \in PhilSet /\ msg.meth = "init" /\ Len(msg.args) = 3
            /\ LET lo_fork == msg.args[1]
             hi_fork == msg.args[2]
             m == msg.args[3]
               IN  Phil_init(a, msg.sender, lo_fork, hi_fork, m) )
       \/ ( a \in PhilSet /\ msg.meth = "try_eat"
            /\ Phil_try_eat(a, msg.sender) )
       \/ ( a \in PhilSet /\ msg.meth = "granted"
            /\ Phil_granted(a, msg.sender) )
        )

Next == \E a \in Actors : StepActor(a)

\* ===== Initial state =====

Init ==
  /\ forks = [a \in ForkSet |-> [held |-> 0, queue |-> <<>>, qstart |-> 0]] /\ phils = [a \in PhilSet |-> [lo |-> "", hi |-> "", meals |-> 0, got_lo |-> 0, done |-> 0]]
  /\ mailboxes = ("p0" :> <<[meth |-> "init", sender |-> "__main__", args |-> <<"f0", "f1", 1>>]>> @@ "p1" :> <<[meth |-> "init", sender |-> "__main__", args |-> <<"f1", "f2", 1>>]>> @@ "p2" :> <<[meth |-> "init", sender |-> "__main__", args |-> <<"f2", "f3", 1>>]>> @@ "p3" :> <<[meth |-> "init", sender |-> "__main__", args |-> <<"f3", "f4", 1>>]>> @@ "p4" :> <<[meth |-> "init", sender |-> "__main__", args |-> <<"f0", "f4", 1>>]>>) @@ [a \in Actors |-> <<>>]

Spec == Init /\ [][Next]_vars

\* ===== Properties =====

\* Some Phil's done flag is 0 — used by NoDeadlock to distinguish
\* normal halt from a true stuck state.  Adapt this predicate per
\* program.
HasUnfinishedPhil == \E p \in PhilSet : phils[p].done = 0

NoDeadlock ==
  ~ ((\A a \in Actors : Len(mailboxes[a]) = 0) /\ HasUnfinishedPhil)

====
