# Model Catalog (current defaults)

TC's default architecture is a two-tier router.

## Primary — Qwen3.8-27B

Provider-agnostic configuration; the included default is the OpenRouter-compatible model id `qwen/qwen3.8-27b`.

Current public OpenRouter listing shows 1M context, tool calling, and current pricing of $0.15/M input and $2/M output. The official Qwen Hugging Face repository lists the Apache-2.0 model and vLLM/Transformers compatibility.

Sources:
- https://openrouter.ai/qwen/qwen3.8-27b
- https://huggingface.co/Qwen/Qwen3.8-27B

## Higher — GPT-6 Astra

Configured through the OpenAI Responses API as `gpt-6-astra`. OpenAI's current model documentation lists a 1,050,000-token context window, 128,000 maximum output tokens, and standard API pricing of $10/M input and $50/M output.

Sources:
- https://developers.openai.com/api/docs/models/gpt-6-astra
- https://developers.openai.com/api/reference/cli/resources/responses/methods/create

Higher-brain routing is intentionally opt-in and budget-limited in TC.
