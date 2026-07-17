# Writing style rules

This project collects writing style rules from 63 well-known style guides and
writing references, then organizes them into one clean set. The goal is a single
source of style rules you can give to an AI writing assistant so it writes the
way these guides teach.

Right now the set has 814 rules. The rules are sorted into 68 categories, and
those categories are grouped into 15 larger groups. Each rule keeps the list of guides it
came from, a reason it helps the reader, and a short before and after example.

## What is in here

- `writing-rules.json` is the main file. Every other file is built from it. It
  holds the rules sorted into groups and categories, plus a metadata block with
  the counts and the full list of sources.
- `writing-rules.flat.json` is the same rules in one flat list, with each rule
  tagged by its group and category. A program rebuilds this file from
  `writing-rules.json`, so do not edit it by hand.
- `dashboard.html` is a single page you can open in a browser to read and search
  the rules. A program rebuilds this file too.
- `scripts/build.js` reads `writing-rules.json` and rebuilds the flat file and
  the dashboard. Run it after anything changes the main file.
- `workflows/` holds the scripts that built the full set of rules, kept for
  reference. `cluster.js` derived the categories from the rules and assigned
  every rule to one. `dedupe.js` merged rules that said nearly the same thing
  inside each category.
- `.claude/workflows/add-writing-rules.js` is the script that adds new sources
  over time. It searches the web for new guides on its own. The next sections
  explain it.
- `data/` holds the working files from the build. `pool.json` is every rule
  before deduping. `taxonomy.json` is the list of categories with a definition
  of what belongs in each. `assignments.json` records which category each pooled
  rule went to. `shards/` and `clusters/` are the files the pool was split into
  for the build scripts to read.
- `sources/` tracks the guides. `mined-sources.json` lists every guide already
  read. `queue/` is where you drop a new guide to add. `processed/` is where the
  add step files a guide once it is done.
- `docs/` holds reference material. `workflow-library.md` explains the small set
  of functions a workflow script can use. `dashboard-template.html` is the page
  page that `build.js` fills with the rule data.

## How to read the rules

Open `dashboard.html` in any browser. No server or build step is needed. You can
browse by group, open a category, and search the rule text. Each rule shows its
reason, its before and after example, and the guides it came from.

To work with the rules in code, read `writing-rules.flat.json`. It is one array,
and every rule has these fields: `id`, `rule`, `applies_to`, `rationale`,
`example_violation`, `example_fixed`, `sources`, `group`, and `category`.

## How it was built

The build had three steps.

First, an extraction step read each guide and pulled out its concrete style
rules. This produced the pool in `data/pool.json`.

Second, a clustering step read the whole pool and built the categories up from
the rules themselves, rather than starting from a fixed list. It then assigned
every rule to one category. The `workflows/cluster.js` script ran this step.

Third, a dedupe step went category by category and merged rules that said the
same thing, joining their source lists into one. The `workflows/dedupe.js`
script ran this step. The merged result became `writing-rules.json`.

Each step is a workflow. A workflow is a plain JavaScript script that the Claude
Code runtime runs in the background. The script does no work itself. It starts
many small AI agents, hands each one a part of the data, and collects what they
return. See `docs/workflow-library.md` for the functions a workflow can use.

## How to add more sources

The add step finds new guides on its own, so you do not have to supply them. In
Claude Code, ask it to run the `add-writing-rules` workflow. The step then does
this:

1. It searches the web for reputable writing guides that the corpus does not use
   yet. It checks each candidate against the list in `sources/mined-sources.json`
   and picks up to four new ones per run. Reading `MAX_WEB_SOURCES` in the
   workflow file lets you change that cap.
2. It also reads any file you dropped in `sources/queue/`, so you can still add a
   guide by hand. A queue file can be the full text of a guide, your notes about
   it, or a short file that names the guide and gives a link.
3. For each source, it pulls out the style rules and fits each rule into the
   closest existing category. It compares every new rule to the rules already in
   that category. If a rule already says the same thing, the step adds the new
   guide to that rule's source list instead of adding a duplicate. Otherwise it
   adds the rule as a new entry.
4. It then rebuilds the flat file and the dashboard, records each new guide in
   `sources/mined-sources.json`, and moves any queue file from `queue/` to
   `processed/`.

The add step fits new rules into the categories that already exist. It does not
create new categories. If the corpus grows onto a new topic and you want fresh
categories to form, run the full build again with `workflows/cluster.js` and
`workflows/dedupe.js`.

## The recurring job

You can run the add step on a schedule, so the corpus keeps growing without you
running it by hand. Each run searches the web for new guides, so it adds rules
even when you have not dropped anything in `sources/queue/`. When it finds no new
sources, the run does nothing and stops. There are two ways to schedule it.

The first way is to ask Claude Code to schedule the `add-writing-rules` workflow,
e.g., once a day. This is quick to set up. It has one limit. A scheduled job
inside Claude Code lives for 7 days and runs only while Claude Code is open, then
it stops on its own. To keep it going, schedule it again after a week.

The second way runs without Claude Code open and does not expire, so it is the
better choice for the long run. The file `scripts/add-from-queue.sh` checks the
queue, runs the workflow through the Claude Code command line, and commits and
pushes any changes. Add it to your crontab to run it every day. Run `crontab -e`
and add this line:

```
17 9 * * * /Users/shreyashankar/Documents/projects/mine-writing-rules/scripts/add-from-queue.sh >> /tmp/add-writing-rules.log 2>&1
```

This runs the script every day at 9:17 in the morning. It needs the Claude Code
command line installed and logged in for the user whose crontab you edit.

## Rebuilding the outputs

If you edit `writing-rules.json` by hand, rebuild the derived files so they
match:

```
node scripts/build.js
```

This rewrites `writing-rules.flat.json` and `dashboard.html`, and it recounts the
rules, groups, and categories in the metadata.
