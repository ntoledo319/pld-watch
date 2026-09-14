# pld-watch

**Which components you ship can no longer receive security updates?**

On **9 December 2026** the EU's new Product Liability Directive — Directive (EU) 2024/2853 —
starts applying to products placed on the EU market. It replaces the 1985 directive, and the
change that matters to software teams is simple:

> **Software, SaaS and AI systems are "products".**

Liability is **no-fault**. A claimant does not have to prove you were negligent — only that the
product was defective, that they suffered damage, and that one caused the other. The directive
also narrows the old "the defect appeared later" defence where the manufacturer keeps control of
the product through updates, and it treats the **failure to supply the security updates needed to
keep a product safe** as something that can evidence defectiveness.

So one question becomes worth asking deliberately, before December:

> Of everything I ship, what can no longer receive a security update at all?

That is what `pld-watch` answers. It reads the runtimes and frameworks a project actually declares
and checks each one against the public [endoflife.date](https://endoflife.date) catalogue.

```
  2 COMPONENT(S) PAST UPSTREAM END-OF-LIFE

    Node.js 16   (.nvmrc)
      upstream EOL   2023-09-11   latest supported: 26
    next 12.3   (package.json)
      upstream EOL   2022-11-21   latest supported: 16
```

## Install

No account, no signup, no API key, no telemetry. Standard library only — Python 3.9+.

```bash
curl -fsSL https://raw.githubusercontent.com/ntoledo319/pld-watch/main/pld_watch.py -o pld-watch
chmod +x pld-watch
./pld-watch scan
```

## Use

```bash
pld-watch scan                    # scan the current directory
pld-watch scan /path/to/project   # scan somewhere else
pld-watch scan --json             # machine-readable, for CI
pld-watch clock                   # days until the PLD applies
```

**Exit codes:** `0` nothing past end-of-life · `1` at least one component past EOL ·
`2` nothing detectable to check.

## What it reads

`.nvmrc` · `.python-version` · `go.mod` · `package.json` (`engines` + known frameworks) ·
`requirements.txt` / `requirements-dev.txt` · `Dockerfile` `FROM` lines.

Version ranges are handled the way people actually write them — `^12.3.1`, `~3.2`, `>=16 <18`,
`v1.19`, `3.7-slim`.

## Scope, plainly

`pld-watch` checks whether a **declared runtime or framework version is past its upstream
end-of-life date**. That is one narrow, checkable fact.

It does **not** tell you whether your product is defective, whether you are liable, whether you are
in scope of the directive, or whether an EOL component is actually reachable or exploitable in your
system. It does not scan your own source, does not read binaries or container images, and only
knows the frameworks in its map. Those are real gaps and you should know about them rather than
discover them.

**Whether a product is defective is decided by a court on the facts — not by a scanner.**

## From a scan to a defensible record

The scan tells you what is past end-of-life. It does not tell you whether you are in scope, what
the directive actually requires, or how to keep a record that you can and do supply security
updates.

If that is the part you need, there is a paid kit — six documents, ~18,500 words, plus a 64-page
PDF: a scope decision tree (including the free-and-open-source carve-out), what changed from the
1985 regime, an update-supportability evidence practice, copy-paste policy templates, and a
two-page board brief. **$149 single-organisation, $490 consultancy licence.**
<https://cra.toledotechnologies.com/pld/>

It is not legal advice and says so throughout. Where a question needs a lawyer it says that
instead of guessing — there are 25 explicit `[VERIFY: ...]` markers. It also tells you that
Recital 51 imposes *no* obligation to provide updates, and that pure economic loss is excluded
(Recital 24), so a B2B SaaS whose failure mode is downtime may have low exposure. Read the free
tool's output first and decide whether you need the kit at all.

## Related

Different regulation, different question: the EU Cyber Resilience Act's Article 14 asks whether
anything you ship is being *actively exploited right now*, on a 24-hour reporting clock. That one
is [`cra-watch`](https://github.com/ntoledo319/cra-watch).

## Licence

MIT © Toledo Technologies LLC. Use it, fork it, ship it in your pipeline.

Engineering tooling, **not legal advice**. Not affiliated with, endorsed by, or connected to the
European Commission or endoflife.date. Data is fetched from endoflife.date's public API at runtime.
