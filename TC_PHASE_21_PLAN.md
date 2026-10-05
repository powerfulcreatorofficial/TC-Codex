# TC Engineering AI — Phase 21 Plan
## Native Higher-Brain Responses Adapter

### Goal
Allow the higher brain to use OpenAI Responses API semantics for structured tool calling while preserving TC's internal Brain protocol.

### Implemented
- Added `OpenAIResponsesBrain`.
- Converts TC chat/tool schema into Responses API function tools and `function_call_output` items.
- Parses function calls and assistant text back into TC's existing `BrainResponse`.
- Added tool-call correlation IDs to `ChatMessage`.
- Higher brain defaults to Responses protocol.
- Responses requests set `store=false` because TC already owns task transcript state.

OpenAI's current GPT-6 Astra guidance says tool calling requires the Responses API, while Astra remains available through the model's supported API surface.
