# 🌟 Misshka's Learning Progress App

A delightful educational web application for children to learn mathematics and science through interactive games and activities, guided by Nova the Space Unicorn! ✨

## 🎯 Features

- **Interactive Math Games**: Addition with cute animal visualizations
- **Science Exploration**: Learn about space and animals (coming soon!)
- **Nova the Space Unicorn**: Friendly character guide
- **Progress Tracking**: Earn stars and track achievements
- **Child-Friendly Design**: Large buttons, colorful animations, engaging feedback

## 🚀 Getting Started

### Prerequisites

- Node.js 20+ installed
- npm or yarn package manager

### Installation & Running Locally

#### 1. Backend Setup

```bash
cd backend

# Install dependencies
npm install

# Start the backend server
npm run dev
```

The backend will start on `http://localhost:3000`

#### 2. Frontend Setup

Open a new terminal window:

```bash
cd frontend

# Install dependencies
npm install

# Start the frontend development server
npm run dev
```

The frontend will start on `http://localhost:5173`

### 3. Open the App

Open your browser and visit: **http://localhost:5173**

You'll see Misshka's Learning Adventure with Nova the Space Unicorn!

## 📁 Project Structure

```
Misshka-Learning-Progress-App/
├── frontend/          # React + TypeScript + Tailwind frontend
│   ├── src/
│   │   ├── components/    # Reusable UI components
│   │   ├── types/         # TypeScript type definitions
│   │   └── App.tsx        # Main app component
│   └── package.json
│
├── backend/           # Node.js + Express backend API
│   ├── src/
│   │   └── server.ts      # Express server
│   ├── prisma/
│   │   └── schema.prisma  # Database schema
│   └── package.json
│
└── docs/              # Architecture documentation
    ├── PRD.md
    ├── DESIGN_SYSTEM.md
    ├── FRONTEND_ARCHITECTURE.md
    └── BACKEND_ARCHITECTURE.md
```

## 🎮 How to Use

1. **Home Page**: Choose between Math Games or Science Fun
2. **Math Activity**: Click on "Math Games" to practice addition with animals
3. **Answer Questions**: Select the correct answer from the options
4. **Earn Stars**: Get stars for correct answers!
5. **Navigate**: Use the "Back to Home" button to return

## 🎨 Design System

- **Primary Color**: Red (#EF4444) - Misshka's favorite!
- **Purple**: (#7C3AED) - Space and magic theme
- **Gold**: (#FBBF24) - Stars and achievements
- **Character**: Nova the Space Unicorn with animated movements

## 🛠 Technology Stack

### Frontend
- React 18 with TypeScript
- Vite for blazing-fast development
- Tailwind CSS for styling
- Framer Motion for animations

### Backend
- Node.js 20 with Express
- TypeScript
- Prisma ORM
- SQLite database (development)

## 📚 Next Steps

This is an MVP (Minimum Viable Product). Planned features:

- [ ] Full authentication system
- [ ] Parent dashboard with progress tracking
- [ ] More math activities (subtraction, counting, shapes)
- [ ] Science activities (animals, space, physics)
- [ ] Achievement system with badges
- [ ] Screen time tracking (1 hour daily limit)
- [ ] Drawing tools
- [ ] Progress reports for parents
- [ ] Sound effects and narration
- [ ] Deployment to production

## 👨‍💻 Development

### Backend Development

```bash
cd backend
npm run dev        # Start development server with hot reload
npm run build      # Build for production
npm run start      # Run production build
```

### Frontend Development

```bash
cd frontend
npm run dev        # Start development server
npm run build      # Build for production
npm run preview    # Preview production build
```

## 📄 License

Created for Misshka with ❤️

---

**Built with love for a 6-year-old's learning journey!** 🎓✨
