# Random Whisker Development

Version `0.1.0`. Runtime mod ID: `RandomWhisker`.

## Runtime

Two Blueprints under `/Game/Mods/RandomWhisker`:

- `BP_MapLoad`: waits for a live session (init phase `DONE`, `ArcoSystems` live, no replay menu), creates the button, mirrors HUD visibility and handles `SpawnOne`.
- `WBP_RandomWhisker`: one button; a click calls `BP_MapLoad.SpawnOne`.

`SpawnOne` checks readiness, ignores repeated clicks within 0.25 s real time and calls
`RwSpawnAtDock(Controller)`. That bridge calls the native
`PlayerController_Play::Arco_SpawnAgentsAtDock(nAgents = 1, education = None)` on the live
player controller. No runtime DLL ships.

## Build

Requirements: compatible Whiskerwood modkit at `..\Modkit`, custom engine at `D:\WWEngine`,
Visual Studio build tools. The modkit's class dump must match the installed game
(`Modkit\Automation\update.bat`).

```powershell
& .\Automation\RandomWhisker\Build-Mod.ps1 -EngineRoot 'D:\WWEngine' -ProjectRoot '..\Modkit'
```

Or double-click `Run-Build.cmd`; output goes to `build-console.log`.

The script copies `Plugins\RandomWhiskerEditor` into the modkit and compiles the editor
target, generates both Blueprints, runs `test_public.py`, prepares an isolated cook chunk,
cooks, lists and verifies the pak. Result:

```text
Modkit\Saved\RandomWhiskerBuilds\<build-id>\Delivery\RandomWhisker\
  RandomWhisker.pak
  RandomWhisker.uplugin
```

Local installation (game closed):

```powershell
& .\Automation\RandomWhisker\Install-Local.ps1 -PackageDirectory '<build>\Delivery\RandomWhisker'
```

## Manual validation

1. New game: button visible below the left-middle edge; hidden in menus.
2. Click: one new Whisker arrives at the dock; population increases by one.
3. Double click: at most one Whisker per 0.25 s.
4. Save, reload, click again.
