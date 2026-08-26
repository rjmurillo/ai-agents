"""Curated cases for rule 16, the link reference definition.

Split out of `commonmark_fence_cases` when that module crossed the 500 line
taste ceiling for the second time. The seam is the rule: one leaf block took
five review rounds and fifteen separate `--write` corruptions to get right,
and its cases outgrew the container cases they used to sit beside. They are
merged back into `CASES` there, so both suites still parametrize over one
table and the inventory pin still covers the union.

A `[` appears in none of the fuzzer's 6,000 generated documents, so every case
below is the only coverage its behaviour has.
"""

LINK_REFERENCE_CASES: dict[str, str] = {
    # Rule 16. A link reference definition is its own leaf block, so it does
    # not leave a paragraph open and a following `2.` may start a list. We
    # read it as prose, vetoed the `2.` under rule 4, and `--write` appended a
    # stray fence to a document the reference parser reads as balanced.
    "a link reference definition is not a paragraph":
        "[foo]: /url\n2. ```\n   code\n   ```\n",
    "a title on the next line continues a definition":
        "[foo]: /url\n\"T\"\n2. ```\n   code\n   ```\n",
    # Controls for rule 16, every one of which passed BEFORE it landed. They
    # pin the four ways it must NOT over-fire: a definition cannot interrupt
    # an open paragraph, a second title is prose once the definition has one,
    # an empty label is not a definition, and four columns of indent is code.
    "a definition cannot interrupt a paragraph":
        "text\n[foo]: /url\n2. ```\n   code\n   ```\n",
    "a second title is prose once the definition has one":
        "[foo]: /url \"A\"\n\"B\"\n2. ```\n   code\n   ```\n",
    "an empty link label is not a definition":
        "[]: /url\n2. ```\n   code\n   ```\n",
    "a definition indented four columns is code":
        "    [foo]: /url\n2. ```\n   code\n   ```\n",
    # Rule 16 continued. The destination and title must be COMPLETE. An
    # earlier version required only one non-space character after the colon,
    # so `[foo]: <broken` cleared paragraph state and `--write` appended a
    # fence to a document holding no fence at all. Measured against the
    # reference parser over 22 destination and title shapes.
    "an unclosed angle destination is not a definition":
        "[foo]: <broken\n2. ~~~\n   code\n",
    "an unclosed title is not a definition":
        "[foo]: /url \"unclosed\n2. ~~~\n   code\n   ~~~\n",
    "junk after a complete title is not a definition":
        "[foo]: /url \"T\" trailing\n2. ~~~\n   code\n   ~~~\n",
    "unbalanced parentheses in a destination are not a definition":
        "[foo]: /u(rl\n2. ~~~\n   code\n   ~~~\n",
    "a closed angle destination is a definition":
        "[foo]: <a b>\n2. ~~~\n   code\n   ~~~\n",
    # And the destination may start on the line after the label. The label
    # line stays paragraph text until a valid destination proves otherwise,
    # which the next two cases pin in both directions.
    "a destination on the following line completes a definition":
        "[foo]:\n/url\n2. ~~~\n   code\n   ~~~\n",
    "a label alone does not clear paragraph state":
        "[foo]:\n2. ~~~\n   code\n   ~~~\n",
    "a label followed by a bad destination stays a paragraph":
        "[foo]:\n<broken\n2. ~~~\n   code\n   ~~~\n",
    # Rule 16 continued. A fence INTERRUPTS a pending definition. The scanner
    # freezes container state for the whole fenced block, so nothing between
    # the opener and the closer is ever observed; a pending destination or
    # title therefore matched the first line AFTER the block, cleared
    # paragraph state the reference parser keeps open, and `--write` appended
    # a closer to a balanced document. Both pending states, both fence
    # characters, because the class is the freeze and not the syntax.
    "a fence interrupts a pending destination":
        "[foo]:\n```\nx\n```\n/url\n2. ~~~\n   code\n",
    "a fence interrupts a pending title":
        "[foo]: /url\n```\nx\n```\n\"T\"\n2. ~~~\n   code\n",
    "a tilde fence interrupts a pending destination":
        "[foo]:\n~~~\nx\n~~~\n/url\n2. ```\n   code\n",
    "a marker-line fence interrupts a pending destination":
        "[foo]:\n- ```\n  x\n  ```\n/url\n2. ~~~\n   code\n",
    # The control for that fix: with no definition pending, a fence followed
    # by an ordered marker behaves exactly as it did before.
    "a fence with no pending definition is unaffected":
        "text\n\n```\nx\n```\n\n2. item\n   ~~~\n   y\n   ~~~\n",
    # Rule 16 continued. A bracketless destination balances parentheses at ANY
    # depth, and a title may carry an escaped copy of its own delimiter. Both
    # were spelled as patterns with a fixed one level, so `[foo]: /u(r(l))` and
    # `[foo]: /url "a\\"b"` were read as prose while the reference parser reads
    # both as definitions. That kept a paragraph open, vetoed the marker below
    # it, and `--write` appended a fence to a balanced document. The depth is
    # why the destination is now a scanner and not a pattern: a pattern has to
    # pick a ceiling, and any ceiling is the next round of this same defect.
    "a destination nests parentheses two deep":
        "[foo]: /u(r(l))\n2. ```\n   code\n   ```\n",
    "a destination nests parentheses five deep":
        "[foo]: /a(((((b)))))\n2. ```\n   code\n   ```\n",
    "a title may escape its own quote":
        "[foo]: /url \"a\\\"b\"\n2. ```\n   code\n   ```\n",
    "a parenthesised title may escape its own bracket":
        "[foo]: /url (a\\)b)\n2. ```\n   code\n   ```\n",
    # The controls: unbalanced stays prose, in both directions, and an escaped
    # parenthesis does not count toward the balance.
    "an unclosed parenthesis is not a destination":
        "[foo]: /a((b)\n2. ```\n   code\n   ```\n",
    "a stray closing parenthesis is not a destination":
        "[foo]: /a(b))c\n2. ```\n   code\n   ```\n",
    "an escaped parenthesis does not open a group":
        "[foo]: /a\\(b\n2. ```\n   code\n   ```\n",
    # Rule 16 continued, and this one no reviewer named. A definition's
    # continuation belongs to the SAME leaf block, so CommonMark strips its
    # indent rather than reading indented code. The indent veto sat in front
    # of that test, so a four-column destination left the label line a
    # paragraph, rule 4 vetoed the marker below it, the real closing fence
    # became a fresh opener, and `--write` appended a closer to a balanced
    # document. Found by sweeping every line shape that can follow a pending
    # state, after a first sweep classified it as a miss: the probe asked
    # whether the tool reported NO defect, and the tool reported a false one.
    "a four-column destination continues a definition":
        "[foo]:\n    /url\n2. ```\n   code\n   ```\n",
    "a tab-indented destination continues a definition":
        "[foo]:\n\t/url\n2. ```\n   code\n   ```\n",
    "a four-column title continues a definition":
        "[foo]: /url\n    \"T\"\n2. ```\n   code\n   ```\n",
    # Controls: the veto still applies when nothing is pending, and when the
    # indented line is not a destination at all.
    "a four-column line with nothing pending is code":
        "text\n\n    code\n\n2. item\n   ```\n   x\n   ```\n",
    "a four-column non-destination does not continue a definition":
        "[foo]:\n    a b\n2. ```\n   code\n   ```\n",
    # Rule 16 continued, five more found by an adversarial sweep of the pending
    # state rather than by review. Every one is a `--write` corruption: the
    # reference parser reads the document as balanced and the tool appends to
    # it. They share one cause, that a pending definition is an OPEN LEAF BLOCK
    # and every block boundary has to say what it does to one.
    #
    # An indented code block is its own leaf block, so it ENDS a pending
    # definition. The indent veto returned before saying so, and the title two
    # lines down was then booked against a definition CommonMark had already
    # closed.
    "indented code ends a pending definition":
        "[foo]: /url\n    zzz\n\"t\"\n2. ```\n",
    # A new list item is a new container, and the pending state belonged to the
    # one outside it. The caller re-parses a marker's remainder inside the item
    # it just opened, and that pass consumed the stale flag.
    "a list marker ends a pending destination":
        "[foo]:\n- /url\nx\n  ```\nx\n",
    "a list marker ends a pending title":
        "[foo]: /url\n- \"t\"\nx\n  ```\nx\n",
    # And the mirror of that: a line CONTINUING a pending definition is a lazy
    # continuation, so it must not close the item holding it. Popping the item
    # on a dedented title moved the fence below it from inside the item to
    # column zero, where nothing could close it.
    "a dedented title does not close the item holding its definition":
        "- [foo]: /url\n\"title\"\n  ~~~\ncode\n",
    # CommonMark normalises a label before comparing it, so one holding only
    # whitespace normalises to empty and the line is not a definition. The
    # blank-label guard tested space and tab, which let every other Unicode
    # whitespace character through.
    "a label of only Unicode whitespace is not a definition":
        "[\u00a0]: /url\n2. item\n    ```\n    code\n",
    # The control: whitespace INSIDE a real label is still a definition.
    "Unicode whitespace inside a label is still a definition":
        "[a\u00a0b]: /url\n2. ```\n   code\n   ```\n",
    # Rule 16 continued. The angle destination form may carry an ESCAPED copy
    # of either delimiter. `find(">")` stopped at the first one and a substring
    # test rejected the other, so both of these read as prose while the
    # reference parser reads them as definitions, and `--write` appended a
    # fence to a balanced document.
    "an escaped closing angle stays inside the destination":
        "[foo]: <a\\>b>\n2. ```\n   code\n   ```\n",
    "an escaped opening angle stays inside the destination":
        "[foo]: <a\\<b>\n2. ```\n   code\n   ```\n",
    # The controls: an UNESCAPED inner `<` is still not a destination, and an
    # escaped BACKSLASH still lets the next `>` close.
    "an unescaped inner angle is not a destination":
        "[foo]: <a<b>\n2. ```\n   code\n   ```\n",
    "an escaped backslash still lets the angle close":
        "[foo]: <a\\\\>\n2. ```\n   code\n   ```\n",
    # And a title may run across lines until its delimiter arrives, which the
    # parser had no state for at all: it needed a third pending state beside
    # the destination and the bare title. All three delimiters, because the
    # missing state is the shape, not the syntax.
    "a double-quoted title may span two lines":
        "[foo]: /url \"a\nb\"\n2. ```\n   code\n   ```\n",
    "a single-quoted title may span two lines":
        "[foo]: /url 'a\nb'\n2. ```\n   code\n   ```\n",
    "a parenthesised title may span two lines":
        "[foo]: /url (a\nb)\n2. ```\n   code\n   ```\n",
    "a title may span three lines":
        "[foo]: /url \"a\nb\nc\"\n2. ```\n   code\n   ```\n",
    "a next-line title may itself span two lines":
        "[foo]: /url\n\"a\nb\"\n2. ```\n   code\n   ```\n",
    # Controls for that state, each measured against the reference parser: a
    # block start ABANDONS the title and the whole run is a paragraph, junk
    # after the closing delimiter is not a definition, and a title that never
    # closes before a blank line was never one.
    "a list marker abandons an open title":
        "[foo]: /url \"a\n2. b\"\n2. ```\n   code\n   ```\n",
    "a fence abandons an open title":
        "[foo]: /url \"a\n```b\"\n2. ```\n   code\n   ```\n",
    "four columns of indent do not abandon an open title":
        "[foo]: /url \"a\n    b\"\n2. ```\n   code\n   ```\n",
    "junk after a multi-line title is not a definition":
        "[foo]: /url \"a\nb\" junk\n2. ```\n   code\n   ```\n",
    "a title that never closes is not a definition":
        "[foo]: /url \"a\nb\n\n2. ```\n   code\n   ```\n",
    # Rule 16 continued, and this pair no reviewer named: the LABEL may span
    # lines too. That is a fourth pending state, and it accumulates BEFORE the
    # destination state the other three sit behind. Same corruption as the
    # title: the reference parser completes the definition, we read prose,
    # rule 4 vetoes the marker below, and `--write` appends.
    "a label may span two lines":
        "[fo\no]: /url\n2. ```\n   code\n   ```\n",
    "a label may span three lines":
        "[f\no\no]: /url\n2. ```\n   code\n   ```\n",
    "a split label may carry an escaped bracket":
        "[fo\\]o\nbar]: /url\n2. ```\n   code\n   ```\n",
    "a split label may leave its destination to the next line":
        "[fo\no]:\n/url\n2. ```\n   code\n   ```\n",
    "a split label may open a multi-line title":
        "[fo\no]: /url \"a\nb\"\n2. ```\n   code\n   ```\n",
    # Controls, each measured: the closing bracket must be followed by a
    # colon, a blank line kills the label, a block start abandons it, and a
    # label that normalises to empty was never one.
    "a split label without a colon is not a definition":
        "[fo\no] /url\n2. ```\n   code\n   ```\n",
    "a blank line kills a split label":
        "[fo\n\no]: /url\n2. ```\n   code\n   ```\n",
    "a list marker abandons a split label":
        "[fo\n- x\no]: /url\n2. ```\n   code\n   ```\n",
    "an ATX heading abandons a split label":
        "[fo\n# h\no]: /url\n2. ```\n   code\n   ```\n",
    "a split label of only whitespace is not a definition":
        "[ \n ]: /url\n2. ```\n   code\n   ```\n",
}
