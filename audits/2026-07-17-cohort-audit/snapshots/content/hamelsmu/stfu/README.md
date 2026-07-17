# STFU

![STFU social card: Mystery sound? Find the noisy tab or app.](assets/social-card.png)

For the stray video, song, or mystery tab you can hear but cannot find.

- Browser tab making noise: close only that tab.
- Mac app making noise: quit that app, with confirmation.
- Multiple sound sources: close them one at a time or use `STFU Everything`.

## Install

Requires macOS 14 or later.

Download the latest `STFU-*.dmg` from [GitHub Releases](https://github.com/hamelsmu/stfu/releases/latest), open it, and run `Install STFU.pkg`.

The installer adds:

- `/Applications/STFU.app`
- `/usr/local/bin/stfu`

Current release builds are unsigned unless the release notes say otherwise. If macOS blocks the installer, Control-click `Install STFU.pkg`, choose `Open`, and confirm you want to run it.

## Supported Sources

STFU closes individual noisy tabs for:

- Safari
- Google Chrome, Chrome Canary, Microsoft Edge, Brave, Chromium, and Arc

Other audio producers are shown as apps and can be quit from STFU.

## Permissions

Open `STFU.app`. If a browser row says it needs Accessibility, click `Open Settings`, then enable STFU in:

`System Settings > Privacy & Security > Accessibility`

macOS requires that permission so STFU can inspect browser tab strips and close only the noisy tab.

If STFU does not appear in the list, click `Open Settings` from the STFU row again. If STFU already appears enabled but Chrome still asks, toggle STFU off and on once. That can happen after replacing a local unsigned build.

macOS may also ask whether STFU can control Safari, Chrome, or another browser. Allow it; that Automation permission lets STFU identify Safari tabs while scanning and focus or close browser tabs. If you denied Automation, re-enable STFU in:

`System Settings > Privacy & Security > Automation`

Open STFU in that Automation list, enable the affected browser under it, then reopen STFU and click `Refresh`.

You can check the local setup from Terminal:

```sh
stfu --doctor
stfu --request-accessibility
```

## Use

In the app:

- `Go to Tab` / `Go to App`: jump to the noisy source.
- `Close Tab`: close only the noisy browser tab.
- `Quit App`: asks before quitting the noisy app. Unsaved work in that app could be lost.
- `STFU Everything`: asks before closing all noisy tabs and quitting noisy apps.
- `Open Settings`: open the relevant Accessibility or Automation permission page.
- `Refresh`: rescan current audio sources.

In the menu bar:

- Open `STFU.app`.
- Use the STFU menu bar item to see current sound sources.
- Use row icons to jump to a source, close a noisy tab, open permission settings, or confirm quitting a noisy app.
- Use `Open STFU` when you want the full window.

From Terminal:

```sh
stfu --list
stfu --dry-run
stfu
stfu --all
stfu --doctor
stfu --request-accessibility
```

## Development

Build and release documentation lives in [DEVELOPMENT.md](DEVELOPMENT.md).
