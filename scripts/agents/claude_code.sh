#!/bin/sh
# Claude Code as a HeisenBench agent: headless, file edits auto-accepted, and shell
# access limited to building, testing and inspecting the repository.
# Usage: claude_code.sh <prompt_file>   (run with the checkout as the working directory)
exec claude -p "$(cat "$1")" \
  --permission-mode acceptEdits \
  --max-turns 80 \
  --allowedTools "Read" "Edit" "Write" "Glob" "Grep" \
    "Bash(make:*)" "Bash(python3:*)" "Bash(c++:*)" "Bash(g++:*)" "Bash(./build/*)" \
    "Bash(git diff:*)" "Bash(git status:*)" "Bash(git log:*)" "Bash(ls:*)" \
  --output-format json
