# reverse-eng-site-skill

Turn browser network traffic into a tested client for a website's undocumented API.

## Install

Install globally with [skills](https://github.com/vercel-labs/skills):

```bash
npx skills add hamelsmu/reverse-eng-site-skill -g
```

For a non-interactive Codex install:

```bash
npx skills add hamelsmu/reverse-eng-site-skill -g -a codex -y
```

## Use

```text
Use $reverse-eng-site-skill to discover and validate the internal API for <site>.
```

In Claude Code, replace `$` with `/`.

Start with a signed-in browser session that can capture network requests. The skill uses one UI action to find the request, then stops clicking and moves to direct HTTP. It checks the response against the site before packaging a reusable client or site-specific skill.
