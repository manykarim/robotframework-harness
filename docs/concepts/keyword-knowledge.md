# Keyword knowledge

The harness turns robotcode's libdoc output into local files for exactly the libraries and resources your tests
import. It works offline, and no specification is uploaded anywhere.

| file | content |
|---|---|
| `.rf/docs/<Library>.md` | one line per keyword: name and arguments. Search it: `grep -i "select option" .rf/docs/*.md` |
| `.rf/docs/<Library>.full.md` | full documentation of every keyword |
| `.rf/docs/kw/<Library>.<Keyword>.md` | one keyword's full documentation, generated **when the agent reads that path** |

- **On import.** When a test file, resource or REPL session imports a library or resource, its index and full docs
  are generated in the background. Project resources imported by path are included.
- **On failure.** The feedback names the failing keyword's doc path. In the lean profile the keyword's signature
  appears once per session; in the rich profile with every failure.
- **Search.** A local BM25 index over keyword names, argument names and the first doc sentence answers intent queries
  ("choose an option in a dropdown" → `Select Options By`). It scored hit@5 0.96 in 0.5 ms on the research benchmark.
  For comparison, rf-mcp's embedding matcher scored 0.83 in about 300 ms.

## Why files, and why the signature inline

The research measured that agents rarely open the doc files: kw-doc reads stayed low in rounds 5–7. The inline
signature on the failing line is what changes behavior. The files exist for the cases where the agent needs more,
and they cost nothing until then. Evidence: [round 2 keyword docs](../../evidence/rounds/02-local-runtime/), and the
engagement tables in rounds 5–7.
