# Signing proves who reported a test result, not that the result is true

## Question

ADR-101 requirement 2 needs test evidence a pull request cannot forge. Does a
signed publisher close it? Candidates: a GitHub App check run, an artifact
attestation, or direct Sigstore.

## Conventional answer

Sign the evidence with an identity the head cannot assume. ADR-101 line 215
says signed execution evidence "is now the only option that closes this
requirement".

## First-principles position

A signature authenticates the signer. It says nothing about how the signer
learned the result. Here the signer learns it from a process the candidate
controls. Against arbitrary candidate code in that process, a signed statement
is as forgeable as an unsigned one. Identity and truth are two properties, and
signing buys only the first.

## Evidence

The PR #6103 spike measured it on 2026-09-30. Two failing tests under `pytest`
exit 1. A candidate-authored `conftest.py` that rewrites reports turns them into
`2 passed`, exit 0, and a JUnit file reading `failures="0"`. With the conftest
removed, the same run reports `2 failed`. ADR-101 lists two forgeries (an
`os._exit(0)` session hook and a conftest that skips every item). This is a
third, and the ADR does not list it.

Spike doc: `.project-toolkit/analysis/adr-101-requirement-2-publisher-app-spike.md`.
Its point 4 says the ADR claim "does not hold". The ADR text change is reported
there and was not made, because it needs a debate log under `adr-review`.

## Decision

Do not cite a publisher App, an attestation, or Sigstore as closing a
requirement about result integrity. A publisher App meets the identity half only.
A base-owned run (`--noconftest`, a base-owned `-c` config, a base-owned canary
test that must fail) raises the cost but does not remove the residual.

Before accepting "signed, therefore true", ask where the signer got the value
and who controls that process.
