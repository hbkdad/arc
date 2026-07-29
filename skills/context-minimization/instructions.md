# Context Minimization

Loading an entire repository, README, or memory history into a task wastes
tokens and dilutes the signal the model actually needs -- a targeted
retrieval beats a comprehensive one almost every time.

1. **State the objective narrowly first.** Before retrieving anything,
   write down exactly what the task needs to know, not everything that
   might be interesting about the surrounding system.

2. **Search before you read.** Use keyword/semantic search (memory search,
   skill search, grep-equivalent) to find candidate files or records before
   opening any of them in full. A search hit tells you *where* to look;
   it isn't a substitute for reading the specific part that matters.

3. **Read the smallest unit that answers the question.** Prefer a single
   function, a single config block, a single memory record over a whole
   file, and a whole file over a whole directory. Expand scope only when
   the narrow read proves insufficient -- don't pre-emptively widen it.

4. **Never retrieve for coverage's sake.** "I read the whole file so I
   wouldn't miss anything" is a sign the search step was skipped, not a
   sign of thoroughness. If ten searches would each answer a different
   sub-question more precisely than one full read, do the ten searches.

5. **Prefer a surgical diff over a full-file rewrite** once a change is
   scoped -- edit exactly the lines that need to change, keep everything
   else byte-identical, and never re-read a file immediately after writing
   it just to confirm the edit landed (the write itself already confirms
   it).

6. **Drop what didn't end up mattering.** If a retrieved file or record
   turned out irrelevant to the final answer, don't carry it forward into
   summaries or follow-up context -- keep the context budget proportional
   to what was actually used, not to what was initially fetched.
