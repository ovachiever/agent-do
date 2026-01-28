# agent-excel - AI-first Excel CLI

Structured CLI for AI agents to interact with Excel workbooks like a human would - read, write, navigate, format, and analyze spreadsheet data.

---

## Design Principles

1. **Structured I/O** - JSON responses, predictable cell references
2. **Stateful session** - Open workbook stays in memory, changes accumulate
3. **Human-like operations** - Mirror what a human does: select, read, write, format
4. **Snapshot-based** - Get current state before acting (like agent-browse)
5. **Graceful errors** - Clear messages with suggestions

---

## Core Commands

### Workbook Management

```bash
agent-excel open <path>              # Open existing workbook
agent-excel new [path]               # Create new workbook
agent-excel save [path]              # Save (optionally to new path)
agent-excel close                    # Close without saving
agent-excel export csv <path>        # Export active sheet to CSV
agent-excel export pdf <path>        # Export to PDF
agent-excel status                   # Current workbook info
```

**Output: `open`**
```json
{
  "path": "/path/to/workbook.xlsx",
  "sheets": ["Sheet1", "Data", "Summary"],
  "active_sheet": "Sheet1",
  "modified": false
}
```

### Sheet Navigation

```bash
agent-excel sheets                   # List all sheets
agent-excel sheet <name>             # Switch to sheet
agent-excel sheet new <name>         # Create new sheet
agent-excel sheet rename <old> <new> # Rename sheet
agent-excel sheet delete <name>      # Delete sheet
agent-excel sheet copy <name> [new]  # Copy sheet
```

### Reading Data

```bash
agent-excel snapshot                 # Overview of active sheet
agent-excel snapshot --range A1:Z50  # Specific range
agent-excel snapshot --used          # Only used range
agent-excel snapshot --headers       # First row as headers + data preview

agent-excel get <cell>               # Get single cell: A1, B2
agent-excel get <range>              # Get range: A1:D10
agent-excel get row <n>              # Get entire row
agent-excel get col <letter>         # Get entire column
agent-excel get value <cell>         # Raw value only
agent-excel get formula <cell>       # Formula if present
agent-excel get format <cell>        # Cell format info
```

**Output: `snapshot`**
```json
{
  "sheet": "Data",
  "used_range": "A1:F150",
  "row_count": 150,
  "col_count": 6,
  "headers": ["ID", "Name", "Email", "Date", "Amount", "Status"],
  "preview": [
    {"row": 2, "A": "1001", "B": "John Doe", "C": "john@example.com", ...},
    {"row": 3, "A": "1002", "B": "Jane Smith", ...}
  ],
  "preview_rows": 5
}
```

**Output: `get A1:C3`**
```json
{
  "range": "A1:C3",
  "values": [
    ["Name", "Email", "Score"],
    ["Alice", "alice@example.com", 95],
    ["Bob", "bob@example.com", 87]
  ],
  "formulas": [
    [null, null, null],
    [null, null, null],
    [null, null, "=B3*1.1"]
  ]
}
```

### Writing Data

```bash
agent-excel set <cell> <value>       # Set single cell
agent-excel set <range> <json>       # Set range from 2D array
agent-excel fill <range> <value>     # Fill range with value
agent-excel clear <range>            # Clear cell contents
agent-excel clear <range> --all      # Clear contents + formatting

agent-excel formula <cell> <expr>    # Set formula: =SUM(A1:A10)
agent-excel paste <range> <json>     # Paste 2D data array
```

**Examples:**
```bash
agent-excel set A1 "Hello World"
agent-excel set B2 42
agent-excel set C3 "=A1&B2"
agent-excel set A1:C2 '[["Name","Age","City"],["Alice",30,"NYC"]]'
agent-excel fill A1:A100 0
agent-excel formula D2 "=SUM(A2:C2)"
```

### Row/Column Operations

```bash
agent-excel insert row <n> [count]   # Insert row(s) at position
agent-excel insert col <letter> [n]  # Insert column(s)
agent-excel delete row <n> [count]   # Delete row(s)
agent-excel delete col <letter> [n]  # Delete column(s)
agent-excel hide row <n>             # Hide row
agent-excel hide col <letter>        # Hide column
agent-excel unhide row <n>           # Unhide row
agent-excel unhide col <letter>      # Unhide column
agent-excel resize row <n> <height>  # Set row height
agent-excel resize col <l> <width>   # Set column width
agent-excel autofit col <letter>     # Auto-fit column width
agent-excel autofit row <n>          # Auto-fit row height
```

### Finding & Filtering

```bash
agent-excel find <text>              # Find text, return cell refs
agent-excel find <text> --regex      # Regex search
agent-excel find <text> --col B      # Search in column B only
agent-excel replace <old> <new>      # Replace all occurrences
agent-excel replace <old> <new> -n 1 # Replace first only

agent-excel filter <col> <op> <val>  # Filter: filter B ">" 100
agent-excel filter clear             # Clear all filters
agent-excel sort <col> [asc|desc]    # Sort by column
agent-excel sort <col1> <col2>       # Multi-column sort
```

**Filter operators:** `=`, `!=`, `>`, `<`, `>=`, `<=`, `contains`, `startswith`, `endswith`, `empty`, `notempty`

**Output: `find "error"`**
```json
{
  "query": "error",
  "matches": [
    {"cell": "C15", "value": "Error: invalid input"},
    {"cell": "C42", "value": "Connection error"},
    {"cell": "F7", "value": "error_log.txt"}
  ],
  "count": 3
}
```

