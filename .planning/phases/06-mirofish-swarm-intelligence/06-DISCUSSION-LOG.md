# Phase 6: MiroFish Swarm Intelligence - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-03-24
**Phase:** 06-mirofish-swarm-intelligence
**Areas discussed:** Agent Profile Design, Ensemble Integration Strategy, Simulation Trigger & Frequency, Fallback Behavior

---

## Agent Profile Design

| Option | Description | Selected |
|--------|-------------|----------|
| Markt-Experten Mix (5-8) | Breite Abdeckung: Tech Analyst, Fundamental, Zentralbank, Risiko, Momentum, Contrarian | |
| Kleines fokussiertes Team (3-4) | Nur wichtigste Rollen | |
| Grosses Gremium (10+) | Spezialisierte Rollen | |

**User's initial choice:** 4 Agenten, keine technische Analyse
**Revised choice:** 10 Agenten, alle nur Wirtschaft/Makro, sequenziell diskutierend, bis Konsens

| Option | Description | Selected |
|--------|-------------|----------|
| Claude waehlt 10 Wirtschafts-Rollen | Claude sucht die besten 10 makro Perspektiven | |
| Ich nenne meine Rollen | User gibt eigene Liste | |

**User's choice:** Claude waehlt 10 Wirtschafts-Rollen

| Option | Description | Selected |
|--------|-------------|----------|
| Du entscheidest (Runden) | Claude bestimmt optimal | |
| 2-3 Runden | Kurze Diskussion | |
| Bis Konsens | Laeuft bis Einigung | |

**User's choice:** Bis Konsens

**Sprache:**

| Option | Description | Selected |
|--------|-------------|----------|
| Englisch | LLMs performen besser | |
| Deutsch | Konsistent mit Projekt | |

**User's choice:** Deutsch
**Notes:** User explicitly wanted to revisit this area to change from 4 to 10 agents and add sequential discussion with reactions.

---

## Ensemble Integration Strategy

| Option | Description | Selected |
|--------|-------------|----------|
| Veto-Recht | MiroFish kann Trades blockieren, nicht selbst ausloesen | |
| Gewichteter Mix | 30% Gewichtung zum ML-Score | |
| Nur Bestaetigungs-Boost | Confidence erhoht bei Zustimmung | |
| Du entscheidest | Claude waehlt | |

**User's choice:** Veto-Recht

| Option | Description | Selected |
|--------|-------------|----------|
| Nebensignal (70-80% ML) | ML bleibt dominant | |
| Gleichwertig (50/50) | Gleiche Gewichtung | |
| Du entscheidest | Claude waehlt | |

**User's choice:** Nebensignal

---

## Simulation Trigger & Frequency

| Option | Description | Selected |
|--------|-------------|----------|
| Vor jedem Trade | Nur bei BUY/SELL Signal | |
| Regelmaessig (alle 15 Min) | Timer-basiert | |
| Einmal pro Session | Tageseinschaetzung | |

**User's choice:** "gleichzeitig" — parallel mit ML, aber seltener (gecached)

**LLM:**

| Option | Description | Selected |
|--------|-------------|----------|
| Ollama lokal | Lokal, keine Kosten | |
| LM Studio lokal | Anderes Interface | |
| OpenRouter (API) | Cloud, minimal Kosten | |

**User's choice:** Ollama lokal
**Notes:** User explicitly rejected OpenAI API — "das soll opensource laufen". Original MIRO-03 requirement (gpt-4o-mini) is overridden.

---

## Fallback Behavior

| Option | Description | Selected |
|--------|-------------|----------|
| Ohne MiroFish weitertraden | ML tradet normal weiter | |
| Alle Trades pausieren | Kein Trading ohne MiroFish | |
| Du entscheidest | Claude waehlt | |

**User's choice:** Ohne MiroFish weitertraden

| Option | Description | Selected |
|--------|-------------|----------|
| Ja, einmal warnen | Eine Warnung bei Offline | |
| Keine Benachrichtigung | Stille Degradierung | |
| Bei jedem Versuch | Warnung pro Tick | |

**User's choice:** Ja, einmal warnen

---

## Claude's Discretion

- 10 specific agent role names (economic/macro focus)
- Ollama model choice for 4GB VRAM
- Cache TTL for simulation results
- Simulation timeout
- Veto logging format

## Deferred Ideas

None
