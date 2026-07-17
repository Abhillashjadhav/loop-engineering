# RADAR Platform - Prototype

Professional supply chain risk management dashboard demonstrating Decision Arbitrage through intelligent alert prioritization.

## Overview

RADAR is a B2B SaaS supply chain risk management platform that provides "Decision Arbitrage" - enabling supply chain executives to act on disruptions 48 hours faster than competitors.

**The Core Problem We Solve:**
Current risk tools generate 100+ daily alerts, causing cognitive overload. Supply chain managers ignore 67% of alerts because they can't distinguish critical risks from noise. RADAR solves this through revenue-weighted prioritization - showing ONLY the top 5-10 risks that actually threaten delivery/compliance/cost.

## Features

- **Executive Dashboard** - Revenue-weighted Top 5 Risks with real-time metrics
- **Interactive Global Map** - 20 supplier pins across global locations with risk visualization
- **Deep-dive Supplier Analysis** - Risk assessment across 12 categories
- **Sub-tier Network Visibility** - Tier 1 → Tier 2 → Tier 3 dependency mapping
- **Real-time Alert Feed** - Severity-based filtering with contextual intelligence

## Tech Stack

- **Framework:** React 18 + TypeScript (strict mode)
- **Styling:** Tailwind CSS v4
- **Routing:** React Router v7
- **Charts:** Recharts
- **Maps:** Leaflet.js with React-Leaflet
- **Icons:** Lucide React
- **Build Tool:** Vite

## Local Development

```bash
# Install dependencies
npm install

# Start development server
npm run dev

# Open http://localhost:5173
```

## Build

```bash
# Build for production
npm run build

# Preview production build
npm run preview
```

## Deployment

```bash
# Deploy to GitHub Pages
npm run deploy
```

## Project Structure

```
src/
├── components/
│   ├── Dashboard/       # Executive dashboard components
│   ├── MapView/         # Interactive global map
│   ├── SupplierDetail/  # Deep-dive supplier analysis
│   ├── AlertFeed/       # Real-time alert sidebar
│   └── Layout/          # Navigation and layout wrapper
├── data/
│   └── mockData.ts      # 20 supplier records with realistic data
├── types/
│   └── index.ts         # TypeScript interfaces
├── App.tsx              # Router configuration
└── main.tsx             # Entry point
```

## Risk Categories (12 Lenses)

1. Economic/Financial
2. Geopolitical
3. Tech/Cyber
4. ESG/Regulatory
5. Catastrophic/Systemic
6. Environmental/Climate
7. Multi-tier Supplier Viability
8. Logistics & Transport
9. Infrastructure
10. Labor & Social
11. Market Competition
12. Digital Transformation

## Color Palette

- **Primary Blue:** #1E40AF
- **Critical/Red:** #DC2626
- **Warning/Yellow:** #F59E0B
- **Success/Green:** #10B981
- **Background:** #F8FAFC
- **Text Dark:** #1E293B

## Live Demo

https://Abhillashjadhav.github.io/RADAR-UI/

---

Created for stakeholder demonstration - January 2025
