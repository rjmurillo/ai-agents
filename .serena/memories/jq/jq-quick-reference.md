# jq: Quick Reference

## Basic Operators

Examples are shown in fenced blocks, not table cells, so the `|` characters
are the real jq pipe operator. A markdown table cell cannot hold a bare `|`,
and the escaped `\|` a table would need is a jq syntax error: `jq '.count \|
tonumber'` exits 3 with `syntax error, unexpected INVALID_CHARACTER`.

```text
Operator  Purpose           Example
.field    Access field      .name
.[]       Iterate array     .[].id
.[n]      Index array       .[0]
|         Pipe              .[] | .name
,         Multiple outputs  .name, .id
```

## Filters

```text
Function    Purpose         Example
select()    Filter          select(.state == "open")
map()       Transform       map(.name)
sort_by()   Sort            sort_by(.date)
group_by()  Group           group_by(.author)
unique      Dedupe          unique
flatten     Flatten arrays  flatten
```

## String Functions

```text
Function      Purpose          Example
contains()    Substring match  select(.name | contains("api"))
startswith()  Prefix match     select(.name | startswith("test"))
split()       Split string     split(",")
join()        Join array       join(", ")
@csv          CSV format       [.a, .b] | @csv
@tsv          TSV format       [.a, .b] | @tsv
```

## Type Functions

```text
Function  Purpose              Example
type      Get type             type
tonumber  To number            .count | tonumber
tostring  To string            .id | tostring
length    Array/string length  length
keys      Object keys          keys
```

## References

- [jq Manual](https://jqlang.github.io/jq/manual/)
- [jq Tutorial](https://jqlang.org/tutorial/)
- [jq Cookbook](https://github.com/stedolan/jq/wiki/Cookbook)

## Related

- [jq-aggregation](jq-aggregation.md)
- [jq-array-operations](jq-array-operations.md)
- [jq-conditionals](jq-conditionals.md)
- [jq-field-extraction](jq-field-extraction.md)
- [jq-filtering](jq-filtering.md)
