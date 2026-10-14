# Windows Python spike (win25-vs2026 / 20260925.250.1)

- WindowsApps exists: True; python aliases: ['python.exe', 'python3.exe']
- App Installer (DesktopAppInstaller): '1.26.510.0'
  - python.exe: isfile=True x=True reparse=True tag=0x8000001b stat_ok=True -> probe rc=9009 0.28s stderr='Python was not found; run without arguments to install from the Microsoft Store, or disable this shortcut from Settings > Apps > Advanced app settings > App exe'
  - python3.exe: isfile=True x=True reparse=True tag=0x8000001b stat_ok=True -> probe rc=9009 0.08s stderr='Python was not found; run without arguments to install from the Microsoft Store, or disable this shortcut from Settings > Apps > Advanced app settings > App exe'
- which (clean PATH): {'python3': 'C:\\Users\\runneradmin\\AppData\\Local\\Microsoft\\WindowsApps\\python3.EXE', 'python': 'C:\\Users\\runneradmin\\AppData\\Local\\Microsoft\\WindowsApps\\python.EXE', 'py': 'C:\\Windows\\py.EXE', 'uv': 'C:\\hostedtoolcache\\windows\\uv\\0.13.1\\x86_64\\uv.EXE', 'uvx': 'C:\\hostedtoolcache\\windows\\uv\\0.13.1\\x86_64\\uvx.EXE'}
- installer repro: rc=1 ['error: C:\\Users\\runneradmin\\AppData\\Local\\Microsoft\\WindowsApps\\python3.EXE did not start']
- UV under uvx: 'UV= C:\\hostedtoolcache\\windows\\uv\\0.13.1\\x86_64\\uv.EXE\nD:\\a\\_temp\\setup-uv-cache\\archive-v0\\VZlDPcQUHw39DJVU\\Scripts\\python.exe'
- which inside uvx: 'python3= C:\\Users\\runneradmin\\AppData\\Local\\Microsoft\\WindowsApps\\python3.EXE\npython= D:\\a\\_temp\\setup-uv-cache\\archive-v0\\VZlDPcQUHw39DJVU\\Scripts\\python.EXE\nprefix= D:\\a\\_temp\\setup-uv-cache\\archive-v0\\VZlDPcQUHw39DJVU\nVIRTUAL_ENV= None'
- synthetic stub probe: rc=9009 ['Python was not found; run without arguments to install from the Microsoft Store, or disable this shortcut from Settings > Apps > Advanced app settings > App execution aliases.']
- installer with synthetic stub on PATH: rc=1 ['error: C:\\Users\\RUNNER~1\\AppData\\Local\\Temp\\rfh-stub-p77d1fs2\\python3.EXE did not start']
- uv python find (default): rc=0 ['C:\\hostedtoolcache\\windows\\Python\\3.14.7\\x64\\python.exe']
- uv python find (only-system): rc=0 ['C:\\hostedtoolcache\\windows\\Python\\3.14.7\\x64\\python.exe']
- uv venv --python 3.12: rc=0 ['Activate with: .venv\\Scripts\\activate']; venv python ok: True
- installer with .venv present: rc=0 ['[dry-run] would write C:\\Users\\runneradmin\\AppData\\Local\\Temp\\rfh-spike-proj-z4h8d6tw\\.rf\\harness.json and add .rf/ to .gitignore']
- hook `python3 -S rfh-launch` (cmd): rc=9009 ['Python was not found; run without arguments to install from the Microsoft Store, or disable this shortcut from Settings > Apps > Advanced app settings > App execution aliases.']
- hook rfh-launch.cmd: rc=0 ['{"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": "[rfh] The Robot Framework harness runtime is not installed in this project\'s Python environment (C:\\\\Users\\\\RUNNER~1\\\\AppData\\\\Local\\\\Temp\\\\rfh-spike-proj-z4h8d6tw\\\\.venv\\\\Scripts\\\\python.exe); the harness hooks are inactive until you run: uvx robotframework-harness install --runtime-only"}}']
- Git Bash: '/c/Users/runneradmin/AppData/Local/Microsoft/WindowsApps/python3\n/c/Users/runneradmin/AppData/Local/Microsoft/WindowsApps/python\n/c/Windows/py\nPATH=/c/Users/runneradmin/bin:/mingw64/bin:/usr/local/bin:/usr/bin:/bin:/mingw64/bin:/usr/bin:/c/Users/runneradmin/bin:/c/Windows/System32:/c/Windows:/c/Wind'
- hook via Git Bash python3: rc=49 ['Python was not found; run without arguments to install from the Microsoft Store, or disable this shortcut from Settings > Apps > Advanced app settings > App execution aliases.']
