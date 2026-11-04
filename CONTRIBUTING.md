# Contributing

This is a public repository. Do not include client documents, live fund prospectuses, personal data, credentials or internal URLs in an issue, branch, commit or pull request.

After cloning, enable the repository's pre-commit guard:

```bash
git config core.hooksPath .githooks
```

The guard blocks accidental commits of `.pdf`, `.docx` and `.xlsx` files outside a skill's `assets/` template directory.

## Adding a new skill

To scaffold a new skill inside `plugins/openfunds-tools/skills/`:

```bash
python3 scripts/scaffold_skill.py \
  --name openfunds-<skill-name> \
  --description "Concise third-person description of what the skill does and when to use it."
```

Each skill follows the portable Agent Skills standard:

```text
plugins/openfunds-tools/skills/<skill-name>/
├── SKILL.md          # Required: YAML frontmatter (name, description, compatibility, metadata) + instructions
├── scripts/          # Optional: deterministic Python/shell utilities
├── reference/        # Optional: schemas, mapping guides and reference docs
├── assets/           # Optional: official blank openfunds Excel templates
└── tests/            # Optional: unit tests (auto-discovered by CI)
```

## Updating an existing skill

1. Create a feature branch from `main` (for example, `git checkout -b feat/update-oftc`).
2. Make your changes and update the version and `CHANGELOG.md` in `plugins/openfunds-tools/`.
3. Run the structural validator and unit test suite locally:
   ```bash
   python3 scripts/validate_plugins.py
   python3 -m unittest discover -s plugins/openfunds-tools/skills/openfunds-terms-and-conditions/tests -v
   ```
4. Open a pull request against `main` for review and approval by the repository maintainers.
