# Windows Python spike (win22 / 20261004.326.1)

- WindowsApps exists: True; python aliases: []
- App Installer (DesktopAppInstaller): ''
- which (clean PATH): {'python3': None, 'python': None, 'py': 'C:\\Windows\\py.EXE', 'uv': 'C:\\hostedtoolcache\\windows\\uv\\0.13.1\\x86_64\\uv.EXE', 'uvx': 'C:\\hostedtoolcache\\windows\\uv\\0.13.1\\x86_64\\uvx.EXE'}
- installer repro: rc=0 ['Installed 1 package in 10ms']
- UV under uvx: 'UV= C:\\hostedtoolcache\\windows\\uv\\0.13.1\\x86_64\\uv.EXE\nD:\\a\\_temp\\setup-uv-cache\\archive-v0\\y_cJ7bUTOxnpX6M4\\Scripts\\python.exe'
- which inside uvx: 'python3= None\npython= D:\\a\\_temp\\setup-uv-cache\\archive-v0\\y_cJ7bUTOxnpX6M4\\Scripts\\python.EXE\nprefix= D:\\a\\_temp\\setup-uv-cache\\archive-v0\\y_cJ7bUTOxnpX6M4\nVIRTUAL_ENV= None'
- synthetic stub probe: rc=9009 ['Python was not found; run without arguments to install from the Microsoft Store, or disable this shortcut from Settings > Apps > Advanced app settings > App execution aliases.']
- installer with synthetic stub on PATH: rc=1 ['error: C:\\Users\\RUNNER~1\\AppData\\Local\\Temp\\rfh-stub-dnoc5qs2\\python3.EXE did not start']
- uv python find (default): rc=0 ['C:\\hostedtoolcache\\windows\\Python\\3.14.8\\x64\\python.exe']
- uv python find (only-system): rc=0 ['C:\\hostedtoolcache\\windows\\Python\\3.14.8\\x64\\python.exe']
- uv venv --python 3.12: rc=0 ['Activate with: .venv\\Scripts\\activate']; venv python ok: True
- installer with .venv present: rc=0 ['[dry-run] would write C:\\Users\\runneradmin\\AppData\\Local\\Temp\\rfh-spike-proj-jbjj14_o\\.rf\\harness.json and add .rf/ to .gitignore']
- hook `python3 -S rfh-launch` (cmd): rc=1 ['operable program or batch file.']
- hook rfh-launch.cmd: rc=0 ['{"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": "[rfh] The Robot Framework harness runtime is not installed in this project\'s Python environment (C:\\\\Users\\\\RUNNER~1\\\\AppData\\\\Local\\\\Temp\\\\rfh-spike-proj-jbjj14_o\\\\.venv\\\\Scripts\\\\python.exe); the harness hooks are inactive until you run: uvx robotframework-harness install --runtime-only"}}']
- Git Bash: '/c/Windows/py\nPATH=/c/Users/runneradmin/bin:/ucrt64/bin:/usr/local/bin:/usr/bin:/bin:/ucrt64/bin:/usr/bin:/c/Users/runneradmin/bin:/c/Windows/System32:/c/Windows:/c/Windows/System32/Wbem:/c/Windows/System32/WindowsPowerShell/v1.0:/c/Users/runneradmin/AppData/Local/Microsoft/WindowsApps:/c/hostedtool'
- hook via Git Bash python3: rc=127 ['/usr/bin/bash: line 1: python3: command not found']
