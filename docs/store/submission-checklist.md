# Submission checklist and declaration worksheet

Prepared 2026-11-14. This is a worksheet, not a signed declaration or a record
of completed Console actions. The maintainer asked to prepare the app and
listing while Google verifies the account. No external inquiries are to be sent.

## Readiness areas

| Area | Completion evidence needed |
| --- | --- |
| Code and user flows | Reviewed source, automated results and observed tests of installation, sessions, input, preview, language and data deletion; correct operator information and disclosures |
| Build and release artifacts | Exact candidate hashes, signing identity, corresponding source/notices, real screenshot manifest and GitHub release assets that match the reviewed candidate |
| Play account and store | Google identity approval, required phone/device checks, accurate trader declaration, listing fields, content forms, testing track and production-access requirements |
| Operator and distribution decisions | Actual external-service terms basis and remaining license/runtime-policy determinations; explicit approval of required legal commitments, never inferred from a passing test |

Keep these results separate. Publish matching reviewed source and notices to
the canonical GitHub release. A GitHub source prerelease, account approval or
successful CI run alone does not approve an app binary for Play distribution.

## Known product inputs

| Console topic | Prepared input | Basis / limit |
| --- | --- | --- |
| App type | App | Local development terminal |
| Language | English (United States) primary; Korean optional | User preference and app implementation |
| Category | Tools, proposed | Confirm available category and tags in Console |
| Pricing | Free | Z8-specific user instruction |
| Ads | No, subject to final dependency verification | No ads in the stated product scope or published privacy policy |
| In-app products | None | No in-app purchases in the stated Z8 scope; provider charges are separate |
| Privacy policy | Public URL in `README.md` | Recheck reachable, current and consistent with final build |
| Z8 account creation | None | External CLI sign-in does not create a Z8 account |
| Access | Core local terminal works without a Z8 account; external clients may require provider accounts | Do not answer “all functionality unrestricted” without disclosing external restrictions |
| Foreground service | `specialUse` | `tools/prepare-app.py`; final AAB manifest and device behavior still govern |

## Data safety — review required before answering

The presence of no Z8 backend is not enough to answer “no data collected.”
Google's definition covers off-device transmission by third-party code too;
local-only processing is treated separately. An applicable user-directed
sharing exception does not automatically remove collection disclosure.
[Official Data safety guidance](https://support.google.com/googleplay/android-developer/answer/10787469?hl=en).

| Data flow | Current implementation / policy description | Outstanding classification |
| --- | --- | --- |
| Project files, shell history, settings and CLI credentials | Stored in app/project storage; project deletion removes its HOME and files | Check final build and any selected tool's extra storage paths |
| Notifications | Local event type/time and project/session identifiers; no original prompt copied into records | Confirm final code and retention behavior |
| Environment/tool downloads | Requests reach distribution servers, including request information and IP address | Identify provider retention and any required data-type disclosures |
| Optional Codex/Claude Code and other tools | User-installed code may send prompts, source code, output, diagnostics and credentials to external services | Evaluate actual pinned/current tool versions and defaults; no final “no collection” assertion |
| Built-in preview | Local cookies/storage/cache; page code can contact external servers | Distinguish controlled sample/content from user-directed web content |
| External browser / support email | Browser/provider handles sign-in; support messages go to the operator's email service | Apply the form's scope and user-directed-transfer criteria accurately |

Pending answers: data types, collection/sharing purposes, optional/required
status, encryption in transit across the declared flows, and deletion-request
options. Do not claim all user-run commands use encrypted transport. Do not
claim that deleting a local project deletes an external provider account.

## Other declarations that still need an actual Console review

- Target age groups: not chosen. The developer-tool use case does not by itself
  determine a legal age cutoff. Do not select children or an adult-only audience
  merely to bypass another form.
- Content rating: complete the IARC questionnaire using actual functionality,
  including relevant user-generated or web-access capabilities. Do not invent
  a rating or reuse a rating from a different app.
- Generative-AI applicability: explain that Z8 runs optional external CLIs and
  does not offer a hosted model/chat service. Do not treat that description as
  a ruling on Google's policy classification.
- Health, financial, news, government, VPN and other special declarations:
  answer the actual Console questions against the final app. The stated Z8
  product is a general development terminal; this worksheet does not submit
  those answers.
- Trader status: account-level declaration must match the maintainer's real
  business activity, with any app-level confirmation completed afterward.
  Z8 being free does not determine this answer.
- Foreground service: use the factual draft in `review-notes.txt`, verify user
  start/stop and notification behavior, and attach a video of the actual flow.
  [FGS requirements](https://support.google.com/googleplay/android-developer/answer/16559646?hl=en).

## Release sequence

- [ ] Google finishes account identity verification and required contact/device
  verification and declarations are complete.
- [ ] Final candidate uses the intended public operator/contact information.
- [ ] App tests and images are tied to that candidate, with actual results
  retained; earlier rc3 evidence is not automatically evidence for a changed build.
- [ ] Complete the distribution decisions and corresponding-source review
  recorded in [`DISTRIBUTION_REVIEW.md`](../DISTRIBUTION_REVIEW.md)
  and [`RELEASE_LICENSES.md`](../RELEASE_LICENSES.md).
- [ ] Produce a properly signed upload AAB through the release procedure. An
  unsigned candidate or development-signed test APK is not an upload-ready release.
- [ ] Create the Console app, select the primary language and fill in the listing.
- [ ] Upload the real icon, feature graphic and verified screenshots.
- [ ] Complete App access, privacy/Data safety, rating, target audience and
  applicable permissions/declarations using reviewed answers.
- [ ] Perform Play test-track validation and address pre-launch report findings.
- [ ] Complete the new-personal-account closed test: at least 12 testers opted
  in continuously for at least 14 days, then apply for production access. Record
  genuine feedback and changes; local tests do not replace this requirement.
  [Current personal-account test requirements](https://support.google.com/googleplay/android-developer/answer/14151465?hl=en).
- [ ] Submit the release for review and confirm its actual publishing state.

Account verification, local QA, source publication and Play app approval are
separate results. This preparation does not mark any unperformed stage complete.
