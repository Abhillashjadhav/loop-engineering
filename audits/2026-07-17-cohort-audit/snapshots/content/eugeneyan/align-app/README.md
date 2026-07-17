# ALIGN Eval Frontend

This is the frontend code for [ALIGN Eval](https://aligneval.com), a prototype game to help you build and optimize LLM evaluators. Read about the workflow and how it was built [here](https://eugeneyan.com/writing/aligneval/).

## What is ALIGN Eval?

ALIGN Eval helps you build better LLM evaluators through:
- 🎮 A prototype game that makes building LLM-evaluators easy and fun
- 📊 Tools to evaluate your prompts against labeled data
- ✨ Semi-automatic optimization to improve your LLM-evaluators
- 🔄 An iterative workflow to align annotators with AI output, and AI with annotator input

While framed as a game to build LLM evaluators, you can use ALIGN Eval to craft and optimize any prompt that does binary classification!

## Getting Started

First, run the development server:

```bash
npm run dev
# or
yarn dev
# or
pnpm dev
# or
bun dev
```

Open [http://localhost:3000](http://localhost:3000) with your browser to see the result.

## Tech Stack

- **Framework**: Next.js with TypeScript
- **Styling**: Tailwind CSS
- **Fonts**: Uses [`next/font`](https://nextjs.org/docs/app/building-your-application/optimizing/fonts) to optimize and load [Geist](https://vercel.com/font)

## Contributing

ALIGN Eval is currently in beta. Please share constructive feedback and report bugs on [GitHub](https://github.com/eugeneyan/align-app) or [X](https://x.com/eugeneyan).
