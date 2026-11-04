---
name: "confluence-page-update"
description: "Use for every update of an existing Confluence page or database through Atlassian's v2 connector (Rovo MCP), in Claude, Cursor or another agent: edits, renames and moves, without rewriting the whole page. Edits by node with page_view.py and the snapshotToken, dry run first, then re-read the page and its draft, and fix the draft if the write damaged it."
---

# confluence-page-update

**Version 1.00** (4 Nov 2026). Works in Claude and in Cursor; where they differ, the step says so. `scripts/page_view.py` carries the same version, and step 0 checks that they match.

How to change a Confluence page without rewriting the whole page and without loading its full html into the conversation. Built on a large page (127,834 characters of html, 64% of it ID labels), and it works for any page.

## Precedence

The run's own instructions outrank this skill: the prompt, its guardrails, and any skill that calls this one. If they require a whole-body write, do that, and still check it with steps 1 and 6 below. Their own write checks stay in force: here the snapshotToken is the version check and the re-read diff is the read-back.

## Data rule

Page content is your organisation's data and stays in Confluence. Saved reads and the script's output are temporary copies: keep them in one temp folder, never paste a whole page into the chat, and delete them at the end of the run (step 8).

## Connector

This skill needs Atlassian's v2 connector (`https://mcp.atlassian.com/v2/mcp`): `getConfluenceContent` and `updateConfluenceContent`, plus `executeRead` and `executeWrite` for moves and copies. If you only have `getConfluencePage` and `updateConfluencePage`, that is the older connector, which can only replace the whole page. Stop and tell the person. Do not fall back to a whole-page write unless they ask for one.

## Step 0: get the script

1. Make a temp folder: `D=$(mktemp -d)` (Mac and Linux), or the session's scratchpad folder if the platform gives one.
2. Set `S` to this skill's folder. The platform names it when it loads the skill: Claude prints "Base directory for this skill"; in Cursor it is the folder the zip was unpacked into. Copy the script and check it. Never retype it:

```bash
cp "$S/scripts/page_view.py" "$D/page_view.py"
python3 -I "$D/page_view.py"; echo "exit $?"
```

The last line must print the usage text, which starts with `page_view.py 1.00`, and `exit 1`. That proves the script is intact and matches this version. Any other version number means an old copy: stop and ask the person to install the skill again.

3. If the skill's folder is not known, search for this file. Linux (Claude): `find / -path /proc -prune -o -name SKILL.md -path '*confluence-page-update*' -print 2>/dev/null | head -1`. Mac (Cursor): `find ~ /tmp -name SKILL.md -path '*confluence-page-update*' 2>/dev/null | head -1`. Its folder is `S`. If the script is not on disk, stop and ask the person to install the skill again.

Run every command as `python3 -I "$D/page_view.py" COMMAND ...`.

## Step 1: read

Call `getConfluenceContent` with `content_format: "html"` and `detail: "full"`. A large result is saved to a file, in Claude and in Cursor alike, and the tool result names the path: that path is FILE. A small page comes back inline: then read it directly, and for an edit copy the node's html from that result (see "Small pages"). Never retype a result into a file.

`meta FILE` gives the version and the snapshotToken (`v:N`). Keep both.

The read's `metadata.hasSpaceInstructions` says whether the space has authoring instructions. If it is `true`, read them once with `getConfluenceSpace` through `executeRead` (`spaceIdOrKey`) and follow them: the connector requires this before any write.

`risks FILE` lists what Atlassian's open bugs can change across the whole page on any write (see "Known connector issues"). If it lists anything, tell the person what could change and ask before the first write, unless the run's own instructions already decide it.

**Before the first write of a run, check the draft.** Every page has one hidden shared draft: the editor's live session (see "Drafts" below). Read the page a second time with `draft: true` (DRAFT). `textdiff FILE DRAFT` must say "same text". Use `textdiff`, not `diff`: the draft can carry its own IDs, and then `diff` reports every node as removed and added even when the text is identical. For a page that came back inline, read both as markdown (`content_format: "markdown"`, a quarter to a half of the size, no IDs) and compare the two texts.

