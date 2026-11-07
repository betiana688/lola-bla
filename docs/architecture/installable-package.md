# Installable package (spec)

Status: approved by the author on 2026-11-07. Nothing here is built yet. It turns the gaps in [publishing.md](publishing.md) into a build order. Facts about Pollen's app come from its published README; the points marked "to verify" must be tried on the robot before building on them.

## Goal

One thing a person installs from Reachy Mini Control's app list, which brings everything Lola-Bla needs, with no commands and no patched copy of anyone's code.

## Today and target

| Today | Target |
|---|---|
| Pollen's app: a git clone pinned to one commit, plus a 24-line patch | A modified copy of Pollen's app inside the package: Pollen's code at the pinned commit plus our patch (decision 5) |
| Our tools and Lola's profile are linked into that clone | Kept inside our package and loaded from outside Pollen's code, through the folders Pollen's app supports for external profiles and tools |
| The console is a second package (`lola-console`) that is not published | Bundled in the same package, so there is nothing else to install |
| Data lives inside the clone's `local_data` folder | In its own data folder, chosen by one setting. The robot that runs today keeps its data where it is |
| Set up by `app/install.sh` | The package installs itself. First-run steps (Signal API, linking) start at the console |

## Shape

```mermaid
%%{init: {"theme":"base","themeVariables":{"primaryColor":"#FFF8E7","primaryTextColor":"#2A1640","primaryBorderColor":"#2A1640","lineColor":"#7B4FC4","textColor":"#7B4FC4","secondaryColor":"#F7D33E","tertiaryColor":"#C9B3F2","noteBkgColor":"#F7D33E","noteTextColor":"#2A1640","noteBorderColor":"#2A1640","actorBkg":"#FFF8E7","actorBorder":"#2A1640","actorTextColor":"#2A1640","actorLineColor":"#7B4FC4","signalColor":"#7B4FC4","signalTextColor":"#7B4FC4","labelBoxBkgColor":"#FFF8E7","labelBoxBorderColor":"#2A1640","labelTextColor":"#2A1640","loopTextColor":"#7B4FC4","edgeLabelBackground":"#FFF8E7","clusterBkg":"#C9B3F2","clusterBorder":"#2A1640","titleColor":"#2A1640"}}}%%
flowchart LR
  subgraph S["One package: lola_bla"]
    A["app code (landing page, startup)"]
    C["console (bundled)"]
    P["profile and tools (content folder)"]
  end
  D["Pollen's conversation app (modified copy, pinned commit)"]
  R["Reachy Mini daemon"]
  A -->|"sets the external folders, then runs"| D
  P -->|"loaded from outside Pollen's code"| D
  A -->|"starts and stops"| C
  R -->|"installs, starts, stops"| S
```

## Decisions in the proposal

1. **Bundle the console** in the same distribution (both `lola_bla` and `lola_console` packages, with its templates, fonts and static files). No second package to find.
2. **External content.** Before Pollen's code reads its settings, `LolaBla.run()` sets `REACHY_MINI_EXTERNAL_PROFILES_DIRECTORY` and `REACHY_MINI_EXTERNAL_TOOLS_DIRECTORY` to folders inside our package and `AUTOLOAD_EXTERNAL_TOOLS=1`. To verify: that the version installed on the robot (1.0.1) reads these, and that our tools find the messaging modules that today sit in `local_data`.
3. **Data folder.** One setting, `LOLA_DATA`, with a default outside the package, so removing or updating the app never deletes the database, audio or Signal keys. The existing robot sets it to where its data is today.
4. **The space is a separate repository.** The store installs from a Hugging Face Space, not from this repository. A small script assembles the Space from this repository (package, `index.html`, `style.css`, the README tag) and publishes it with Pollen's assistant, so this repository can stay private. Decided: the Space is private.
5. **Fork.** Lola-Bla needs a two-line change in Pollen's app (it lets a tool mute the microphone), and Pollen has not taken it. Decided: fork. The Space script takes Pollen's code at the pinned commit, applies our patch and bundles the result, so there is no second package to install and no extra repository. Pollen's license (Apache-2.0) is kept and the change is stated in the Space's README. Asking Pollen to accept the change is not a priority; the author will say when they have. If they do, the copy is dropped and the package depends on theirs.

## Build order (each step is tested on its own)

1. **Assemble the Space folder with a script:** both packages, the content folder, the modified copy of Pollen's app, `index.html`, `style.css` and the README tag. Test: Pollen's checker passes; install it into a fresh environment on the robot (not the daemon's) and import every package.
2. **External content:** set the folders in `run()`. Test: Lola's profile is the active one, her tools are found, `sleep_robot` is listed.
3. **Data folder:** `LOLA_DATA` with the safe default. Test: the running robot still uses its current data; a fresh one gets an empty database.
4. **Private release:** publish a private Space, install it from the app list on the robot, start it, stop it.
5. **Removal test:** remove the app, check that the data, the Signal keys and the Signal API are untouched, then install again.
6. **Public release**, only if the author wants it, after a final privacy re-check.

## Open questions

- If a robot already has Pollen's own conversation app installed, does installing Lola-Bla (which carries a modified copy with the same package name) clash with it? To test with the private release.
- Does Pollen's app (the version the store brings) read the external folders the same way as the pinned commit?
- Where does the first-run setup of the Signal API container live for a stranger: a guide, or the console?
