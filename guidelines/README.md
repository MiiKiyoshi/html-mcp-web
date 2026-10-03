# Guidelines

Content conventions for presentation material. Each package lives at
`guidelines/<name>/GUIDELINE.md`. Related references, fixtures, and scripts stay in the
same package when they exist. Page geometry belongs to template documentation. Shared
components and production procedures belong to `templates/COMPONENTS.md`.

Public packages belong in this directory. User-owned packages belong under
`~/.config/html-mcp-web/guidelines/<name>/` and remain outside the repository.

## Amending a guideline

Review each proposed rule against the whole guideline before accepting it. State the reader failure it prevents and ask whether an existing rule already resolves that failure. A new case alone does not justify a new rule.

Give each rule one home, defined by its application condition and required action. Merge repeated instructions only when their conditions and behavior remain intact. State where each merged instruction survives and check for meaning lost in the merge. Keep distinct actions distinct even when they concern the same topic.

Write conditions and actions that apply beyond the originating example. Preserve the reader need behind an explicit requester instruction. Obtain authorization before weakening or changing that instruction, even when it prescribes a particular technique. Do not turn a technique into a universal requirement without a reason.

Keep content rules in the guideline and production procedures in the shared template documentation that authors are instructed to read. Name the actual destination before moving a rule. Automated detection does not remove the underlying obligation or cover untested cases.

Accept wording only if an author can tell when the rule applies and what to do. Test whether removing each added sentence loses a needed instruction. Use length targets to find repetition, not to justify loss of meaning. Preserve named requirements referenced by other guidelines or update their references in the same change.

Read the revised guideline and connected documentation as an author would. Check for contradictions, orphaned references, ambiguous exceptions, and missing obligations. Record the mapping and change rationale outside the reader-facing guideline.
