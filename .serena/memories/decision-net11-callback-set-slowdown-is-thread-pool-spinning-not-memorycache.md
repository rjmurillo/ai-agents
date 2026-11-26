# Disabling thread pool spinning removed the MemoryCache Set slowdown with eviction callbacks on .NET 11.0.0

**Atomicity**: 90%
**Category**: .NET performance, benchmark method
**Source**: Agent session sweep, sessions dated 2026-11. Sweep ids E076, E077, E078. State checked on main at 1be533c496 (2026-11-26).

## Question

Is the MemoryCache Set slowdown on .NET 11.0.0 a MemoryCache regression or a thread pool effect?

## Conventional answer

An earlier benchmark attributed a +16.9% Set slowdown to the runtime or MemoryCache 11.0.0. One hypothesis blamed contention between the Set caller and callback threads. Earlier tests also appeared to show a benefit from changing the spurious dispatch threshold.

## First-principles position

A repro on a 4 CPU x64 Ubuntu box ran MemoryCache.Set with and without a no-op eviction callback. It covered .NET 10.0.15, 11.0.0-rc.1 and 11.0.0. Turning thread pool spinning off removed the callback slowdown and cut user CPU sharply. The no-callback row stayed flat, so the +16.9% figure was noise. The repro's `--control` flag floods the pool and distorted the earlier rc.1 headlines.

## Evidence with limits

- E076 (2026-11-19): the RawCache_Set row has no callback. It moved from +0.1% to +16.9% across runs, so that figure is noise. The callback case regressed 13.5% (median over six rounds) on 11.0.0 against 10.0.15.
- E076: the no-callback Set row stayed flat at 110.9 against 111.7 ns/op.
- E077 (2026-11-19): the callback row ran 875.1 ns/op on 11.0.0 default and 323.2 ns/op with `DOTNET_ThreadPool_UnfairSemaphoreSpinLimit=0`. rc.1 ran 338.6. A second callback row read 872.4, 450.1 and 438.5 on the same three settings.
- E077: user CPU per trial fell from 6021 ms to 509 ms in the first row, and from 5785 ms to 736 ms in the second.
- E078 (2026-11-19): `--control` floods the pool between trials and pushed rc.1 from about 340 to about 715 ns/op. A one-round check without it read 857.8 against 971.1.
- E078: setting the spurious-dispatch threshold to 0 gave mixed trials. A spin limit of 256 did not help. Turning spinning off did.
- Limits: One machine (4 CPUs, load average 4 to 28 during runs), one microbenchmark, a few rounds. Not tied to ai-agents code. The toggle points to thread pool spinning. A runtime maintainer did not confirm the link to the backport for runtime issue 132765.
- State on main at 1be533c496 (2026-11-26): no repo artifact. `performance-principles-detailed.md:51` shows `export ThreadPool_UnfairSemaphoreSpinLimit=0` as ARM64 tuning only. No memory covers this .NET 11 callback finding.

## Decision

Before blaming a library for a regression, isolate it with a no-callback control, a spin-limit toggle and CPU time. Do not run the pool-flooding `--control` flag when comparing runtimes.

## Related

- `.serena/memories/quality/performance-principles-detailed.md`
