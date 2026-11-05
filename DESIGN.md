---
name: Report Checker
description: An auditor's working-paper file. Ledger-green pad, printed green rules, coloured-pencil tick marks.
colors:
  desk: "#c9d8c2"
  pad: "#e8f0e3"
  pad-col: "#e0eadb"
  rule: "#b5ccb0"
  rule-strong: "#4f7a5e"
  print: "#183324"
  print-2: "#3d5848"
  print-3: "#4f6858"
  blue: "#1f4fa3"
  red: "#b3221a"
  brown: "#7b4416"
  ochre: "#8a5a00"
  graphite: "#4e5752"
  blue-wash: "rgba(31, 79, 163, .08)"
  red-wash: "rgba(179, 34, 26, .09)"
  brown-wash: "rgba(123, 68, 22, .1)"
  ochre-wash: "rgba(138, 90, 0, .1)"
  graphite-wash: "rgba(78, 87, 82, .08)"
  tab-hover: "#d6e4d1"
  note-bg: "#f2f7ef"
  llm-bg: "#eef3fb"
  on-ink: "#cfe0c8"
  browser-chrome: "#dbe8d5"
typography:
  display:
    fontFamily: "Archivo, Arial Narrow, sans-serif"
    fontSize: "clamp(2.6rem, 6.4vw, 5.25rem)"
    fontWeight: 800
    lineHeight: 0.92
    letterSpacing: "-0.02em"
    fontVariation: "'wdth' 72"
  headline:
    fontFamily: "Archivo, Arial Narrow, sans-serif"
    fontSize: "clamp(1.45rem, 2.6vw, 2rem)"
    fontWeight: 750
    lineHeight: 1.1
    letterSpacing: "-0.01em"
    fontVariation: "'wdth' 78"
  title:
    fontFamily: "Archivo, Arial Narrow, sans-serif"
    fontSize: "1rem"
    fontWeight: 700
    lineHeight: 1.25
    fontVariation: "'wdth' 85"
  label:
    fontFamily: "Archivo, Arial Narrow, sans-serif"
    fontSize: "0.74rem"
    fontWeight: 600
    lineHeight: 1.3
    letterSpacing: "0.06em"
    fontVariation: "'wdth' 85"
  purpose:
    fontFamily: "Source Serif 4, Georgia, serif"
    fontSize: "clamp(1.2rem, 2vw, 1.5rem)"
    fontWeight: 400
    lineHeight: 1.35
  body:
    fontFamily: "Source Serif 4, Georgia, serif"
    fontSize: "1.0625rem"
    fontWeight: 400
    lineHeight: 1.6
  report-text:
    fontFamily: "Source Serif 4, Georgia, serif"
    fontSize: "1.16rem"
    fontWeight: 400
    lineHeight: "2rem"
    fontFeature: "'lnum', 'tnum'"
  data:
    fontFamily: "JetBrains Mono, Consolas, monospace"
    fontSize: "0.92rem"
    fontWeight: 400
    fontFeature: "'tnum'"
  sql:
    fontFamily: "JetBrains Mono, Consolas, monospace"
    fontSize: "0.8rem"
    fontWeight: 400
    lineHeight: 1.55
  hand:
    fontFamily: "Kalam, Segoe Print, cursive"
    fontSize: "2rem"
    fontWeight: 400
    lineHeight: 1
rounded:
  claim: "2px"
  tab: "3px"
spacing:
  line: "2rem"
  gutter: "clamp(1rem, 3vw, 2.5rem)"
  sheet-pad: "clamp(1rem, 2.6vw, 2.25rem)"
  sheet-max: "84rem"
components:
  index-tab:
    backgroundColor: "{colors.desk}"
    textColor: "{colors.print}"
    rounded: "{rounded.tab}"
    padding: "0.5rem 0.6rem"
  index-tab-hover:
    backgroundColor: "{colors.tab-hover}"
  index-tab-selected:
    backgroundColor: "{colors.pad}"
    textColor: "{colors.print}"
  wp-ref:
    textColor: "{colors.print}"
    typography: "{typography.data}"
    padding: "0.45rem 0.55rem 0.4rem"
  margin-note:
    backgroundColor: "{colors.note-bg}"
    textColor: "{colors.print}"
    padding: "1rem 1.05rem 1.1rem"
  sql-block:
    backgroundColor: "{colors.pad}"
    textColor: "{colors.print}"
    typography: "{typography.sql}"
    padding: "0.6rem 0.7rem"
  procedure-step:
    backgroundColor: "{colors.pad}"
    textColor: "{colors.print}"
    padding: "1rem 1.1rem 1.15rem"
  procedure-step-llm:
    backgroundColor: "{colors.llm-bg}"
  procedure-step-output:
    backgroundColor: "{colors.print}"
    textColor: "{colors.pad}"
  run-tag:
    textColor: "{colors.blue}"
    padding: "0.05rem 0.3rem"
