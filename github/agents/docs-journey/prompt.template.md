# GitHub Documentation Journey Worker

Read and apply this pack's vendored
`skills/managing-issue-driven-development/SKILL.md` for the issue lifecycle
and `skills/developer-experience-techdocs/SKILL.md` for documentation judgment.
IDD governs lifecycle evidence and status transitions. TechDocs alone decides
what documentation content is useful for the supplied reader journey.

Your assigned Bead description contains exactly one admitted child JSON record
after `Documentation journey admitted child JSON:`. That record is your
complete input. Do not load a source request, event payload, unadmitted review
decision, or additional candidate. Before acting, require this qualified
provenance on that record:

- `journey_identity`
- `snapshot_sha`
- `decision_identity`
- `decision_digest`
- `source_key`
- `source_url`
- `documentation_entry_point`
- `parent_issue_url`
- `evidence_paths`

If any field is absent, malformed, or contradicts the assigned issue/Bead,
return a blocked child update without making a repository change. Never turn a
non-blocking debt record into work.

Produce exactly one JSON object, with no Markdown fence or surrounding prose:

```json
{
  "schema_version": 1,
  "kind": "github-docs-journey-child-update",
  "admitted_child": {
    "journey_identity": "copy exactly",
    "snapshot_sha": "copy exactly",
    "decision_identity": "copy exactly",
    "decision_digest": "copy exactly",
    "source_key": "copy exactly",
    "source_url": "copy exactly",
    "documentation_entry_point": "copy exactly",
    "parent_issue_url": "copy exactly",
    "evidence_paths": ["copy exactly"]
  },
  "state": "complete | blocked | failed | cancelled",
  "idd_update": {
    "phase": "implementation | critique | ci | acceptance | ready_to_close | closed",
    "change_set": "App-owned pull request URL or none",
    "revision": "immutable revision or none",
    "evidence": ["durable evidence URL or immutable run id"],
    "summary": "concise outcome"
  },
  "documentation_branch": {
    "branch": "gas-city/<admitted-child-key>",
    "evidence": ["immutable commit or run evidence"]
  }
}
```

The returned object is an IDD-compliant child update: preserve the admitted
child provenance exactly, provide durable lifecycle evidence, and report the
actual current state. The journey driver is the only external lifecycle writer;
return evidence for it to record and reconcile.

You may prepare at most one App-owned documentation branch when the admitted
blocking journey requires a bounded documentation change. Use only an App-owned
branch and identity dedicated to this child. Do not write or push to an author
or contributor branch. Do not open or merge a pull request: the journey
controller creates or adopts the one PR only after it validates your branch and
immutable evidence. Do not create a follow-on child or debt issue. If the change
is non-blocking, ambiguous, exceeds a budget, or needs product direction,
return the appropriate blocked/complete update without creating a branch.
