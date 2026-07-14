# ENTCare AI v1.0
## ENT (Ear, Nose, Throat) & Head-Neck Health Intelligence Platform

## CRITICAL ENT EMERGENCY DISCLAIMER
- **Airway obstruction** (stridor, drooling, tripod positioning): 112/999/911 IMMEDIATELY
- **Sudden hearing loss** (unilateral, <72 hours): Urgent same-day ENT assessment
- **Peritonsillar abscess** (trismus, drooling, muffled voice): Urgent ENT/A&E
- **Severe/uncontrolled epistaxis**: Emergency assessment
- **Button battery exposure** (nose/ear/swallowed): Same-day removal, paediatric emergency
- All content is AI-generated educational research only — NOT medical advice

## Quick Start (Windows)
1. Extract ZIP to any folder
2. Double-click **START_ENTCare_AI.bat**
3. Auto-installs everything (2-5 min first time)
4. Browser opens at **http://localhost:5100**
5. Accept disclaimer and begin

## Security — AES-256-GCM + Software Safety Hardening
- API keys AES-256-GCM encrypted client-side before localStorage
- PBKDF2 key derivation (100,000 iterations) from device fingerprint
- XSS protection: escapeHtml(), escapeFilename(), sanitizeAIResponse()
- Backend rate limiting (30 req/60s), input sanitisation/bounding, provider whitelist
- No hardcoded secrets — all API keys from environment or client-supplied at runtime
- Opaque, non-enumerable file and report identifiers (UUID-based)
- Opaque error handling — no internal stack traces returned to client

## 6 AI Providers (All Real API Calls)
| Provider | Model | Get Key |
|---|---|---|
| Claude (Anthropic) | claude-sonnet-4-20250514 | console.anthropic.com |
| ChatGPT (OpenAI) | gpt-4o | platform.openai.com/api-keys |
| Gemini (Google) | gemini-2.0-flash | aistudio.google.com/apikey |
| Grok (xAI) | grok-2-latest | console.x.ai |
| DeepSeek | deepseek-chat | platform.deepseek.com/api_keys |
| Mistral AI | mistral-large-latest | console.mistral.ai/api-keys |

## Ambiguity Resolver
Query 2-6 AIs simultaneously (parallel) — synthesised best answer generated automatically.
Click **⚡ Ambiguity Resolver** in the Chat panel.

## Sections (14 Panels)
- **Conditions** — 20+ dropdown (ear, nose/sinus, throat/voice, head-neck, emergencies)
- **Ear** — 4 tabs: Infections, Hearing loss, Tinnitus/vertigo, Cholesteatoma
- **Nose & Sinus** — Rhinosinusitis, allergic rhinitis, nasal polyps, epistaxis
- **Throat & Voice** — Tonsillitis, peritonsillar abscess, chronic hoarseness, dysphagia
- **Head & Neck** — Neck lumps, thyroid nodules, head-neck cancer red flags
- **Paediatric ENT** — Glue ear, adenotonsillar hypertrophy, foreign bodies (button batteries)
- **Sleep & Snoring** — Obstructive sleep apnoea, CPAP, surgical options
- **Emergency** — Airway obstruction, severe epistaxis, sudden hearing loss, button batteries
- **India Context** — CSOM burden, tobacco-related oral cancer, AOI guidance, NPPCD
- **Assessment** — Symptom-based AI research with affected-side field

## India ENT Resources
- AOI: Association of Otolaryngologists of India (aoi-nhq.org) | AIIMS ENT: aiims.edu
- NPPCD: National Programme for Prevention and Control of Deafness
- PM-JAY: ENT surgical procedure insurance coverage
- Emergency: **112**

## Clinical Sources
AAO-HNS | ENT UK | WHO | NICE | AOI | PubMed

*ENTCare AI — For research and educational purposes only. Not medical advice.*
*ENT EMERGENCY: 112 (India) / 999 (UK) / 911 (US)*