---

# Design System: Report Checker

## Overview

**Creative North Star: "The Working-Paper File"**

The whole surface is an auditor's working-paper file on one analyst report. Each section is a sheet of pale ledger-green pad laid on a darker green desk, headed by a printed working-paper block (a boxed reference such as Report 02, a condensed title, a row of form fields: client, prepared by, period, reviewed by, settings). Inside, the analyst's report sits on the pad's printed ruling and every figure carries a coloured-pencil tick mark that points to its evidence in the margin.

Density is that of a real working paper: compact form labels, schedules with rules and footings, notes in the margin. The voice is calm and procedural. Colour is almost entirely the green of the paper and its print; the pencils (blue, red, brown, ochre, graphite) carry meaning and nothing else. The world refuses the AI-showcase default of hero headline, feature cards and metric tiles; the cover is the file's label, and the work leads.

**Key Characteristics:**
- Ledger-green pad sheets on a green desk, edged by a strong green rule and a soft paper shadow.
- Printed working-paper header on every sheet: condensed Archivo title, uppercase field labels, and on the report sheets a boxed monospace reference to the selected report.
- Coloured-pencil tick marks drawn as authored SVG strokes; each status has its own pencil, mark shape and underline style.
- Red only where the data contradicts a figure.
- Four type hands with fixed jobs: printed form, the report's text, data, and the preparer's handwriting.
- One authored motion: the red pencil circle drawing around a contradicted figure.

## Colors

A monochrome ledger-green paper world, printed in deep green ink, annotated with five coloured pencils.

### Primary
- **Ledger Print Green** (print): all printed matter, from the display title to the 2px rules under headers, schedule heads and footings. Also the solid ground of the procedure's output step.
- **Agreed Blue Pencil** (blue): the default pencil. Agreed ticks, verified and supported underlines, links, the focus ring, the preparer's signature, the footing mark, the frozen-run tag and the frozen-run row wash.

### Secondary
- **Exception Red Pencil** (red): figures the data contradicts and nothing else; the exception tick, the drawn circle, the contradicted underline and hover wash, and the margin note's border while it shows a contradicted claim.
- **Does-Not-Foot Brown** (brown): the report's own numbers disagree; also the "missing" requirement mark.
- **Unsupported Ochre** (ochre): conclusions the data does not support, partial coverage, missed answer-key items, and an older (non-frozen) run in the sheet header.
- **Graphite** (graphite): could not be verified, and checker-side query failures; also the held-out stamp.

### Neutral
- **Green Desk** (desk): page ground behind the sheets, and the unselected index tab.
- **Ledger Pad** (pad): the sheet itself, the selected tab (continuous with the sheet), SQL blocks and procedure steps.
- **Pad Column** (pad-col): the secondary column tint; the band under the sheet header and the held-out panel.
- **Faint Ruling** (rule): the pad's printed ruling under the report text and schedule cell rules.
- **Strong Ruling** (rule-strong): sheet borders, tab edges, field dividers and step boxes.
- **Second and Third Print** (print-2, print-3): field labels, subtitles, evidence lines, untested rows, the ditto mark.
- **Margin Note Paper** (note-bg): the slightly lighter slip the evidence note is written on.
- **LLM Step Tint** (llm-bg): a faint blue tint marking the procedure steps an LLM performs.
- **On-Ink Green** (on-ink): secondary text on the dark output step.
- **Washes** (blue-wash, red-wash, brown-wash, ochre-wash, graphite-wash): each pencil's 8 to 10% wash, used only as the hover and active background of a claim in that pencil, and the frozen-run row.

### Named Rules
**The Red Pencil Rule.** Red marks a figure the data contradicts. It is never decoration, never a brand accent, never an error style for anything else.

**The Pencil Per Status Rule.** A status is encoded three ways at once: its pencil colour, its tick-mark shape, and its underline style (solid, double, wavy, dotted, dashed). Never rely on colour alone, and never give two statuses the same pencil and mark.

