# Terms and brand check

Read 2026-09-28. This is a product research summary, not legal advice; obtain owner or counsel review before distribution.

## OpenCode software license

The current OpenCode source tree and npm package identify as MIT. The license permits use, modification and redistribution, including commercially, provided copies and substantial portions retain the copyright and permission notice. The source states, “The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.” We include the notice in `THIRD_PARTY_NOTICES.md`. Source, read 2026-09-28: [github.com/anomalyco/opencode/blob/dev/LICENSE](https://github.com/anomalyco/opencode/blob/dev/LICENSE); package metadata, read 2026-09-28: [npmjs.com/package/opencode-ai](https://www.npmjs.com/package/opencode-ai) (MIT). The npm package downloads a platform-specific executable package, so before each distribution we must inspect that package's notices and preserve any additional notices it supplies.

## Name and logo

OpenCode's project documentation says: “If you are working on a project that's related to OpenCode and is using ‘opencode’ as part of its name … please add a note to your README to clarify that it is not built by the OpenCode team and is not affiliated with us in any way.” Source, read 2026-09-28: [OpenCode project README](https://github.com/anomalyco/opencode). OpenCode's [brand page](https://opencode.ai/brand), read 2026-09-28, publishes brand assets but does not state a grant for third-party logos. We can use the factual compatibility statement “Built on OpenCode” in descriptive copy, with a clear non-affiliation statement. AI4Science remains the product and command name; do not use “OpenCode” in the product name, product logo, or imply endorsement. Do not use OpenCode's logo or brand artwork as ours. Any prominent co-branding or use beyond nominative factual text needs owner/counsel review.

## Claude Pro/Max login

Anthropic's consumer terms, effective October 8, 2025, say users may not access consumer Services “through automated or non-human means, whether through a bot, script, or otherwise,” except through an Anthropic API key or where Anthropic explicitly permits it (section 3.7): [Consumer Terms](https://www.anthropic.com/legal/consumer-terms), read 2026-09-28. Anthropic separately documents that Pro/Max access is through its own Claude Code client: [Using Claude Code with your Pro or Max plan](https://support.anthropic.com/en/articles/11145838-using-claude-code-with-your-pro-or-max-plan), read 2026-09-28.

**Decision for AI4Science:** do not offer Claude Pro/Max subscription OAuth or reuse its credentials in this third-party wrapper. Use a customer's Anthropic API key only under the applicable commercial/API terms. The exact boundary for user-driven use of third-party clients is not described in a dedicated integration grant; ask Anthropic and counsel before changing this stance.

## ChatGPT subscription login

OpenAI's current individual Terms of Use prohibit “automatically or programmatically extract[ing] data or Output” and require use of its name/logo under its brand guidelines (sections Using our Services and Our IP rights): [Terms of Use](https://openai.com/policies/terms-of-use/), read 2026-09-28. OpenAI documents subscription login for its own Codex CLI, not as a general third-party login facility: [Codex CLI and Sign in with ChatGPT](https://help.openai.com/en/articles/11381614-api-codex-cli-and-sign-in-with-chatgpt), read 2026-09-28.

**Decision for AI4Science:** do not implement ChatGPT account OAuth, extract/reuse ChatGPT credentials, or route subscription usage through AI4Science. A user's OpenAI API key is a separate API product and may be used subject to its API terms. The public terms do not expressly settle every possible third-party OAuth client scenario, so any proposed ChatGPT subscription integration needs written OpenAI clarification and owner/counsel approval first.
