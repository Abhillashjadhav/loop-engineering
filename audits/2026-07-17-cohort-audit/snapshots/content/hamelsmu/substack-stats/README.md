# Substack Stats

An interactive dashboard for comparing public Substack newsletters by subscriber count, paid plan price, and modeled monthly revenue.

Live site: https://substack-stats.vercel.app

## What This Shows

- Scatterplot of public subscribers versus modeled monthly revenue
- Configurable paid conversion assumption
- Search and watched-newsletter labels
- Table view with sorting and highlighting
- Analysis and methods tabs explaining the lower-bound conversion data

The revenue model is an estimate:

```text
modeled monthly revenue = public subscribers x monthly plan price x paid conversion rate
```

It is not a report of actual Substack revenue.

## Data

The public data files live in `public/`:

- `substack_top50_research_with_paid_free.csv`
- `substack_price_tiers.json`

The generated TypeScript dataset is `src/newsletters.ts`.

## Development

```bash
npm install
npm run dev
```

## Validation

```bash
npm run build
npm run test:e2e
```

The e2e suite covers chart labels, hover cards, search, watched newsletters, filters, table sorting, analysis, methods, static assets, and responsive layouts.
