# Writing guide

How to write the postmortem so it is blameless, useful, and actually read.

## Blameless language

- Describe systems and conditions, not individuals. Replace a person's name with their role or the system they operated, for example "the deploy pipeline applied the change" rather than a name.
- Assume good faith. Everyone acted reasonably with the information and tools they had at the time. If a person made a choice that looks wrong in hindsight, the interesting question is why it looked right then, and what made the wrong choice easy.
- Aim at the system. For every "someone did X", ask what allowed X to have that effect, and what would make it impossible or obvious next time. That answer is the action item.

## Separate the trigger from the weakness

- The trigger is what set the incident off, for example a specific change or a traffic spike.
- The underlying weakness is why the trigger had that effect, for example a missing guardrail, a single point of failure, or a gap in alerting.
- Fixing only the trigger prevents this exact incident. Fixing the weakness prevents a class of incidents. Weight action items towards the weakness.

## Good action items

- Specific: a clear, verifiable change, not "improve monitoring".
- Owned: a named team or role accountable for it.
- Dated: a realistic due date.
- Balanced across Prevent, Detect, and Mitigate. If every item is Prevent, you have not improved how fast the next one is caught or contained.
- Tracked outside the document, so it does not die when the postmortem is filed.

## Honesty about the unknown

- If the root cause is not fully understood, say so plainly and make the investigation an action item with an owner and a date. A confident wrong root cause is worse than an honest open question.
- Put near misses in the got lucky list. They are the cheapest lessons available, because they cost nothing this time.

## Tone

- Neutral and factual. No blame, and also no minimising. The point is to learn, which needs an honest account of what happened and what it cost.