### Formatting

```bash
agent-excel format <range> --bold    # Bold text
agent-excel format <range> --italic  # Italic text
agent-excel format <range> --underline
agent-excel format <range> --font <name>
agent-excel format <range> --size <n>
agent-excel format <range> --color <hex>
agent-excel format <range> --bg <hex>     # Background color
agent-excel format <range> --align <l|c|r>
agent-excel format <range> --valign <t|m|b>
agent-excel format <range> --wrap         # Wrap text
agent-excel format <range> --number <fmt> # Number format: #,##0.00
agent-excel format <range> --date <fmt>   # Date format: YYYY-MM-DD
agent-excel format <range> --border <style>
agent-excel merge <range>                 # Merge cells
agent-excel unmerge <range>               # Unmerge cells
```

### Tables & Named Ranges

```bash
agent-excel table create <range> <name>   # Create table from range
agent-excel table list                    # List all tables
agent-excel table delete <name>           # Delete table
agent-excel table addrow <name> <json>    # Append row to table

agent-excel name <range> <name>           # Create named range
agent-excel name list                     # List named ranges
agent-excel name delete <name>            # Delete named range
agent-excel get @TableName                # Read by name
```

### Formulas & Calculations

```bash
agent-excel calc                     # Recalculate all formulas
agent-excel calc <range>             # Recalculate range
agent-excel eval <expression>        # Evaluate expression, return result

# Common formula helpers
agent-excel sum <range>              # =SUM(range)
agent-excel avg <range>              # =AVERAGE(range)
agent-excel count <range>            # =COUNT(range)
agent-excel max <range>              # =MAX(range)
agent-excel min <range>              # =MIN(range)
```

### Charts (Basic)

```bash
agent-excel chart create <type> <data_range> <target_cell>
# Types: bar, column, line, pie, scatter, area

agent-excel chart list               # List all charts
agent-excel chart delete <index>     # Delete chart
agent-excel chart title <index> <t>  # Set chart title
```

### Validation & Comments

```bash
agent-excel validate <range> list <items>    # Dropdown list
agent-excel validate <range> number <min> <max>
agent-excel validate <range> date <min> <max>
agent-excel validate clear <range>

agent-excel comment <cell> <text>    # Add comment
agent-excel comment delete <cell>    # Remove comment
agent-excel comments                 # List all comments
```

---

## Session Management

```bash
# Multiple workbooks
agent-excel --workbook <id> <command>  # Target specific workbook
agent-excel list                       # List open workbooks
agent-excel switch <id>                # Switch active workbook
```

---

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | General error |
| 2 | File not found |
| 3 | Invalid range/cell reference |
| 4 | Sheet not found |
| 5 | Formula error |
| 6 | Permission denied (file locked) |
| 7 | Validation error |

---

## Example Workflows

### Read and analyze data

```bash
agent-excel open sales_data.xlsx
agent-excel snapshot --headers
# See: headers and data preview
agent-excel get A1:F100
# Get full data range
agent-excel find "pending" --col F
# Find pending orders
agent-excel filter F "=" "pending"
# Filter to show only pending
agent-excel sum E2:E100
# Sum the Amount column
```

### Update records

```bash
agent-excel open inventory.xlsx
agent-excel find "SKU-12345"
# Returns: {"cell": "A42", ...}
agent-excel set D42 150
# Update quantity
agent-excel set E42 "=D42*C42"
# Update total formula
agent-excel save
```

### Create report

```bash
agent-excel new monthly_report.xlsx
agent-excel sheet rename Sheet1 Summary
agent-excel set A1:D1 '["Metric","Jan","Feb","Mar"]'
agent-excel set A2:A5 '["Revenue","Costs","Profit","Margin"]'
agent-excel format A1:D1 --bold --bg "#4472C4" --color "#FFFFFF"
agent-excel format A2:A5 --bold
agent-excel formula B5 "=B4/B2"
agent-excel format B5:D5 --number "0.0%"
agent-excel chart create column B2:D4 F2
agent-excel save
```

### Batch update from JSON

```bash
# Update multiple cells from external data
agent-excel open data.xlsx
agent-excel paste A2 '[
  ["1001", "John", "john@example.com", "Active"],
  ["1002", "Jane", "jane@example.com", "Active"],
  ["1003", "Bob", "bob@example.com", "Inactive"]
]'
agent-excel save
```

---

## Implementation Notes

### Technology Stack

- **Python + openpyxl** for .xlsx manipulation
- **xlrd/xlwt** for legacy .xls support (optional)
- **Unix socket daemon** (like agent-browse) for session persistence
- **JSON protocol** for structured communication

### File Locking

- Check for lock file (~$filename.xlsx) before opening
- Create advisory lock while workbook is open
- Graceful handling of "file in use" scenarios

### Memory Management

- Large workbooks: stream reading for snapshots
- Lazy loading: don't load all sheets until accessed
- Auto-save option for long sessions

### Formula Handling

- Preserve formulas on read
- Recalculate on demand (not automatic)
- Support formula auditing (precedents/dependents)

---

## Future Considerations

- **Pivot tables** - Create and manipulate pivot tables
- **Conditional formatting** - Rules-based formatting
- **Data validation** - Complex validation rules
- **Macros** - Read/write VBA (security considerations)
- **Real-time collaboration** - Watch for external changes
- **Templates** - Create workbooks from templates
- **Diff/merge** - Compare workbooks, merge changes
