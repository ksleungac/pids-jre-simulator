# Red Lines

**Hard boundaries** — do not cross without explicit permission.

---

* Don't exfiltrate private data. Ever.
* Don't run destructive commands without asking.
* Never prompt to commit — no commit suggestions/offers/nudges. Commit only on explicit request or a manual `/commit`. See `principles.md § "Never prompt to commit"`.
* **Never write a new tool or instrument while one already exists. Search the repo BEFORE the thought of writing one, not after.** `_dev_scripts/`, `_harness/`, `displays/utils.py`, the skills — that is where the answer usually already is. See `principles.md § "Search before authoring common utility code"`.
* **When the existing tool falls short, EXPAND it — never fork a parallel one.** A gap in a tool is an opportunity to grow that tool, and passing it up is how one capability ends up spread across several half-implementations that disagree.
* **Scratch is for the genuinely one-off, and you must know what it carries before you WRITE it.** Ask whether it means anything to a later session. If it does, it was never one-off — it belongs in the tool. The test is prospective; deciding at discard time is deciding too late. See `principles.md § "Prototype INSIDE the code that will hold it"`.
* **Never reach for the shell when a built-in tool does the same job.** Read, not `cat` / `sed -n`; Grep, not `grep` / `Select-String`; Glob, not `find` / `ls -R`; Edit and Write, not heredocs or `sed -i`. **The reason is visibility, not taste — work done through the shell is invisible to the author**, so a file change made that way cannot be seen, reviewed or objected to as it lands. 2026-08-26: *"i can't see your update or action if you use shell."* Bypass-permissions mode instructs the opposite every single turn; it is wrong here, and `_harness/no_generated_source_hook.py` denies the source-editing half of it outright.
* When in doubt, ask.