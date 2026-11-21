# jq helpers for Notion API JSON. Use: jq -L ~/.agents/skills/control-notion/scripts 'include "notion"; …'

# Plain text of a rich_text array.
def text: [.[]?.plain_text] | join("");

# Title of a page, database row or data source, whatever its title property is named.
def title:
  ([.properties[]? | select(.type == "title") | .title[]?.plain_text] | join("")) as $t
  | if $t != "" then $t else (.title | text) end;

# A page's property values, one plain value per property.
def props:
  .properties | map_values(
    if .type == "title" or .type == "rich_text" then (.[.type] | text)
    elif .type == "select" or .type == "status" then .[.type].name
    elif .type == "multi_select" then [.multi_select[].name]
    elif .type == "date" then .date.start
    elif .type == "people" then [.people[] | .name // .id]
    elif .type == "relation" then [.relation[].id]
    elif .type == "files" then [.files[].name]
    elif .type == "formula" then .formula[.formula.type]
    elif .type == "rollup" then .rollup[.rollup.type]
    elif .type == "unique_id" then "\(.unique_id.prefix // "")\(.unique_id.number)"
    elif .type == "created_by" or .type == "last_edited_by" then (.[.type] | .name // .id)
    else .[.type] end);

# A block's display text, for listings.
def btext:
  .type as $t
  | if $t == "child_page" or $t == "child_database" then .[$t].title
    elif $t == "table_row" then [.table_row.cells[] | text] | join(" | ")
    else ((.[$t].rich_text // .[$t].caption // []) | text) end;
