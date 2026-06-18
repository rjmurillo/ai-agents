# Reflect Triggers (Detailed)

Full trigger tables and proactive-invocation guidance for the reflect skill.
SKILL.md keeps a short summary and points here.

## Trigger Phrases

| Trigger Phrase | Operation |
|----------------|-----------|
| `reflect on this session` | Extract learnings from conversation |
| `learn from this mistake` | Capture correction patterns |
| `capture what we learned` | Document session insights |
| `improve skill {name}` | Target specific skill memory |
| `what did we learn` | Review and store patterns |

Also monitor user phrasing such as "what if...", "ensure", or "don't forget". These phrases should route into the MEDIUM trigger table below and be batched until multiple edge-case signals appear.

### 🔴 HIGH Priority Triggers (Invoke Immediately)

| Trigger | Example | Why Critical |
|---------|---------|--------------|
| User correction | "no", "wrong", "not like that", "never do" | Captures mistakes to prevent repetition |
| Chesterton's Fence | "you removed that without understanding" | Documents architectural decisions |
| Immediate fixes | "debug", "root cause", "fix all" | Learns from errors in real-time |

### 🟡 MEDIUM Priority Triggers (Invoke After Multiple)

| Trigger | Example | Why Important |
|---------|---------|---------------|
| User praise | "perfect", "exactly", "great" | Reinforces successful patterns |
| Tool preferences | "use X instead of Y", "prefer", "rather than" | Builds workflow preferences |
| Edge cases | "what if X happens?", "don't forget", "ensure" | Captures scenarios to handle |
| Questions | Short questions after output | May indicate confusion or gaps |

### 🟢 LOW Priority Triggers (Invoke at Session End)

| Trigger | Example | Why Useful |
|---------|---------|------------|
| Repeated patterns | Frequent use of specific commands/tools | Identifies workflow preferences |
| Session end | After skill-heavy work | Consolidates all session learnings |

---

## Original Triggers (Still Supported)

| Phrase | Action |
|--------|--------|
| "reflect" | Full analysis of current session |
| "improve skill" | Target specific skill for improvement |
| "learn from this" | Extract learnings from recent interaction |
| "what did we learn" | Summarize accumulated learnings |

## Proactive Invocation Reminder

**Don't wait for users to ask!** Invoke reflect immediately when you detect:

1. **User says "no"** → Invoke reflect NOW (captures correction)
2. **User says "perfect"** → Invoke reflect NOW (captures success pattern)
3. **Multiple "what if" or edge-case signals appear** → Invoke reflect (captures scenario patterns)
4. **You used multiple skills** → Invoke reflect at END (captures all learnings)
5. **User corrected your output** → Invoke reflect IMMEDIATELY (critical learning)

**Why this matters**: Without proactive reflection, learnings are LOST. The Stop hook captures some patterns, but **manual reflection is MORE ACCURATE** because you have full conversation context.

**Cost**: ~30 seconds of analysis. **Benefit**: Prevents repeating mistakes forever.
