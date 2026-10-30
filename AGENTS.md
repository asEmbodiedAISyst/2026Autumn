# Course media and GitBook sync

All course media have one authoritative location: `2026-autumn/resources/`, organized by class. Do not add a root `resources/`, a separate `media/` tree, or `.gitbook/assets/` copies.

Static course illustrations are PNG. Keep worksheet PDFs as PDFs, and retain required videos and GIF animations. Figure-generation source and private preparation notes belong in the private Assistants repository, not this public course repository.

## GitBook MCP authoring

- Before editing, read the latest GitHub main and the current GitBook revision; wait for any active Git Sync import/export to complete.
- Preserve canonical external image URLs exactly, including their URL encoding. Use `https://raw.githubusercontent.com/asEmbodiedAISyst/2026Autumn/main/2026-autumn/resources/<class>/<path>` for embedded repository images. Use existing links for PDFs, datasets, code packages and videos.
- Do not re-upload existing media with `insert_files`, substitute `/files/<id>` references for canonical image URLs, or paste image bytes into GitBook. Those paths can make GitBook export duplicate copies under `.gitbook/assets/`.
- Before merging an MCP-authored change request, inspect its file library as well as its pages. The resources-only baseline has no retained upload records. GitBook exports unused library files too: canonical page URLs alone do not prevent old uploads from returning. If records reappear, reconcile them against resource hashes and remove only verified unused copies in a reviewed change request before publishing.
- Add new images to their class resources directory through GitHub first, then reference their canonical public URL. Preserve relative course-page links and their anchors.
- Published changes use a change request. Read back the persisted page before merging, preserving text, captions, equations, tables, page IDs and slugs. After merging, wait for successful export and inspect its complete paginated diff and recursive tree.
- Run `python3 .github/scripts/check_course_resources.py` before committing and after GitBook exports. A failed check requires correction; do not bypass it by deleting links or removing content.
- Do not use `.gitignore` as an export control: GitBook can commit assets independently of a local Git checkout.

These instructions govern repository maintenance, not student learning activities. The workflow only checks files; it does not delete, relocate, or auto-commit them.
