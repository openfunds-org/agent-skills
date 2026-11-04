# openfunds tools

This plugin contains practical Agent Skills and utilities for working with openfunds standards.

## Skills

### Terms and conditions (`openfunds-terms-and-conditions`)

The `openfunds-terms-and-conditions` skill creates an evidence-backed draft OFTC 2.14.0 transmission from a fund's legally binding prospectus, offering memorandum or supplement. It includes scope assessment, candidate discovery, structured validation and human-review workbook views.

Invoke it in Claude Code as:

```text
/openfunds-tools:openfunds-terms-and-conditions
```

The current version is `2.0.1` (aligned to the openfunds v2.14.0 OFTC field set). Every generated workbook is an unverified draft requiring review and approval by the fund manager or administrator before publication or operational use.
