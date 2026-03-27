---
name: review-dirty
description: Review dirty code changes. When user say to "review"
  or "review changes" or "review dirty code"
---

All dirty repo changes are likely made in this session,
though not always

if you are Codex, just review the dirty code and ignore the
rest in this skill. If you are not Codex, continue:

Do not modify anything unless I tell you to. Run this cli
command (using codex as our reviewer) passing in the original
prompt to review the changes: `codex exec "Do not modify
anything unless I tell you to. Review the dirty repo changes
which are to implement: <prompt>"`. $ARGUMENTS. Do it with
Bash tool. Make sure if there's a timeout to be at least 10
minutes.