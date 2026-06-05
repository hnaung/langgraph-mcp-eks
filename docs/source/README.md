# Source Documents

This folder holds original source documents (Word, PDF) that accompany the markdown documentation in the parent `docs/` folder.

## Expected Files

| File | Markdown equivalent |
|---|---|
| `AI_Platform_Security_Architecture_Proposal.docx` | [../AI_PLATFORM_SECURITY_ARCHITECTURE_PROPOSAL.md](../AI_PLATFORM_SECURITY_ARCHITECTURE_PROPOSAL.md) |

## Adding the Original Proposal

To include your prepared Word document in the repository:

```bash
cp ~/Downloads/AI_Platform_Security_Architecture_Proposal.docx docs/source/
git add docs/source/AI_Platform_Security_Architecture_Proposal.docx
git commit -m "Add original security architecture proposal source document"
```

The markdown version in `docs/AI_PLATFORM_SECURITY_ARCHITECTURE_PROPOSAL.md` is the version-controlled, GitHub-readable equivalent. Keep both in sync when updating the proposal.

> **Note:** Binary `.docx` files are included for audience distribution (presentations, formal reviews). The markdown version is the canonical reference for developers browsing the repo.
