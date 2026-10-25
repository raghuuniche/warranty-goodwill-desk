# Exercises

The plumbing is done. These are the parts that teach you something, roughly
in the order you should do them. Each one names the concept it is drilling.

## 1. Make it run, then break it on purpose (15 min)

Run `python run_cli.py CLM-1003`. It should deny a cabin air filter cheaply.

Now set `MAX_REVISIONS = 99` in `src/config.py` and run `CLM-1002`. Watch
what happens to the event feed and the cost number.

**Concept.** An unbounded disagreement between two agents is the standard way
agent systems generate surprise bills. The loop cap is not a nicety. Put it
back to 3.

## 2. Fix the policy prompt (25 min)

`CLM-1002` contains a customer threatening legal action. Rule G-03 says tone
and pressure must never influence a decision. The policy prompt currently
does not mention this.

Run it as is. Then add the instruction. Compare the two rationales.

**Concept.** Grounding is not the same as compliance. Giving an agent the
rules does not make it follow them. You have to tell it which rules bind its
own reasoning, not just which rules describe the domain. This gap is where
most enterprise agent incidents live.

## 3. Make the reviewer earn its place (30 min)

Right now the reviewer's deterministic checks do the real work and the LLM
half is vague. Pick one judgement the code genuinely cannot make. A good
candidate is whether the rationale actually follows from the rule it cites.
Write that into `REVIEWER_SYSTEM` precisely.

Then try the opposite. Move one of the hard checks out of code and into the
prompt. Run CLM-1002 five times.

**Concept.** You will see the prompt-based check pass sometimes and fail
sometimes. That variance is the argument for putting hard constraints in
code. Keep the result, it is the best paragraph in your write-up.

## 4. Run policy and cost in parallel (20 min)

They do not depend on each other. Replace the supervisor round trip with two
edges fanning out from `intake` and a join before `adjudicator`.

**Concept.** Fan-out and fan-in, and why `events` needed `operator.add`. Two
nodes finishing at once would overwrite each other without the reducer. Watch
the event ordering change.

## 5. Add a second approver level (25 min)

Right now any payout over 500 goes to one human. Add a rule where anything
over 1,200 needs a different approver. Carry an `approver_role` through the
interrupt payload and show it in the UI.

**Concept.** Approval is a policy, not a boolean. Real change control has
levels, and the level is config, not code. This is also the exercise that
turns your project into something you could actually show a client.

## 6. Record who approved (15 min)

The interrupt payload currently has no identity. Add an approver name field
to the UI, store it in state, and print it in the final decision.

**Concept.** An approval with no named human is not an audit trail. Every
governance conversation about agents eventually arrives here.

## 7. Kill switch (15 min)

Add a running cost total to state. In `route_from_reviewer`, if the run has
spent more than a configured ceiling, route to `human_gate` with a budget
reason instead of continuing.

**Concept.** The difference between observing cost and controlling it. In
production this belongs in an LLM gateway that can refuse the call before it
reaches the provider. Doing the crude version here shows you why.

## Stretch, only if you are ahead

- Swap the intake agent to a cheaper model and compare quality and cost.
  Task-tier routing is the biggest cost lever you have.
- Add a second claim running on a different `thread_id` and show both in the
  UI. Concurrency is where single-process agent designs start to hurt.
- Kill the Streamlit process mid-approval and restart it. The thread resumes
  from sqlite. Record that, it demos better than anything else in the project.
