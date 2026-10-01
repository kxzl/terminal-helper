# llama.cpp as the inference backend

We use llama.cpp's `llama-server` rather than Ollama or a Python inference
stack. Reasons: first-class Vulkan support for the RDNA2 GPU, schema-constrained
decoding, and a single self-contained binary that is portable across distros. We
talk to it over its OpenAI-compatible HTTP API so the transport stays swappable,
but no other runtime is supported. Considered: Ollama (easier model management,
weaker control of the backend) and vLLM (poor ROCm-on-RDNA2 story).