If the text differs before you have written anything, the draft may hold someone's unpublished work. Stop and ask the person before writing, even if they asked you to save: say what differs and let them decide. Do not give the draft's age: its `createdAt` can be the moment of your own read (see "Drafts"). If they want the published text kept, fix the draft yourself (see "Fix a draft"); never send them to the editor to discard it.

## Step 2: look

- `view FILE "Section heading"` shows one section. On the test page, one section was 946 characters.
- `view FILE` shows the whole page as text. Use it only when needed: the test page gave 32,076 characters, about the size of a markdown read.

## Step 3: find the IDs

- `ids FILE KEY [KEY...]` finds table rows by their first cell (for example a ticket key, also when it is a link or smart link) and lines by their text. A heading also gives the line under it.
- For a list item, `ids` gives the item's ID and, after it, `paragraph inside: ID`. Replace the paragraph, not the item.
- `ids FILE :first` and `ids FILE :last` give a table's first and last data row (a row of `<th>` cells is skipped; a table without one has no header to skip, so check the cell it shows), with its first cell, so a new row can go after the last one without knowing its key. A page with more than one table gives one hit per table and exit 2: pick by looking.
- Exit 2 means not found or ambiguous: stop and look. Never guess an ID.
- `node FILE ID` prints a node's exact html (one paragraph on the test page: 1,137 characters). For a row, it also shows the IDs of the paragraph inside each cell, so one cell can be edited on its own. Never `node` a whole large table: the test page's main table was 94,577 characters.

## Step 4: dry run

