# One model; no deep tier

The deep keybinding (`Alt-:`) runs the same model as suggest with a larger token
budget instead of a second, larger model. We originally planned a 32B on a
second port, CPU-only. On a 16 GB-VRAM card the always-on suggest model already
holds about 9 GB, so an 18.5 GB 32B cannot coexist, and every option was slow
(CPU-only, ~3-6 tok/s), VRAM-juggling, or another multi-gigabyte download.
Considered: a 24B that fits (~25-30 tok/s but still evicts suggest) and a hybrid
32B with partial offload (~8-14 tok/s). Consequence: quality is capped by the
single model that fits, and `Alt-:` buys more thinking tokens, not a stronger
model. Supersedes the deep-tier part of ADR-0001.
