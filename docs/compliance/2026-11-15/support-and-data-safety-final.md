# Support processing and Data safety: bounded final assessment

Reviewed November 15, 2026 for the published rc7 behavior. This supplements,
rather than rewrites, the earlier rc6 [privacy review](privacy-review.md).
No mailbox, account settings, app binary or Play declaration was changed.
This is an evidence-based assessment, not a regulator's decision or worldwide
legal clearance.

## 1. Ordinary support: a concrete processing basis

The actual scope is a free local terminal, an optional support address, ordinary
consumer Gmail and no automatic forwarding. The operator uses an address and
the minimum technical question/replies needed to answer the sender. There is
no support marketing, profiling, account registration or requested identity
document in this workflow. The existing rule is handling time plus 90 days
after resolution, with earlier deletion requests and permanent deletion of
operator-controlled copies. See the [manual procedure](support-retention.md).

For this limited collection/use, this assessment supports **PIPA Article
15(1)(6), legitimate interests**, rather than requiring a fictitious paid
support contract or treating an unsolicited email as statutory consent. The
assessment follows purpose, necessity and balancing; the law also requires a
substantial relationship to the interest and a reasonable scope. The
[PIPC explanation of that test](https://pipc.go.kr/np/cop/bbs/selectBoardArticle.do?bbsId=BS210&mCode=C020020000&nttId=10665)
describes it in an AI guidance context; it is used here only for the general
test, not as a ruling about Z8 or Gmail. The applicable basis is in
[Article 15](https://www.law.go.kr/LSW/lsLinkProc.do?joLnkStr=%EC%A0%9C15%EC%A1%B0&lsNm=%EA%B0%9C%EC%9D%B8%EC%A0%95%EB%B3%B4%EB%B3%B4%ED%98%B8%EB%B2%95&mode=11).

| Test | Application to this workflow |
| --- | --- |
| Legitimate purpose | Answer a request the sender initiated and resolve a problem with Z8. The sender and operator share that immediate purpose. |
| Necessity | A reply address and enough technical detail are needed for an individual answer. An alias and redacted/minimal reproduction suffice; a legal name, phone, credentials or a whole private repository are not needed. |
| Balance | A sender reasonably expects a response and a short follow-up record. Use is limited to that case; it does not affect access to the offline terminal. Early deletion/cessation is available. The 90-day follow-up period is bounded, not indefinite retention for possible future marketing. |
| Limits | Do not request sensitive data, government identifiers or credentials. Remove irrelevant personal material from working copies and do not retain unnecessary attachments. If a particular case needs different data or use, assess that case separately; this basis does not authorize it automatically. |

This closes the generic “no support collection/use basis selected” item for
the described practice. It **does not supply a separate overseas-transfer
basis**. Likewise, Article 15(1)(4)'s contract route is not the only possible
collection basis, but a free app does not by itself prove every storage
arrangement is contractually necessary.

The public policy now identifies the operator's privacy/support responsibility
and published email. Do not invent a separate legal entity or staffed privacy
department, or publish a home address, identity document or private phone
number from account verification. [Article 30](https://law.go.kr/lsLinkCommonInfo.do?chrClsCd=010202&lsJoLnkSeq=1034056209)
requires responsible contact information; [Article 31](https://www.law.go.kr/lsLinkCommonInfo.do?chrClsCd=010202&lsJoLnkSeq=1034292993)
addresses responsibility, including the owner/representative where its small
operator exception applies. No unverified appointment, corporate status or
employee count is asserted here.

## 2. Gmail: the remaining issue is specific

Established recipient: Google LLC's consumer Gmail, under the
[Korean consumer terms](https://policies.google.com/terms?hl=ko&gl=kr).
Google's [Korean privacy policy](https://policies.google.com/privacy?hl=ko)
includes received email content, worldwide processing and the privacy contact
`googlekrsupport@google.com`. Its US entity address is not a mailbox-location
guarantee. No Workspace addendum, region election, delegation or undisclosed
forwarding configuration was inferred or inspected.

The operator-controlled particulars are already concrete:

| Particular | Current evidence |
| --- | --- |
| Data | Reply address, technical inquiry, voluntarily supplied relevant attachments and replies; no request for sensitive data or credentials. |
| Purpose | Receive, store and answer that inquiry, including short follow-up. |
| Timing and method | When email is delivered/replied to, followed by mailbox storage through Google's network service. No automatic forwarding. Do not promise that every sender's SMTP hop is TLS. |
| Operator retention | Until resolved, then 90 days; earlier deletion/cessation requests through the same contact. |
| Provider retention | Google's separate deletion/backup process; no claim of complete provider erasure at the operator deadline. |
| Choice and consequence | Do not send a support email, or request cessation/deletion. The offline terminal remains usable; individual email support needs a reply address and question. |
| Country scope | **Not established for this consumer mailbox.** Neither “US only” nor a list of all Google facilities is supported as the actual processing-country list. |

[Article 28-8(1)](https://www.law.go.kr/LSW/lsLinkCommonInfo.do?chrClsCd=010202&lsJoLnkSeq=1029334743)
has multiple transfer routes. Necessary contract-related outsourcing/storage
with notice may be one; separate consent is another.
[The required particulars](https://www.law.go.kr/LSW/lsLinkCommonInfo.do?lsJoLnkSeq=1033215841)
include destination countries. No reviewed official text supplies a consumer
Gmail exception allowing this field to be replaced by an unspecified worldwide
scope. A checkbox or the operator's acceptance of Google's terms does not
invent the sender's transfer consent or the missing country facts. This review
also did not establish a qualifying certification/adequacy route for this exact
arrangement. An EU/US privacy framework is not automatically Korean approval.

The [PIPC distinction](https://pipc.go.kr/np/default/page.do?mCode=D060040000)
between a foreign service's direct collection and an operator's transfer is
relevant, but not an exemption for all operator-selected overseas storage.
The sender's initial email may be delivered directly to Google; continued
operator mailbox storage and replies must still be assessed. Conversely,
users' own CLI-provider accounts do not automatically make those providers
the Z8 operator's processors.

**Finite unresolved item:** applicable country particulars and a supported
Article 28-8 route for the actual Gmail storage arrangement. The generic
collection/use, retention and purpose issues above are not still open.
No universal traffic audit or lawyer's signature is substituted for evidence.
Available public consumer-service documents did not close this item. The user
cannot cure it by guessing a country. No vendor inquiry, purchase or provider
migration is authorized by this assessment; none occurred. Keep this limitation
visible before representing Korean support-processing compliance as complete.

## 3. App collection is not the same as operator correspondence

`Z8AboutActivity.email()` creates an `ACTION_SENDTO` intent containing only the
public `mailto` destination. It attaches no subject/body, logs, files or user
identifier and does not read the email subsequently composed in the external
mail app. Therefore ordinary external support correspondence is **outside
this app's collection declaration** on these facts. The privacy policy still
covers it because the operator receives and processes it. A future in-app
support form or attached diagnostic export would need reassessment.

The local shell and offline preparation do not send project contents. Supported
Codex/Claude task execution does send data from the app environment, even when
the operator never receives it. The cloud-backup exception for an app that
never accesses the uploaded data is not a sound blanket exemption here: Z8
handles terminal input and project files, and runs these clients. The
[Console worksheet](../../store/play-console-data-safety.md) now contains
specific draft choices instead of a request to audit every possible command.

## 4. WebView and system services: narrow interpretation

The [official form guidance](https://support.google.com/googleplay/android-developer/answer/10787469?hl=en)
exempts system-service apps themselves from completing a form. It does not
expressly exempt every ordinary app that uses a platform component. Its
open-web exception concerns page data where the app does not control that
content; it is not an express exclusion for native crash reports.

The [WebView reporting specification](https://developer.android.com/develop/ui/views/layout/webapps/webview-privacy)
describes app-associated crash stacks and a per-app pseudonymous 128-bit crash
token, conditioned on the user's Google diagnostics choice. The manifest
opt-out removes usage statistics, not those crash reports. This supports
including **Crash logs** and **Device or other IDs** for Z8's instantiated
WebView in the draft, for analytics, as optional. This is a reasoned application
of the third-party-code rule, not an explicit Google ruling on Z8. It does not
include unrelated Android, Play Store, browser or device-wide telemetry.
There is no need to manufacture a crash or inspect private reports to describe
the documented capability. The stock Chromium Android
[uploader uses HTTPS](https://chromium.googlesource.com/chromium/src/+/b4fb8097f2d5bd6acf4087a12db20141cec5f76e/components/minidump_uploader/android/java/src/org/chromium/components/minidump_uploader/MinidumpUploadCallable.java);
that source does not attest every vendor's custom WebView binary.

## 5. Scope of the prepared answers

The draft covers the official supported CLI versions/default endpoints,
ordinary task/file/image input, documented diagnostics and the managed app
paths. Existing [versioned provider evidence](follow-up-provider-data.md) is
sufficient for that bounded declaration; a complete packet inventory of every
user-installed program is not a prerequisite. External account creation,
provider-only payment details, unrelated browser activity and optional
integrations the user independently adds are not automatically Z8 collection.

Revisit the relevant row when a managed client update changes a data practice,
Z8 adds a transmitting feature, a supported endpoint changes, or another active
Play version has different behavior. Publishing an exact declaration still
requires entering it for the actual submitted build; this document does not
claim that Console submission or Google review occurred.
