# Desktop safety

Desktop automation with [PlatynUI](https://github.com/imbus/robotframework-PlatynUI) sends real mouse and keyboard
input. Pointed at your own desktop, an agent could click into your e-mail. The harness therefore copies rf-mcp's desktop
guards: its safety, isolation, focus and launch rules.

!!! warning "Off by default in this release"
    Live desktop steps are refused unless `RFH_DESKTOP=1`. The guards pass parity tests against rf-mcp (1,116 recorded
    decisions replay identically), but desktop has not yet been through the live release gate.

## What the guards decide

- **Active-desktop refusal.** Pointer and keyboard input on your active desktop, or on an unknown display, is refused
  by default. Input is allowed on an **isolated** display: an Xvfb, Xephyr or Xorg server you started, declared with
  `RFH_PLATYNUI_ISOLATED_DISPLAY` plus `RFH_PLATYNUI_ISOLATED_XPID`. The harness verifies that the process really owns
  that display.
- **Escape hatches**, all audited:
  - `RFH_PLATYNUI_ALLOW_ACTIVE_DESKTOP=1`;
  - `RFH_PLATYNUI_SAFETY_GUARD=warn`, which warns instead of refusing.
- **Focus before act.** The target window is raised and verified before input, with the process lineage checked
  (`RFH_PLATYNUI_NO_FOCUS=1` disables this).
- **Locator guardrails**:
  - unscoped `//` queries refused (`RFH_PLATYNUI_ALLOW_UNSCOPED`);
  - a file path in the `Take Screenshot` descriptor slot refused (`RFH_PLATYNUI_ALLOW_PATH_DESCRIPTOR`);
  - `control:Window` on Linux refused (`RFH_PLATYNUI_ALLOW_CONTROL_WINDOW`).
- **Launch hardening.** Snap environment sanitization; accessibility and X11 backend pins (`GTK_A11Y=atspi`) for
  launched applications; a one-time Wayland warning (`RFH_PLATYNUI_KEEP_WAYLAND`).

The refusal messages carry rf-mcp's guidance, including a recipe for an isolated display:

```bash
Xvfb :99 -screen 0 1920x1080x24 &
export DISPLAY=:99 RFH_PLATYNUI_ISOLATED_DISPLAY=:99 RFH_PLATYNUI_ISOLATED_XPID=$!
```

## Known differences from rf-mcp

- rf-mcp's guard covers only pointer and keyboard input on the active desktop. Window actions and screenshots pass
  there; the harness keeps that behavior for parity, but its `RFH_DESKTOP` gate covers them today.
- The harness shows all three one-time opt-in warnings. rf-mcp shows only one of them.
- rf-mcp's isolation bootstrap script is not shipped. Use the manual Xvfb/Xephyr steps above.

The full variable list is in the [environment reference](../reference/environment.md). The parity tests are in
`tests/desktop/`. The research's host-dependency map explains why these guards must run on the user's machine and
cannot move into robotcode or a remote service: [capability spikes](../../evidence/rounds/01-capability-spikes/map/).