## Typography

**Display Font:** Archivo, variable width (with Arial Narrow)
**Body Font:** Source Serif 4 (with Georgia)
**Label/Mono Font:** JetBrains Mono (with Consolas)
**Hand Font:** Kalam (with Segoe Print)

**Character:** Condensed Archivo is the printed form, Source Serif is the analyst's typed report and the reviewer's prose, JetBrains Mono is the data, and Kalam is the preparer's pencil. All four are self-hosted (latin subset).

### Hierarchy
- **Display** (Archivo 800, condensed to 72% width): the cover title only.
- **Headline** (Archivo 750, 78% width): the sheet title in each working-paper header.
- **Title** (Archivo 700, 85% width, 1 to 1.25rem): sub-heads within a sheet (answer key, memo, caveats, schedule titles, the note's status line, procedure step names).
- **Purpose** (Source Serif 4, 1.2 to 1.5rem, balanced, max 34ch): the one-line pitch under the cover title.
- **Body** (Source Serif 4 400, 1.0625rem/1.6): prose, memo, notes; measure 60 to 72ch.
- **Report Text** (Source Serif 4, 1.16rem on the 2rem ruling, lining tabular figures, max 68ch): the report under review.
- **Label** (Archivo 600, 0.74rem, 0.06em tracking, uppercase, print-2): form field labels, table column heads, legend caption, step "who" lines, signature caption.
- **Data** (JetBrains Mono): report refs (700), requirement refs, numeric schedule cells, the note's data figure, model names, SQL (0.8rem/1.55).
- **Hand** (Kalam 400): the signature (2rem, rotated -2deg) and the ditto mark in the run history.

### Named Rules
**The Four Hands Rule.** Each face has one job. Archivo prints the form; Source Serif carries sentences; JetBrains Mono is reserved for data, references and SQL; Kalam appears only as the signature and the ditto mark.

**The Tabular Figures Rule.** Every figure that can be compared vertically or read against data uses tabular numerals (schedules, tab tallies, report text).

## Layout

Each section is a sheet: centred, max 84rem, full width below that, padded by the sheet padding, separated by 1.5 to 2.25rem of desk. The page gutter is clamp(1rem, 3vw, 2.5rem). The report text sits on a 2rem ruling drawn as a repeating gradient in the faint rule colour.

The review sheet is a three-column working paper at full width: index tabs (11rem) hanging off the sheet's left edge, the ruled report, and a margin (15 to 21rem) holding the evidence note above the legend; the answer key sits under the report. The note stays in its place (never sticky or fixed), so it can never cover the legend or any other content.

Responsive behaviour (desktop first):
- **1100px:** the index tabs become a strip of top tabs across the sheet; the note stays beside the report; the six-step procedure wraps to three columns.
- **960px:** schedules marked to stack become labelled rows: the header row is hidden, each cell is a two-column grid with its uppercase label drawn from the data label, and the footing keeps its single-over, double-under rules.
- **900px:** one column. The note sits under the report, and tapping a claim scrolls the note into view (instantly under reduced motion). Instruction copy switches to its tap wording.
- **760px:** phone. The cover's field block is replaced by a compact byline, the tab strip scrolls horizontally, the header keeps only the prepared-by and run fields, two-column blocks stack, and the procedure becomes a single column whose arrows point down.

## Elevation & Depth

Depth is physical paper on a desk, nothing more. Sheets sit on the desk with a hairline plus a long, soft, low shadow; the margin note is a slip lying on the sheet. There are no other shadows, no blur, and no hover lift.

### Shadow Vocabulary
- **Sheet on desk** (`box-shadow: 0 1px 0 rgba(24, 51, 36, .06), 0 18px 40px -26px rgba(24, 51, 36, .45)`): every sheet.
- **Note slip** (`box-shadow: 0 10px 24px -20px rgba(24, 51, 36, .6)`): the margin note only.

### Named Rules
**The Paper On Desk Rule.** Only paper casts a shadow, and only the green-ink shadow above. Controls, tabs and tables are printed on the paper and stay flat.

## Shapes

Square paper. Sheets, notes, SQL blocks, schedules, procedure steps and the report ref box have square corners and 1 to 2px green rules. The only rounding: index tabs (3px on their free corners, like cut card tabs), the claim highlight and the focus ring (2px). Procedure steps join edge to edge and point to the next step with a rotated-square arrow. The held-out panel uses a dashed rule; its stamp is a bordered uppercase label rotated -3deg. Schedule footings use a single rule over and a 3px double rule under, as a ledger total.

## Components

### Working-Paper Header
Printed and procedural. On the report sheets a boxed reference (JetBrains Mono 700, 1.5px print border) spans two rows at left; the condensed headline and either a subtitle or a field row (uppercase label, Archivo value) sit beside it. A 2px print rule closes the header, with a 3px pad-column band beneath. The ref names the selected report ("Report 02") on the report, coverage and memo sheets; the benchmark and method sheets have no ref box.

### Index Tabs
Card-index tabs, not buttons. Unselected tabs are desk green with a strong rule on three sides; hover lightens to tab-hover over 0.2s. The selected tab turns pad colour, gains 700 weight, and extends 1px to merge with the sheet. Each tab is named "Report 02" (never an analyst's name: the reports are fictional samples, and the list is headed "10 sample reports to check") and states its findings in words ("1 wrong · 1 unsupported", or "clean"); an earlier-run note is set in italic. Below 1100px they become top tabs; below 760px the strip scrolls.

### Tick Marks and Claims
Authored SVG symbols drawn once in the page and reused: agreed (check), exception (cross), does-not-foot (double bar struck through), unsupported (question), unverified (dashed circle), query failed (arrow to a bar), partial (short check with dash), missing (struck circle). Each takes `currentColor` from its pencil. A claim is underlined in its pencil's style (1.5px, offset 0.28em) with its tick after the text; hover or selection washes it in its pencil. A contradicted figure is circled in red pencil.

### Margin Note
The evidence slip. Note paper, strong-rule border (red while it shows a contradicted claim), status line with its tick, the quoted claim, the data figure in mono, the reasoning in print-2, and the SQL in a pad-coloured block with a faint rule. "Show the data" (a disclosure in blue Archivo) opens the dataset rows the claim's query read, as a small ledger table with plain column names, and names the source with a link (Our World in Data, energy dataset). Sharing is a small, labelled "Copy link" with a link icon in print-2, never presented as a source.

### Schedules
Ledger tables. Uppercase label heads over a 2px print rule, faint cell rules with vertical separators, mono right-aligned numbers, footing with single-over double-under rules. Results are an Archivo label with a tick. Below 960px they stack into labelled rows.

### Procedure
Six joined boxes with arrow joints. LLM steps are tinted llm-bg, code steps are pad, and the output step is reversed (print ground, pad text, on-ink secondary text).

### Sign-off
A 2px print rule, the Kalam signature in blue pencil rotated -2deg over an uppercase caption, and the links.

### Browser Surface
Light colour scheme only. The browser chrome tint and favicon ground are browser-chrome green, with a blue pencil check as the favicon. Scrollbars use strong ruling on pad-column; text selection is blue pencil at 22%; focus is a 2px blue outline offset 3px.

### Motion
One authored motion: when a report opens on a contradicted claim, its red circle draws in (1.1s, cubic-bezier(.16, 1, .3, 1), after 0.35s). Under reduced motion the circle is simply present. Everything else is a colour transition of 0.18 to 0.2s.

## Do's and Don'ts

### Do:
- **Do** head every sheet with the working-paper block: condensed Archivo title, field row or subtitle, and the boxed report ref on report sheets.
- **Do** write every label in plain words for a technical leader, not an accountant: "Contradicted by the data", "Numbers inside the report don't add up", "Legend"; the working-paper look carries the world, the words stay plain.
- **Do** encode each status by pencil colour, tick shape and underline style together, and show the legend on the sheet that uses the marks.
- **Do** draw tick marks from the authored SVG symbol set, coloured by `currentColor`.
- **Do** set every comparable figure in tabular numerals and data, refs and SQL in JetBrains Mono.
- **Do** close totals with a single rule over and a 3px double rule under.
- **Do** keep the red circle as the only drawn motion, and disable it under reduced motion.

### Don't:
- **Don't** use red for anything except a figure the data contradicts.
- **Don't** use Kalam beyond the signature and the ditto mark.
- **Don't** add hero headlines, feature cards or metric tiles; numbers live in sentences and schedules.
- **Don't** put an uppercase label above a heading as a section kicker; the uppercase label names a form field, a column or a caption.
- **Don't** add shadows beyond the sheet and the note slip, or round anything other than tabs, claims and focus.
- **Don't** introduce a dark theme; the file is paper.
