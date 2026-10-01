# Strictly local inference; no cloud egress

The helper runs every request against a local llama.cpp server and has no code
path that sends prompts, context, or command output to a remote service. We
considered optional cloud escalation for hard requests, with redacted payloads,
and rejected it: a keypress tool that can silently leave the machine is not
auditable, and the redaction boundary would have to be trusted. Consequence: the
tool cannot fall back to a stronger model, so model choice is a hardware
decision and quality is capped by the single model that fits (see ADR-0006).
