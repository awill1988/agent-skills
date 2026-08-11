# `--urgent` — and the question it must ask first

Urgency is a claim about consequence, and a claim nobody can check is one a
channel learns to discount. This flag does not change the volume; it adds a
**reason**, and the reason has to come from the person invoking it.

## Ask before writing

Use `AskUserQuestion` with concrete candidates rather than a blank prompt — a
deploy window, a dependent team blocked, a customer or incident commitment, a
release cut, an expiring credential or environment. Ask for the *date or time*
and *what happens if it slips*.

**If no deadline comes back, do not escalate.** Say plainly that there is
nothing to escalate on and offer the normal digest. An urgent framing with no
named consequence is what makes the next real one ignorable — refusing it here
is the whole value of the flag.

## The shape, once a deadline exists

```
⏳ *<ticket key>* — needs review before <deadline>

<one clause: what it unblocks and what slips if it does not land>

The ask is *<repo>#<n>* only — <line item>, +<add>/-<del>.
The rest of the stack can wait.
<url>

If you can't get to it before <deadline>, tell me and I'll find another
reviewer rather than let it sit.
```

### Worked example

Sixty-two authored words against the 80-word budget:

```
⏳ *PROJ-412* — needs review before Thursday 16:00

The staging window closes Thursday and this is the last change that has to be
in it; missing it pushes the rollout a week.

The ask is *acme/platform#1456* only — the gateway and the api start sharing
one principal, +2886/-425. The rest of the stack can wait.
https://github.com/acme/platform/pull/1456

If you can't get to it before Thursday, tell me and I'll find another reviewer
rather than let it sit.
```

## Rules that survive the flag

- **The deadline is stated once, as a fact, without adjectives.** No "ASAP", no
  "urgent" in the body, no bold on the time. The date is the pressure.
- **Still name the smallest unit.** Urgency narrows the ask; it never widens it
  into "please review all five".
- **Still offer the exit** — more important here, not less, because the reader
  now has a reason to feel cornered.
- **Never invent or soften the consequence.** "The staging window closes at
  16:00" stays that; it does not become "prod is blocked".
- **Own sequencing is a legitimate reason, stated honestly.** "I'd like to land
  this before I start X" reads far better than a manufactured deadline, and is
  true.
- **Urgency does not bypass preflight.** A red PR is still red, and a deadline
  makes shipping a broken ask worse rather than more forgivable.
