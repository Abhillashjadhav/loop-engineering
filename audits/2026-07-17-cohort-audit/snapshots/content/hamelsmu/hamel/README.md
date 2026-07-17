# hamel


## Install

``` sh
pip install hamel
```

All CLI tools below are installed automatically with the package. Use
`<command> --help` to see the full capabilities of each. Example
commands are shown below.

Docs: [hamelsmu.github.io/hamel](https://hamelsmu.github.io/hamel/)

## Available Utilities

### [Gemini](plugins/hamel-tools/skills/gem/SKILL.md) — `ai-gem`

Text generation, PDF/image/video analysis via Google Gemini.

``` sh
ai-gem "Summarize this document" report.pdf
ai-gem "Describe what you see" photo.jpg
ai-gem "What are the key points?" https://youtu.be/VIDEO_ID
ai-gem "Extract all tables" spreadsheet.png -o tables.md
```

### [YouTube](plugins/hamel-tools/skills/youtube/SKILL.md) — `youtube`

Transcripts, AI chapters, uploads, scheduling, downloads.

``` sh
youtube transcribe "https://youtu.be/VIDEO_ID"
youtube transcribe recording.mp4
youtube chapters "https://youtu.be/VIDEO_ID"
youtube upload --file video.mp4 --title "My Video" --privacy private
youtube list
youtube download --id VIDEO_ID
```

### [X / Twitter](plugins/hamel-tools/skills/x/SKILL.md) — `xapi`

Follow tracking, likes, bookmarks, screenshots.

``` sh
xapi resolve HamelHusain
xapi fetch HamelHusain
xapi diff snapshot1.json snapshot2.json --fetch-posts
xapi likes --limit 20
xapi bookmarks -o bookmarks.json
xapi screenshot https://x.com/user/status/123456
```

### [Zoom](plugins/hamel-tools/skills/zoom/SKILL.md) — `zoom`

Download Zoom meeting transcripts.

``` sh
zoom 123456789 -o transcript.vtt
zoom 123456789 | ai-gem "Summarize this meeting"
```

### [Kit](plugins/hamel-tools/skills/kit/SKILL.md) — `kit-broadcasts`

Fetch newsletter broadcasts for writing context.

``` sh
kit-broadcasts -o broadcasts.json
kit-broadcasts --full | jq '.[0:5]'
kit-broadcasts | ai-gem "List the main topics covered"
```

### [Annotate Talk](plugins/hamel-tools/skills/annotate-talk/SKILL.md) — `ai-annotate-talk`

Create blog posts from technical talks with slides.

``` sh
ai-annotate-talk "https://youtu.be/VIDEO_ID" slides.pdf output_images/
ai-annotate-talk "https://youtu.be/VIDEO_ID" slides.pdf out/ --output post.md
```

## AI Agent Skills

These utilities are also available as skills for AI coding agents.
Install the plugin to give your agent access to all the tools above.

### Claude Code

``` sh
claude /plugin install hamel-tools@hamelsmu-hamel
```

Or load directly from a local clone:

``` sh
claude --plugin-dir ./plugins/hamel-tools
```

### Codex CLI

Codex supports the same skill format. Point it at the plugin directory:

``` sh
codex --plugin-dir ./plugins/hamel-tools
```
