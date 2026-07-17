# Semantic IDs: Training an LLM-Recommender Hybrid

**Teaching language models to speak in product IDs and natural language**   
[Writeup](https://eugeneyan.com/writing/semantic-ids/) | [Video Demo](https://www.youtube.com/watch?v=_0n4QS--3V8) | [Notebook Demo](demo.ipynb) | [Models on HF](https://huggingface.co/eugeneyan)

An experimental implementation of an LLM-recommender hybrid that can make recommendations via conversation. Unlike traditional approaches that use retrieval or tools, this model natively understands items as part of its vocabulary—it's "bilingual" in English and item IDs.

```python
# The model can seamlessly mix natural language and recommendations
INPUT = "I like animal and cute games. <|rec|>"
>>> "Animal Crossing: New Leaf", "DISNEY INFINITY Starter Pack", "Nintendogs + Cats"

# It can explain its recommendations
INPUT = "I just finished Dragon Quest Heroes II. Suggest another <|rec|> and explain why:"
>>> "Nights of Azure - PlayStation 4"
>>> "Both are action RPGs for PS4 with combat focus and character progression..."
```

## Quick Start

### Try the Demo

```bash
# Clone the repository
git clone https://github.com/eugeneyan/semantic-ids-llm.git
cd semantic-ids-llm

# Install dependencies with uv
uv sync

# Run the demo notebook
jupyter lab demo.ipynb
```

### Use Pre-trained Models

```python
from transformers import AutoModelForCausalLM, AutoTokenizer

# Load the finetuned model
model = AutoModelForCausalLM.from_pretrained(
    "eugeneyan/semantic-id-qwen3-8b-video-games",
    torch_dtype=torch.bfloat16,
    device_map="auto"
)
tokenizer = AutoTokenizer.from_pretrained(
    "eugeneyan/semantic-id-qwen3-8b-video-games"
)

# The model understands semantic IDs like <|sid_start|><|sid_64|><|sid_313|>...
```

## What Are Semantic IDs?

Traditional recommender systems use meaningless hash IDs (`B0040JHNQG`) for items. Semantic IDs (`<|sid_0|><|sid_256|><|sid_512|><|sid_768|>`) are hierarchical tokens that encode item information, where similar items share common prefixes.

This project trains a language model to:
1. **Understand items natively** - Items are tokens in the vocabulary, not retrieved entities
2. **Make recommendations** - Predict next items based on user history
3. **Converse naturally** - Steer recommendations through chat
4. **Explain choices** - Reason about why items are similar

The key innovation: **One unified model** instead of separate search/recommendation/chat systems.

## Project Structure

```
semantic-ids-llm/
├── notebooks/
│   ├── 01-prep-items-and-sequences.ipynb
│   ├── 02-clean-descriptions.ipynb
│   ├── 03-clean-titles.ipynb
│   ├── 04-augment-metadata.ipynb
│   ├── 05-update-items-and-sequences.ipynb
│   ├── 06-get-semantic-ids-per-asin.ipynb
│   ├── 07-get-semantic-ids-to-asin-sequences.ipynb
│   ├── 08-prep-finetuning-data.ipynb
│   ├── 09-evaluate-sasrec-baseline.ipynb
│   └── 10-evaluate-sasrec-semantic.ipynb
├── src/
│   ├── embed_items.py           # Item embedding with Qwen3-0.6B
│   ├── train_rqvae.py           # RQ-VAE for semantic IDs
│   ├── train_sasrec.py          # Baseline recommender
│   ├── train_sasrec_semantic_id.py  # Semantic ID recommender
│   ├── finetune_qwen3_8b_vocab.py   # Vocabulary extension
│   └── finetune_qwen3_8b_full.py    # Full model finetuning
├── demo.ipynb          # Interactive demo
├── pyproject.toml      # Dependencies
└── setup.sh            # GPU instance setup script
```

## Installation

### Local Setup

```bash
# Using uv
pip install uv
uv sync

# Or using pip
pip install -r requirements.txt
```

### GPU Setup

For training on your GPU instance

```bash
chmod +x setup.sh
./setup.sh
```

### Requirements

- Python 3.12+
- CUDA-capable GPU (8GB+ VRAM for inference, 48GB+ for training)
- ~50GB disk space for models and data

## Examples

### Basic Recommendation

```python
# Given user history, recommend next items
INPUT = """<|sid_start|><|sid_64|><|sid_313|><|sid_637|><|sid_768|><|sid_end|>,
           <|sid_start|><|sid_64|><|sid_447|><|sid_706|><|sid_768|><|sid_end|>
           <|rec|>"""

>>> "Mass Effect - Xbox 360"
```

### Natural Language Steering

```python
# Combine preferences with platform constraints
INPUT = "I like scifi and action games for Xbox. <|rec|>"

>>> "Star Wars Knights of the Old Republic - Xbox"
>>> "Halo 4 - Xbox 360"
>>> "Fallout: New Vegas - Ultimate Edition"
```

### Multi-turn Conversation

```python
# Turn 1
USER: "I'm looking for games similar to Mario Kart. <|rec|>"
ASSISTANT: "Sonic & All-Stars Racing", "Need for Speed"

# Turn 2
USER: "How about something similar but for Xbox? <|rec|>"
ASSISTANT: "Forza Motorsport 4", "SSX - Xbox 360"

# Turn 3
USER: "Suggest a bundle name for these"
ASSISTANT: "Ultimate Racing & Arcade Fun Bundle"
```

## Training Pipeline

### 1. Data Preparation

Using [Amazon Reviews 2023](https://amazon-reviews-2023.github.io) Video Games category:
- 66k products with rich metadata
- 79k user purchase sequences (avg length: 6.5 items)
- Cleaned with Gemini 2.5 Flash for quality

### 2. Semantic ID Generation

Train RQ-VAE to convert item embeddings → semantic IDs:

```python
# RQ-VAE with 3 quantization levels + 1 uniqueness level
uv run -m src.train_rqvae
```

### 3. Baseline Comparison

Evaluate semantic IDs vs regular IDs:

```python
# Train baseline SASRec
uv run -m src.train_sasrec

# Train semantic ID variant
uv run -m src.train_sasrec_semantic_id
```

### 4. Language Model Finetuning

Two-stage finetuning of Qwen3-8B:

```python
# Stage 1: Vocabulary extension (add semantic ID tokens)
uv run -m src.finetune_qwen3_8b_vocab

# Stage 2: Full finetuning
uv run -m src.finetune_qwen3_8b_full
```

## Results

### Recommendation Performance

| Model | Hit@10 | NDCG@10 | MRR |
|-------|--------|---------|-----|
| **Baseline SASRec** | 0.281 | 0.154 | 0.130 |
| **Semantic ID SASRec** | 0.202 | 0.114 | 0.101 |

The semantic ID model trades some accuracy for:
- **Cold-start handling** via shared prefixes
- **Natural language steerability**
- **Explainability** of recommendations

### Model Capabilities

**What it can do:**
- Recommend items based on history
- Explain recommendations
- Handle platform/genre constraints
- Name and describe bundles
- Multi-turn refinement

**Limitations:**
- Lower precision than specialized recommenders
- 4x inference cost (4 tokens per item)
- Requires careful RQ-VAE tuning

### Trained Models

Available on HuggingFace:
- [`eugeneyan/video-games-semantic-ids-mapping`](https://huggingface.co/datasets/eugeneyan/video-games-semantic-ids-mapping) - Item mappings
- [`eugeneyan/semantic-id-qwen3-8b-video-games`](https://huggingface.co/eugeneyan/semantic-id-qwen3-8b-video-games) - Finetuned model

## Citation

```bibtex
@article{yan2025semantic,
  title={How to Train an LLM-recommender Hybrid that Speaks English & Item IDs},
  author={Yan, Eugene},
  journal={eugeneyan.com},
  year={2025},
  url={https://eugeneyan.com/writing/semantic-ids/}
}
```

## References

Key papers that inspired this work:

- [TIGER: Recommender Systems with Generative Retrieval](https://arxiv.org/abs/2305.05065) (Rajput et al., 2023)
- [Better Generalization with Semantic IDs](https://arxiv.org/abs/2306.08121) (Singh et al., 2024)
- [RQ-VAE: Residual Quantized VAE](https://arxiv.org/abs/2107.03312) (Zeghidour et al., 2021)
- [SASRec: Self-Attentive Sequential Recommendation](https://arxiv.org/abs/1808.09781) (Kang & McAuley, 2018)

## Contributing

Contributions welcome! Areas of interest:
- Multi-modal semantic IDs (images, audio)
- Larger-scale experiments (millions of items)
- Alternative quantization methods
- Production deployment strategies

## License

MIT License - see [LICENSE](LICENSE) file for details.

## Discussion & Support

- **Writeup**: [Comments on eugeneyan.com](https://eugeneyan.com/writing/semantic-ids/)
- **Twitter/X**: [@eugeneyan](https://x.com/eugeneyan)

---

*Built with ♥️ by [Eugene Yan](https://eugeneyan.com) | Compute credits courtesy of [RunPod](https://runpod.io?ref=4uddqig9)*
