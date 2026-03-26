# How Kokoro Generates Speech

A technical explainer of Kokoro's architecture, from text input to audio waveform.

## The Pipeline

```
Text → Phonemes → PL-BERT embeddings → Style vectors → Duration/Pitch → Decoder → Audio waveform
        misaki        (linguistic         (voice           (prosody)      ISTFTNet
         G2P          understanding)     character)
```

## Step 1: Text to Phonemes (misaki G2P)

The `misaki` grapheme-to-phoneme library converts written text into phoneme sequences — the actual sounds of speech. "Hello" becomes /hɛˈloʊ/.

English spelling is notoriously inconsistent — "read" can be /riːd/ or /rɛd/, "though" and "through" look similar but sound completely different. G2P resolves this ambiguity so downstream components get a consistent representation of pronunciation.

## Step 2: Phonemes to Embeddings (PL-BERT)

A BERT-based encoder processes the phoneme sequence into dense vector representations. These embeddings capture linguistic structure — not sound, but the *meaning and context* that determines how speech should sound.

BERT isn't generating audio here. It's generating representations of linguistic structure that downstream components use to make acoustic decisions:

- "This is a question" → pitch rises at the end
- "This word is important" → longer duration, higher pitch
- "This is a comma" → brief pause

Think of it as: BERT reads the script and marks it up with acting notes ("stress this word, pause here, make this a question"). The decoder then performs the script based on those notes.

### What is PL-BERT?

PL-BERT (Phoneme-Level BERT) is a variant of BERT specifically pre-trained on phoneme sequences rather than words. Regular BERT's vocabulary is words/subwords — it tokenizes "hello" as one token. PL-BERT's vocabulary is phonemes — it sees /h/ /ɛ/ /l/ /oʊ/ as separate tokens. Its embeddings capture phoneme-level patterns: which sound combinations flow naturally, where stress falls, how pronunciation shifts in context.

**Architecture**: 12-layer ALBERT model, hidden size 768, intermediate size 2,048, 12 attention heads.

**Training data**: Wikipedia text, converted to phoneme sequences using G2P. Trained for 1M steps (~10 epochs) on 3 Nvidia A40 GPUs with batch size 192.

**Training tasks** (two simultaneous objectives):

1. **Masked phoneme prediction** — mask random phonemes, predict what they are. This is standard BERT-style self-supervised learning, teaching the model phoneme-level context patterns.

2. **Grapheme prediction** — given phonemes, predict the original written letters. This is the clever addition — it forces the model to understand the relationship between spelling and pronunciation. This helps with heteronyms like "read" (/riːd/ vs /rɛd/) and "lead" (/liːd/ vs /lɛd/), where surrounding context determines the correct pronunciation.

**Author**: Yinghao Aaron Li (same author as StyleTTS 2).

## Step 3: Style Vectors

This is Kokoro's key architectural idea, inherited from StyleTTS 2. Instead of directly generating audio from text, the model first works with a **style vector** — a compact representation of *how* something should be said (voice timbre, speaking rate, intonation, emotion).

Each voice (`af_heart`, `af_bella`, etc.) is essentially a different style vector. The style is applied through **Adaptive Instance Normalization (AdaIN)** — the same technique used in neural style transfer for images (turning photos into paintings). Here, it transfers a "speaking style" onto the linguistic content.

The original StyleTTS 2 used a diffusion model to sample style vectors at inference time (allowing random variation in delivery). Kokoro simplifies this — it uses pre-computed style vectors per voice. No diffusion sampling needed at runtime, which is a major reason it's so fast.

## Step 4: Duration and Pitch Prediction

The model predicts two things for each phoneme:

- **Duration** — how long each sound lasts (milliseconds per phoneme)
- **F0 (fundamental frequency)** — the pitch contour, which gives speech its melody and intonation

A **Source Module** (SourceModuleHnNSF) generates harmonic and noise signals based on the predicted F0. This is the raw "buzzing" that the decoder will shape into speech — analogous to how your vocal cords produce a buzz that your mouth then shapes into words.

## Step 5: Decoder (ISTFTNet)

The decoder takes the linguistic features, style-modulated representations, and source signals, and produces the final audio waveform. It uses **ISTFTNet** — a vocoder based on the **inverse Short-Time Fourier Transform (iSTFT)**.

Traditional neural vocoders (like WaveNet, HiFi-GAN) generate audio sample-by-sample — each of the 24,000 samples per second is predicted sequentially. This is slow.

ISTFTNet works in the **frequency domain** instead. It predicts frequency components (a spectrogram-like representation) and converts them to a waveform in one step using the inverse FFT. This is mathematically equivalent but computationally much cheaper — predicting a few hundred frequency bins per frame rather than thousands of individual samples.

The decoder also uses:
- **Residual blocks** with Snake activation functions (for modeling periodic signals like speech)
- **AdaIN conditioning** (applying the style vector throughout the decoder)

## Step 6: Adversarial Training

During training (not at inference time), Kokoro uses large pre-trained speech language models — specifically **WavLM** (a 300M+ parameter model from Microsoft) — as **discriminators**. These models have been trained on massive amounts of real speech and can detect subtle artifacts in generated audio.

The training loop:
1. Kokoro generates speech from text
2. WavLM judges whether it sounds real or synthetic
3. Kokoro adjusts its weights to fool WavLM
4. Repeat

This is the same idea as GANs (generative adversarial networks) in image generation. The discriminator is discarded after training — only Kokoro's 82M parameter generator is used at inference time. But the adversarial pressure during training forces the tiny model to produce audio that can fool a much larger model, pushing quality well beyond what 82M parameters would normally achieve.

## Why It's So Small (82M params)

Three design choices keep it tiny:

1. **Decoder-only** — no separate encoder network for processing reference audio at inference time (unlike models that need to encode a voice sample)
2. **Pre-computed style vectors** — no diffusion model needed at runtime. Each voice is a fixed vector, not sampled from a probabilistic model.
3. **ISTFTNet vocoder** — works in the frequency domain rather than generating individual audio samples, requiring fewer parameters for clean output

## Why It Sounds Good Despite Being Small

1. **Adversarial training with WavLM** — a 300M+ parameter speech model judges quality during training, forcing the 82M model to punch above its weight
2. **StyleTTS 2 architecture** — cleanly separates *what* is said (linguistic content) from *how* it's said (style), making each component simpler and more focused
3. **Quality training data** — a few hundred hours of clean, permissive audio rather than noisy web-scraped data
4. **PL-BERT pre-training** — phoneme-level language understanding trained on all of Wikipedia gives the model deep knowledge of English prosody patterns

## Sources

- [Kokoro-82M — HuggingFace](https://huggingface.co/hexgrad/Kokoro-82M)
- [Kokoro GitHub](https://github.com/hexgrad/kokoro)
- [StyleTTS 2 paper — Li et al.](https://arxiv.org/abs/2306.07691)
- [StyleTTS 2 architecture — DeepWiki](https://deepwiki.com/yl4579/StyleTTS2/3-system-architecture)
- [PL-BERT paper — Li et al.](https://arxiv.org/abs/2301.08810)
- [PL-BERT GitHub](https://github.com/yl4579/PL-BERT)
- [Kokoro architecture — Analytics Vidhya](https://www.analyticsvidhya.com/blog/2025/01/kokoro-82m/)
- [Kokoro model details — DeepWiki](https://deepwiki.com/Blaizzy/mlx-audio/3.2-api-reference)