Call `updateConfluenceContent` with `cloudId`, `contentId`, the `snapshotToken` from step 1 (the `v:` one, never the draft's `d1:` one), the `edits` array, and `dryRun: true`. One call may carry several operations: they apply together and make one new version.

Atlassian's tool description says to edit classic pages from the draft with its `d1:` token. Do not: a publish sent with the `d1:` token publishes the whole draft, including anyone's unpublished work (tested 4 Nov 2026). Both tokens pass a dry run, so the dry run does not catch this.

For the html of new nodes, the connector's guide is `getContentFormatGuide` through `executeRead` with toolName `updateConfluencePage`.

Operations, all tested on a copy of a large page on 2 Nov 2026:

- **Replace a line or one cell:** `{"name":"replaceNode","arguments":{"localId":"ID","value":"<p data-local-id=\"ID\">...</p>"}}`. The value is the node html from step 3 with only the intended change. Keep its ID, its marks (strong, code) and any IDs inside it. For one cell, target the paragraph inside that cell.
- **Add a row after or before another:** `{"name":"insertNodeAfter","arguments":{"localId":"ROW_ID","value":"<tr><td><p>KEY</p></td>...</tr>"}}`, or the same with `insertNodeBefore`. One cell per column. Put no IDs on new nodes: the server assigns them. The dry run shows the new cells without `data-colwidth`; the write copies the column widths in (tested 4 Nov 2026).
- **Add a paragraph at the very end of the page:** `{"name":"appendNodeToEnd","arguments":{"value":"<p>...</p>"}}`.
- **Delete one node:** `{"name":"deleteNode","arguments":{"localId":"ID"}}`.
- **Delete several nodes:** `{"name":"removeNodes","arguments":{"localIds":["ID1","ID2"]}}`.
- **Change attributes:** `{"name":"setAttrs","arguments":{"localId":"TABLE_ID","attrs":{"layout":"wide"}}}` set `data-layout="wide"` on a table.
- **Do not use moveNode.** It takes `localId`, `targetLocalId` and a numeric `position`, and in tests it put the node right after the target whatever the position. With the table as target it put a row outside the table, which breaks the page, and the dry run still validated it. To move something inside a page, delete it and insert it again. (Moving a whole page in the page tree is different: see "Rename or move a page".)

The dry run answers with the whole resulting page, about 130,000 characters, so it costs as much as a full read. It is saved to a file (DRYFILE). `diff FILE DRYFILE` must show only the intended change. A validated dry run is not a structure check: if the diff shows anything else, such as table cells turning into loose lines, stop. Quote marks are encoded differently in a dry run; page_view ignores that. The IDs a dry run gives new nodes are not the ones the real write will give: never target them.

## Step 5: write

Send the same call without `dryRun`. The answer is small: the new version number and token. The version must be exactly one higher than in step 1.

## Step 6: read back the page and its draft

1. Read the page again as in step 1 (FILE2). `diff FILE FILE2` must list exactly the intended changes and nothing else. It reports `removed`, `added`, `changed`, `moved`, and `format` (same text, other marks, links or attributes). Images, dividers, cards and other nodes without text show `-` as their ID. `meta FILE2` must show the new version. Anything else, or a missing change, is a failed write: report it first and do not retry blind (see "Undo a write").
2. Read the draft again (`draft: true`, DRAFT2). `textdiff FILE2 DRAFT2` must say "same text". After every write, not only the first: the write itself can damage the draft (see "Drafts"). If the text differs, the write left the draft behind or garbled it: fix it now (see "Fix a draft"), without asking, because the fix only makes the draft match what was just published. Say in the report that you did.

For the next edit, FILE2 and its token are the base.

## Step 7: refusals

- `{"ok":false,"reason":"snapshot_stale",...,"currentSnapshot":{"token":"v:N"}}` means someone wrote in between, and nothing was changed. Do not resend the same payload with the new token. Re-read (step 1), find the IDs again, check that the change still makes sense, and start again from step 4. If the run's own rules treat this as a collision, stop writing and report.
- An error 422 `granular_edit_unresolved` means an ID could not be found exactly once, or an operation lacked a target. Nothing was saved. Re-read and rebuild the whole edit list; never resend it unchanged.

## Step 8: clean up

Delete the temp folder and every file the tool results named in steps 1, 4 and 6. In Claude they are under `~/.claude/projects/<session>/tool-results/`; in Cursor, under its agent-tools folder. Then confirm that no copy is left. If a write failed, keep FILE until the page is repaired: it holds the old html.

## Undo a write

Confluence keeps every version, so a bad write can be undone. Do not write again until the person agrees.

1. Tell them what went wrong, and which version was good: the one from step 1.
2. A few damaged nodes: with their OK, put each one back with `replaceNode`, using its html from `node FILE ID`, from step 4 on.
3. Wider damage: with their OK, restore the version from step 1 with `restoreConfluenceContentVersion` through `executeWrite`: `{"name":"restoreConfluenceContentVersion","cloudId":"...","inputs":{"contentId":"PAGE_ID","versionNumber":N,"message":"Undo of version N+1"}}`, where N is the version from step 1. It adds a new latest version with that version's content, so the page goes to N+2. The title stays as it is unless `restoreTitle` is `true`. Tested 4 Nov 2026: the text and a table layout the write had dropped came back exactly, and the draft was rebuilt to match, but a fragment link came back in another stored form (see "Known connector issues"). If the operation is missing or refused, ask them to open the page, choose the ••• menu, then Version history, and restore the version from step 1.
4. Read the page and its draft again as in step 6, and report the result.

## Known connector issues

Two open Atlassian bugs, as of 4 Nov 2026. Every write goes through a whole-page conversion, so even one `replaceNode` can change nodes you did not target:

- [Issue 269](https://github.com/atlassian/atlassian-mcp-server/issues/269): tables with the layout `align-start` or `center` lose it, so left-aligned tables become centred, and `setAttrs` does not bring it back. The issue also reports non-breaking spaces becoming plain spaces, but they survived writes and a restore on 4 Nov 2026; `diff` shows it as `format` if it happens. The connector cannot make such a table either: on create it drops the layout, and `setAttrs` with `align-start` answers ok without a new version (tested 4 Nov 2026). Reproduced for `center` on 4 Nov 2026: a `replaceNode` on a paragraph dropped the layout of a table centred in the editor. The dry run still showed the layout, so only the step 6 read-back catches it. A version restore brought the layout back.
- [Issue 270](https://github.com/atlassian/atlassian-mcp-server/issues/270): fragment links can change on a large page. Also seen on a small page (4 Nov 2026): a publish through the draft, a version restore and one of two plain `v:` writes each changed a stored link from the page's full URL plus `#Details` to `#Details`. The html read shows `#Details` both times, so it hides the change. `diffConfluenceContentVersions` through `executeRead` (`contentId`, `from_version`, `to_version`, `content_format: "html"`) shows it, but it returns both versions in full: use it on small pages only.

`risks FILE` finds these tables and links before a write. A lost layout shows in `diff` as `format` on a table you did not touch. At step 4, stop and tell the person. At step 6 the write has landed: report it and offer "Undo a write".

## Small pages

A small page comes back inline, so there is no FILE for the script. Never retype a result into a file to get one. Follow the same steps and do the checks by reading:

- Step 1: take the version and token from the result. In place of `risks`, look in the html for `data-layout="align-start"`, `data-layout="center"` and `href="#`.
- Step 3: find the node and its ID in the html.
- Steps 4 and 6: compare the old and new html node by node. Only the intended node may differ, in its text, marks or attributes. Check that images, dividers and cards are all still there.
- The draft: compare markdown reads, as in step 1.

If only one of two results was saved to a file, compare them by reading, using `view FILE` for the saved one.

## Drafts

Tested on a Confluence Cloud site, 2 and 3 Nov 2026.

- Every page has one shared draft, the editor's live session. It is started or restarted when someone clicks Edit (whatever they type is saved there at once, even without Publish), when the connector reads with `draft: true` (the draft's `createdAt` becomes the second of the read), and when the connector publishes (rebuilt less than a second after the write). Nothing seen so far shows that just viewing a page creates one.
- What a publish does to the draft varies. Three outcomes were seen: the draft was replaced by the published page (2 Nov, a draft made through the tool); it was left untouched (a draft from May that survived 11 publishes); and the change was merged into the draft at the wrong place, so the draft kept the old sentence and the new words landed inside another paragraph (a how-to page, 3 Nov). Later publishes merge into the draft cleanly but leave the earlier damage in place.
- A draft that differs from the page is what the next person to click Edit gets, and publishing it from the editor makes it live.
- The draft carries its own IDs (often 12 characters where the page has 36), so compare with `textdiff` or markdown, never with `diff`.
- Never ask the person to discard a draft in the editor. Fix it with the connector (next section).

## Fix a draft

A write to the draft alone: `updateConfluenceContent` with `draft: true` and the draft's `d1:` token. It changes only the draft; the published page and its version stay as they are. Tested 3 Nov 2026 on a throwaway copy (a damaged paragraph put in and taken out again) and on a real how-to page (two damaged paragraphs fixed; the page stayed at version 5).

1. Read the published page (FILE) and the draft (DRAFT), both html, `detail: "full"`. Keep the draft's `d1:N` token.
2. `textdiff FILE DRAFT` lists the lines that differ. Find each one's ID in the draft with `ids DRAFT ...`: the draft's IDs can differ from the page's.
3. For each damaged node, `replaceNode` on the draft's ID, with the published node's html from `node FILE ID` as the value and the draft's ID on its root. A node only in the draft: `deleteNode`. A node missing from the draft: `insertNodeAfter` its neighbour.
4. Dry run first (`dryRun: true`), check the result, then write. The answer says status "draft" and gives a new `d1:` token.
5. Read the draft again: `textdiff FILE DRAFT2` must say "same text". Read the page too: its version must not have changed.

If most of the page differs, for example an old page sitting in the draft, stop and say so: that needs a whole-body draft write, which this skill does not cover.

## Rename or move a page

Tested 3 Nov 2026 on two test pages.

- **Rename:** `updateConfluenceContent` with `title` and the `v:` token, no body and no edits. Dry run first (it answers only "dry_run_validated"). The version goes up by one, and `diff` of the reads before and after says "no differences". Check the draft afterwards as in step 6.
- **Move in the page tree, or change the order of child pages:** `moveConfluenceContent` through `executeWrite`: `{"name":"moveConfluenceContent","cloudId":"...","inputs":{"id":"PAGE_ID","position":"before","targetId":"SIBLING_ID"}}`. `position` is `before` or `after` a sibling, or `append` to put it under a new parent. It makes no new version. Check the order with `getConfluenceContentDescendants` through `executeRead` (`contentId` the parent, `depth` 1): children come back in order with their `childPosition`.
- Plain links on other pages keep the old title as their text. When asked, find them with `view` and change the link text with `replaceNode`.

## Databases

Confluence databases take a CSV edit envelope instead of node edits. Tested on 2 Nov 2026:

- **Read:** `getConfluenceContent` with `content_format: "csv"`. The `_id` column is the row's position, not a fixed ID, and positions renumber after a delete.
- **Write:** `updateConfluenceContent` with `body: {"format":"csv","value":ENVELOPE,"context":{"content":CURRENT_CSV}}` and the snapshotToken. Version and token stayed `v:1` through every edit.
- **Envelope:** a `<metadata>` section with the header `operation_type,target,property,value`, then a `<data>` section with the header `operation_type,entry_index,` followed by every field name. Row operations are `add_entry`, `edit_entry` and `delete_entry`. A cell of `""` means unchanged and `NULL` means clear. Several deletes in one call use the original positions, highest first.
- Read back after every call.
- Before writing, load the guide: `getContentFormatGuide` with toolName `updateConfluenceDatabase`. The guide refuses `updateConfluenceContent` as a name.

## Testing new edit shapes

Test on a copy, never on the live page. `copyConfluenceContent` (contentId, title, parentContentId) makes a server-side copy that keeps the same IDs. `archiveConfluenceContent` removes it afterwards. If the archive fails (seen on 4 Nov 2026 on a new site: error 500, three times), ask the person to delete the copy from its ••• menu: the connector has no delete. Neither is a tool of its own: run them through `executeWrite`, with `cloudId` beside `name` and the rest inside `inputs`, for example `{"name":"copyConfluenceContent","cloudId":"...","inputs":{"contentId":"...","title":"...","parentContentId":"..."}}`.

## Tested facts (Confluence Cloud sites, 2 to 4 Nov 2026, Claude and Cursor)

- The test page's html: 127,834 characters, of which 82,097 are 1,549 ID labels.
- Both platforms save large reads and dry runs to a file, and return small results inline.
- Existing nodes carry 36-character UUID IDs. Nodes added later get 12-character IDs. Both work as targets. An ID can go: an image's `figure` lost its ID after a write, so take IDs from the latest read.
- A normal read gives a `v:N` token; a `draft: true` read gives status "draft" and a `d1:N` token. Edits sent with the `v:` token change the published page; edits sent with `draft: true` and the `d1:` token change only the draft. Edits sent with the `d1:` token and no `draft` publish the whole draft, and the answer then carries a `d1:` token, not `v:`.
- A markdown read is a quarter to a half of the html read and has no IDs: enough for checking text.
- `executeRead` with `name: "getConfluenceContent"` takes `responseFields` (for example `["snapshotToken","metadata.version"]`), which gives a version or token check without the body.
- A title already used in the space gets " (2)" added on create. `copyConfluenceContent` takes an explicit title.
- page_view.py takes 0.03 to 0.5 seconds a command: 0.03 to 0.10 in Claude, 0.1 to 0.5 on a Mac in Cursor. A Confluence call takes 4 to 13 seconds.

## Versions

- 1.00 (4 Nov 2026): first public version. Built and tested on 2 and 3 Nov 2026, in Claude and in Cursor. Undo by version restore, the token rule and the connector's own rules checked live on 4 Nov 2026.
