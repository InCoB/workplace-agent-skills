# workplace-agent-skills

Agent skills for the tools teams use every day, like Confluence. Each one tested on real pages, in Claude and Cursor, before release.

## Skills

| Skill | Version | What it does |
| --- | --- | --- |
| [confluence-page-update](#confluence-page-update) | 1.00 | Edits one line, cell or table row of a Confluence page, instead of sending the whole page back. |

## confluence-page-update

Your AI agent can change one line, one cell or one table row of a Confluence page. The guide that Atlassian's connector gives the agent only shows how to rewrite the whole page. On a big page that breaks, and you can't put it on autopilot. This skill teaches the agent the small, safe edit.

**Tested in:** Claude and Cursor, with Atlassian's v2 connector (Rovo MCP). Other agents that use the same connector will most likely work the same way.

### What it does

- Edits by line, cell or table row: replace a line or a cell, add or delete table rows, append at the end.
- Dry run first, then reads the page back and reports anything that changed beyond the edit, with steps to undo it.
- If someone edited the page in the meantime, Confluence refuses the update instead of overwriting their work.
- Checks the page's hidden draft before writing, and fixes it if a write damaged it.
- A small Python script reads the saved page for the agent, so the agent reads under 1% of a large page. Standard library only, no network, writes nothing.
- Also covers renaming and moving pages, and Confluence databases.

### Install: no technical skills needed

1. Download [`confluence-page-update-1.00.zip`](https://github.com/InCoB/workplace-agent-skills/releases/download/v1.00/confluence-page-update-1.00.zip).
2. Give the zip to Claude or Cursor and ask:

   > Check this skill for security. If it is safe, install it for me.

3. If your agent can't install it, do it yourself:
   - **Claude app:** go to Customize > Skills, click **+**, choose **Create skill**, then **Upload a skill**, and pick the zip.
   - **Claude Code:** unzip it into `~/.claude/skills/`.
   - **Cursor:** unzip it into `~/.cursor/skills/`.

### Install: for developers

One command, for Claude Code, Cursor and other agents (needs Node.js):

```bash
npx skills add InCoB/workplace-agent-skills --skill confluence-page-update
```

Or as a Claude Code plugin:

```text
/plugin marketplace add InCoB/workplace-agent-skills
/plugin install confluence-page-update@workplace-agent-skills
```

### What you need

- Atlassian's v2 connector (`https://mcp.atlassian.com/v2/mcp`), on Confluence Cloud. If your agent only has `getConfluencePage` and `updateConfluencePage`, that is the older connector, and the skill will stop and tell you.
- `python3` where your agent runs commands, on Mac or Linux.

### Before you use it on a real page

Try it on a copy first: the skill shows how to copy a page and archive the copy afterwards. It never uses `moveNode`: in tests it put a table row outside its table, and the dry run still passed it.

### Known limits

Atlassian's connector can change more than the edit itself. Two open bugs report that any write can affect the whole page:

- [#269](https://github.com/atlassian/atlassian-mcp-server/issues/269): left-aligned and centred tables lose their layout, and non-breaking spaces become plain spaces.
- [#270](https://github.com/atlassian/atlassian-mcp-server/issues/270): fragment links can change on a large page.

The skill checks for these before the first write and asks you first. If a write still changes too much, it tells you, and you can restore the old version from the page's version history.

## License

[MIT](LICENSE). Not affiliated with Atlassian.
