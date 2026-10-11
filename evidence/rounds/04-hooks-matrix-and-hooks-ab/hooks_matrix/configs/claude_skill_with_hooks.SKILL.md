---
name: rf-harness
description: Robot Framework harness. ALWAYS use this skill before creating or editing any .robot file.
hooks:
  PostToolUse:
    - matcher: "Write|Edit"
      hooks:
        - type: command
          command: "/usr/bin/python3 ~/workspace/rf-mcp-robotcode/experiments/robotcode-remote/round4/hooks_matrix/bin/hooklog.py --agent claude --event PostToolUse --cell ~/workspace/rf-mcp-robotcode/experiments/robotcode-remote/round4/hooks_matrix/runs/claude/skill --src skill"
  Stop:
    - hooks:
        - type: command
          command: "/usr/bin/python3 ~/workspace/rf-mcp-robotcode/experiments/robotcode-remote/round4/hooks_matrix/bin/hooklog.py --agent claude --event Stop --cell ~/workspace/rf-mcp-robotcode/experiments/robotcode-remote/round4/hooks_matrix/runs/claude/skill --src skill"
---
# RF harness
When writing Robot Framework files, use 4-space separators. After each file write you may receive harness
feedback; follow it.
