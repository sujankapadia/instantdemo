# Local TTS Models (March 2026)

Open-source text-to-speech models that run locally with human-level quality. Any of these could be added as a `--tts` provider in render.py.

## Comparison

| Model | Quality | Voice Cloning | Speed | Hardware | Notable |
|---|---|---|---|---|---|
| **Chatterbox** | Outperforms ElevenLabs in blind tests | Yes (short sample) | Fast | GPU or Apple MPS | Emotion control, open source by Resemble AI |
| **Kokoro-82M** | Near-human, very natural | Limited | Extremely fast (<0.3s) | Runs on CPU, M1+ Mac, or GPU | Only 82M params — tiny and fast |
| **F5-TTS** | High quality, natural | Yes (reference audio) | Fast | GPU recommended | Good balance of quality and controllability |
| **Fish Speech V1.5** | High quality, multilingual | Yes (~10s sample) | Fast | GPU | Captures accent, tone, delivery style |
| **IndexTTS-2** | State-of-the-art | Yes | Moderate | GPU | Best word error rate and speaker similarity |
| **XTTS-v2** (Coqui) | Good | Yes (3-6s sample) | Moderate | GPU | Cross-language cloning |
| **CosyVoice2** | High quality | Yes | Ultra-low latency | GPU | Best for streaming/real-time |

## Most interesting for InstantDemo

- **Chatterbox** — if it genuinely beats ElevenLabs in blind tests, it could replace the paid ElevenLabs tier entirely. Free, local, human quality.
- **Kokoro-82M** — runs on CPU with no GPU needed. Could replace Piper as the default local TTS. Much more natural, tiny model.
- **Fish Speech** — best voice cloning from a short sample, which is exactly what the "custom voice" monetization tier would need.

## Current TTS providers in render.py

| Provider | Quality | Cost | Local? |
|---|---|---|---|
| **Piper** | Robotic | Free | Yes |
| **Google Cloud TTS** (WaveNet) | Natural | Free tier (1M chars/mo) | No |
| **ElevenLabs** | Most natural | Paid (~$5/mo starter) | No |

## Sources

- [Best Open-Source TTS Models 2026 — BentoML](https://www.bentoml.com/blog/exploring-the-world-of-open-source-text-to-speech-models)
- [Best Open Source Voice Cloning 2026 — SiliconFlow](https://www.siliconflow.com/articles/en/best-open-source-models-for-voice-cloning)
- [Chatterbox — Resemble AI](https://www.resemble.ai/chatterbox/)
- [Kokoro TTS, F5-TTS, SparkTTS Comparison — DigitalOcean](https://www.digitalocean.com/community/tutorials/best-text-to-speech-models)
- [Best ElevenLabs Alternatives — Open Source TTS Comparison](https://ocdevel.com/blog/20250720-tts)
