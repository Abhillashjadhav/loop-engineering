# Rich Text Editor Tutorials

Comprehensive tutorials for learning TipTap and CKEditor 5, with a focus on custom image handling, galleries, and advanced integrations.

## 🚀 Quick Start

**Start here:** [START_HERE.md](./START_HERE.md)

## 📚 Contents

1. **[START_HERE.md](./START_HERE.md)** - Your entry point! Quick start guide
2. **[EDITOR_COMPARISON_SUMMARY.md](./EDITOR_COMPARISON_SUMMARY.md)** - Quick comparison & decision guide
3. **[TIPTAP_TUTORIAL.md](./TIPTAP_TUTORIAL.md)** - Deep dive into TipTap (with devrelifier examples)
4. **[CKEDITOR_TUTORIAL.md](./CKEDITOR_TUTORIAL.md)** - Deep dive into CKEditor 5
5. **[HANDS_ON_EXERCISES.md](./HANDS_ON_EXERCISES.md)** - Practical coding exercises
6. **[ARCHITECTURE_DIAGRAMS.md](./ARCHITECTURE_DIAGRAMS.md)** - Visual architecture diagrams
7. **[README_TUTORIALS.md](./README_TUTORIALS.md)** - Comprehensive learning guide

## 🎯 What You'll Learn

- ✅ How rich text editors work internally
- ✅ Custom image click-to-replace functionality
- ✅ Building screenshot galleries with modals
- ✅ HTMX integration for server-rendered modals
- ✅ Markdown conversion systems
- ✅ Plugin/extension architecture patterns
- ✅ When to choose TipTap vs CKEditor

## 🎓 Based on Real-World Code

These tutorials analyze the **devrelifier** codebase - a production application that converts videos into blog posts using TipTap. You'll learn from real, working code, not toy examples.

## 🛠️ For Python Developers Learning Frontend

Written specifically for Python developers transitioning to frontend development. Each tutorial includes:
- Clear explanations of JavaScript concepts
- Pseudo code breakdowns
- Side-by-side comparisons
- Practical exercises

## 📖 Reading Order

### Beginner Path (Start here!)
1. [START_HERE.md](./START_HERE.md)
2. [EDITOR_COMPARISON_SUMMARY.md](./EDITOR_COMPARISON_SUMMARY.md)
3. [TIPTAP_TUTORIAL.md](./TIPTAP_TUTORIAL.md) (sections 1-3)
4. [HANDS_ON_EXERCISES.md](./HANDS_ON_EXERCISES.md) (Exercise 1.1-1.3)

### Advanced Path
1. Complete TipTap tutorial
2. [CKEDITOR_TUTORIAL.md](./CKEDITOR_TUTORIAL.md)
3. Complete all exercises
4. Build your own project!

### Visual Learner Path
1. [START_HERE.md](./START_HERE.md)
2. [ARCHITECTURE_DIAGRAMS.md](./ARCHITECTURE_DIAGRAMS.md)
3. Then dive into specific tutorials

## 💡 Key Features Covered

### TipTap Implementation
- Custom image click handlers
- HTMX-based screenshot gallery
- Markdown ↔ HTML conversion
- Auto-save system
- Custom toolbar creation

### CKEditor 5 Implementation
- Plugin architecture
- Command system
- Built-in Dialog API
- Model-View-Controller pattern
- Custom UI components

## 🎬 Quick Example

```javascript
// TipTap: Simple and direct
const editor = new Editor({
    extensions: [StarterKit, Image],
    editorProps: {
        handleDOMEvents: {
            click: (view, event) => {
                if (event.target instanceof HTMLImageElement) {
                    openGallery(); // Your custom function
                }
            }
        }
    }
});

// CKEditor: Structured with plugins
class ImageClickPlugin extends Plugin {
    init() {
        this.editor.editing.view.document.on('click', (evt, data) => {
            const element = this.editor.editing.mapper.toModelElement(data.target);
            if (element && element.name === 'imageBlock') {
                this._openGallery();
            }
        });
    }
}
```

## 🔗 Reference Project

These tutorials are based on analyzing [devrelifier](https://github.com/kentro-tech/devrelifier), which uses TipTap to create a video-to-blog-post editor with:
- Screenshot extraction from videos
- Click-to-replace image functionality
- HTMX-powered gallery modals
- Markdown storage with HTML editing

## 📦 What's Included

- **7 comprehensive tutorials** (~160KB total)
- **Complete code examples** with detailed comments
- **Pseudo code explanations** for complex logic
- **Visual architecture diagrams** (ASCII art)
- **Hands-on exercises** with solutions
- **Comparison guides** to help you choose

## 🎯 Who This Is For

- ✅ Python developers learning frontend
- ✅ Developers choosing between TipTap and CKEditor
- ✅ Anyone building custom rich text editors
- ✅ Developers studying editor architecture
- ✅ Frontend devs wanting to understand editors deeply

## 🚀 Getting Started

```bash
# Start with this
cat START_HERE.md

# Then read the comparison
cat EDITOR_COMPARISON_SUMMARY.md

# Then dive into specifics
cat TIPTAP_TUTORIAL.md
```

Or just open [START_HERE.md](./START_HERE.md) and follow the guide!

## 📝 License

These tutorials are provided as educational material. Use freely for learning purposes.

## 🤝 Contributing

Found an error? Have a suggestion? Feel free to open an issue or submit a pull request!

## 📧 Questions?

All answers are in the tutorials! They include:
- Detailed explanations
- Code examples
- Pseudo code breakdowns
- Common questions sections
- Debugging tips

**Happy Learning!** 🎓

---

**Created:** 2025-10-31  
**Author:** OpenHands AI Assistant  
**Based on:** devrelifier codebase analysis
