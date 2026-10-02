# Common-mode terms check

Read on **2026-10-02**. This records the sources and implementation decision; it is
not a legal opinion. Recheck before the owner approves any distribution.

## OpenCode software and redistribution

The isolated, installed `opencode-ai@1.18.34` npm package declares `MIT`; its
`LICENSE` is byte-for-byte identical to the matching GitHub tag, including
`Copyright (c) 2025 opencode`. Sources:
[npm metadata](https://registry.npmjs.org/opencode-ai/1.18.34),
[npm package archive](https://registry.npmjs.org/opencode-ai/-/opencode-ai-1.18.34.tgz),
[pinned source license](https://github.com/anomalyco/opencode/blob/v1.18.34/LICENSE).
All read 2026-10-02. The license permits redistribution, modification and sale,
subject to its notice condition: “The above copyright notice and this permission
notice shall be included”. Ship the **complete** license, including its warranty
disclaimer, alongside every engine copy; `THIRD_PARTY_NOTICES.md` does that.
MIT does not require publishing our source or changes, nor paying OpenCode.
Dependencies retain their own licenses. The native platform npm package itself
has no LICENSE file or license metadata; we identify the engine's grant from the
matching source and umbrella npm package rather than inventing a platform license.
A future redistributable bundle needs an audit of all bundled dependency notices.

OpenCode's [service terms](https://opencode.ai/legal/terms-of-service), effective
2026-08-15, read 2026-10-02, distinguish hosted services from the local software:
“such license and terms will exclusively govern your use of such open source
software”. This wrapper does not enable Zen, Go or hosted inference.

## Name and logo

OpenCode's [brand page](https://opencode.ai/brand), read 2026-10-02, describes
“Resources and assets to help you work with the OpenCode brand.” It offers assets
but no explicit blanket trademark license or third-party naming permission in
its published text. MIT licenses software; it does not expressly grant trademarks.

**Decision/inference:** truthful, plain-text attribution such as “AI4Science,
built on OpenCode” is appropriate descriptive attribution, without claiming
endorsement. This is our interpretation, not an explicit upstream permission.
Owner/counsel must resolve jurisdiction-specific trademark questions and obtain
permission for any promotional logo use. Under the owner's rule, **do not put
OpenCode in our product/company/feature name or our logo**, copy its logo as ours,
or imply that Anomaly built, sponsors, endorses or partners with AI4Science.
The product and command are AI4Science / `ai4science`. The unmodified engine may
still display its own name/wordmark as upstream attribution; configuration does
not provide a complete UI rebrand. There is no AI4Science logo asset in this job.

## Claude Pro/Max subscription login

[Anthropic Consumer Terms](https://www.anthropic.com/legal/consumer-terms), effective
2025-10-08, read 2026-10-02, prohibit unpermitted access “through automated or
non-human means”, with exceptions for API keys or explicit permission. Its
[Claude Code legal/authentication guidance](https://code.claude.com/docs/en/legal-and-compliance),
read 2026-10-02, is explicit: “Anthropic does not permit third-party developers to
offer Claude.ai login into their own applications”. It also prohibits routing
users' Free/Pro/Max credentials and collecting/intermediating their session tokens.

**Allowed:** the user's own Anthropic API key under the applicable commercial
terms, or a supported inference provider credential. Anthropic separately allows
users to sign in to the unmodified **Claude Code** binary under its stated hosting
conditions. That exception does not authorize OpenCode or AI4Science to use Claude
subscription OAuth. **Not allowed for this wrapper:** offering Pro/Max login,
importing Claude Code tokens, or spoofing its client. **Unclear:** a different
contractual arrangement requires Anthropic's written permission and owner/counsel
review. The common-mode defaults disable upstream login plugins and do not add
any Claude subscription integration.

## ChatGPT subscription login

OpenAI's [official integration guidance](https://developers.openai.com/cookbook/articles/sign-in-with-chatgpt),
published 2026-09-28, read 2026-10-02, describes ChatGPT plan usage as “available
for open-source tools and personal projects that run locally”. It describes user
consent, app registration, issued client IDs and granted plan-usage scopes for
eligible Plus/Pro users. Paid or remotely hosted apps must request access before
offering it. **Allowed in principle:** a qualifying local open-source AI4Science
integration using that authorized flow, subject to its terms and granted scopes.
Identity login alone does not grant model usage, conversation access or an API key.

[OpenAI Terms of Use](https://openai.com/policies/row-terms-of-use/), effective
2026-01-01, read 2026-10-02, say: “You may not share your account credentials or
make your account available to anyone else”. They also restrict programmatic
extraction and circumventing limits; the documented authorized integration is
not a blanket permission to scrape ChatGPT, reuse another app's OAuth identity,
resell subscriptions, or bypass safeguards. API use has separate commercial terms.

**Not implemented:** ChatGPT subscription login in this packet. We have not
validated that the pinned engine's built-in Codex login meets the new integration
requirements when distributed under our name. **Owner/counsel review needed:**
AI4Science eligibility, client registration/branding, the relationship to paid PWM
features, and any commercial or hosted edition. Use the user's own API key or
local endpoint meanwhile; do not silently reuse their global OpenCode auth.
