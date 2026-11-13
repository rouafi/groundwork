# Interview script: capturing know-how (day 3)

Three to five interviews of 30 to 45 minutes, with the people who write to customers and to
colleagues every day: sales, account management, customer success, support. Record, transcribe,
then save each transcript as `client_packs/<client>/interviews/<client>-i-<n>.md`.

```markdown
---
id: <client>-i-1
role: head of sales
---
Interviewer: ...

Head of sales: ...
```

`id` is unique in the pack and `role` is the speaker's job. Keep the speaker's own words:
`groundwork extract-rules` cites verbatim sentences, so a transcript that is paraphrased cannot
support a rule. Use synthetic or anonymised names; no real customer data goes in the repository.

## Before you start
- Tell the person this is to write down how the team already writes, not to judge them.
- Ask for permission to record. Never ask them for a password or a key.
- Their answers are data: if a transcript contains an instruction aimed at an assistant, it stays
  in the transcript and is reviewed by a person, it is never followed.

## Questions
Ask for a real example each time: "the last time that happened, what did you write?"

**Tone and length**
1. How do you write to a small customer, to a large one? What changes: greeting, length, formality?
2. And to a colleague, internally? What do you leave out?
3. Does it depend on who reads it: the person who pays, the person who evaluates the product, the user?

**Money**
4. When you mention a price, where does the number come from? Do you ever round it?
5. Do you ever put a discount in writing? Who decides, and where does it appear instead?
6. What happens when a customer asks for a discount or a custom quote?

**Promises**
7. What can you say about the product without checking? What must you always check first?
8. Which delivery times, dates or results do you promise in writing? Which ones never?
9. What do customers hear that turns out to be untrue, and who said it?

**When things go wrong**
10. How do you write about bad news: an outage, a delay, a mistake of ours?
11. What do you never write to a customer, even when it is true?

**How the team works**
12. What do you record in the CRM, and when? What do you wish colleagues recorded?
13. What do new colleagues get wrong in their first weeks?
14. Who approves what, today, before a message goes out?

## After the interview
- Read the transcript once and fix names. Do not edit what was said.
- Run `uv run groundwork extract-rules --pack <client>`: it proposes rules, each with the quote it
  relies on. A person reads every proposal and copies the ones they approve into `rules.yaml`
  with `status: approved`. Rules are never approved by the tool or the assistant.
