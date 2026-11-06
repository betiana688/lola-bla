# How the Pi, the repo and GitHub connect

```mermaid
%%{init: {"theme":"base","themeVariables":{"primaryColor":"#FFF8E7","primaryTextColor":"#2A1640","primaryBorderColor":"#2A1640","lineColor":"#7B4FC4","textColor":"#7B4FC4","secondaryColor":"#F7D33E","tertiaryColor":"#C9B3F2","noteBkgColor":"#F7D33E","noteTextColor":"#2A1640","noteBorderColor":"#2A1640","actorBkg":"#FFF8E7","actorBorder":"#2A1640","actorTextColor":"#2A1640","actorLineColor":"#7B4FC4","signalColor":"#7B4FC4","signalTextColor":"#7B4FC4","labelBoxBkgColor":"#FFF8E7","labelBoxBorderColor":"#2A1640","labelTextColor":"#2A1640","loopTextColor":"#7B4FC4","edgeLabelBackground":"#FFF8E7","clusterBkg":"#C9B3F2","clusterBorder":"#2A1640","titleColor":"#2A1640"}}}%%
flowchart LR
  subgraph GH["GitHub"]
    direction TB
    G1["betiana688/lola-bla<br/>private - our code"]
    G2["pollen-robotics/<br/>reachy_mini_conversation_app<br/>public - the engine"]
  end
  subgraph PI["The Pi"]
    direction TB
    R["~/lola-bla<br/>OUR REPO - code only"]
    subgraph C["Pollen's clone - the app runs from here"]
      direction TB
      L["our files here are LINKS<br/>pointing into the repo"]
      D["DATA - stays here, never pushed<br/>lola.db, audio/, hf_token"]
    end
  end
  R <-->|"push and pull over SSH<br/>deploy key, this one repo only"| G1
  G2 -->|"install.sh clones the pinned commit<br/>and applies our small patch"| C
  L -.->|"point to"| R
```

- The app runs from Pollen's clone. Our files there are links to the files in this repo, so there is one copy of each.
- Editing a file edits the repo's file. Then commit and push from the repo folder.
- The database, audio and tokens stay in the clone's local_data folder, outside the repo, so they cannot be committed by accident.
- Pollen's engine comes from its public repo at one pinned commit (app/patches/POLLEN_COMMIT) plus our patch. We never push there.
