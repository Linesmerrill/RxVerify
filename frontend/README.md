# RxVerify Frontend

> **Modern, demo-ready frontend for RxVerify - Multi-Database Drug Assistant**

## 🚀 **Features**

- **Modern HeroUI Pro Design**: Beautiful, responsive interface with glass morphism effects
- **Real-time API Integration**: Connects directly to RxVerify backend
- **Interactive Query Interface**: Easy-to-use form with character counting and validation
- **Advanced Search Options**: Configurable search parameters and result counts
- **Rich Results Display**: Formatted answers, source citations, and cross-validation results
- **Example Queries**: Pre-built examples to showcase system capabilities
- **Toast Notifications**: User feedback for all actions
- **Keyboard Shortcuts**: Ctrl+Enter to submit, Escape to reset
- **System Status Monitoring**: Real-time backend health checks

## 🎨 **Design Highlights**

- **Glass Morphism**: Modern backdrop blur effects and transparency
- **Gradient Backgrounds**: Beautiful color transitions
- **Smooth Animations**: Fade-in effects and smooth transitions
- **Responsive Layout**: Works perfectly on desktop, tablet, and mobile
- **HeroIcons Integration**: Professional icon set throughout the interface
- **Tailwind CSS**: Utility-first CSS framework for consistent styling

## 🛠️ **Setup**

### **Prerequisites**
- RxVerify backend running on `http://localhost:8000`
- Modern web browser with ES6+ support

### **Quick Start**

1. **Ensure backend is running**:
   ```bash
   # In your RxVerify project directory
   source venv/bin/activate.fish
   python -m uvicorn app.main:app --reload --port 8000
   ```

2. **Open the frontend**:
   - Simply open `frontend/index.html` in your web browser
   - Or serve it with a local HTTP server:
     ```bash
     cd frontend
     python -m http.server 8080
     # Then open http://localhost:8080
     ```

3. **Start querying**:
   - Type your drug-related question
   - Click "Get Answer" or press Ctrl+Enter
   - View results with full citations and cross-validation

## 🔧 **Configuration**

### **API Endpoint**
The frontend connects to the backend at `http://localhost:8000` by default. To change this:

1. Edit `frontend/app.js`
2. Update the `apiBaseUrl` in the `RxVerifyApp` constructor:
   ```javascript
   constructor() {
       this.apiBaseUrl = 'http://your-backend-url:port';
       // ...
   }
   ```

### **Customization**
- **Colors**: Modify the Tailwind config in `index.html`
- **Styling**: Update CSS classes and custom styles
- **Features**: Add new functionality in `app.js`

## 📱 **Usage**

### **Basic Query**
1. Enter your question in the text area
2. Click "Get Answer" button
3. View AI-generated response with citations

### **Advanced Options**
- Check "Advanced search options" for:
  - Results count (3-10 results)
  - Search type (Hybrid, Vector, Keyword)
  - Response style (Professional, Simple, Detailed)

### **Example Queries**
Click on any example query card to automatically load it into the input field.

### **Keyboard Shortcuts**
- **Ctrl+Enter**: Submit query
- **Escape**: Reset form
- **Tab**: Navigate between form elements

## 🎯 **Demo Scenarios**

### **For Stakeholders**
- Show the beautiful, professional interface
- Demonstrate real-time drug information retrieval
- Highlight source citations and data validation

### **For Developers**
- Showcase modern frontend architecture
- Demonstrate API integration patterns
- Highlight responsive design and UX best practices

### **For Medical Professionals**
- Demonstrate comprehensive drug information
- Show cross-source validation capabilities
- Highlight professional-grade interface design

## 🔍 **Troubleshooting**

### **Common Issues**

1. **"Network error" messages**:
   - Ensure RxVerify backend is running on port 8000
   - Check browser console for CORS errors
   - Verify network connectivity

2. **No results displayed**:
   - Check backend logs for errors
   - Verify API endpoints are working
   - Check browser console for JavaScript errors

3. **Styling issues**:
   - Ensure Tailwind CSS is loading properly
   - Check for CSS conflicts
   - Verify all CDN resources are accessible

### **Debug Mode**
Open browser developer tools (F12) to see:
- Console logs and errors
- Network requests and responses
- Element inspection and styling

## 🚀 **Deployment**

### **Production Deployment**
1. Update `apiBaseUrl` to production backend URL
2. Minify JavaScript and CSS files
3. Optimize images and assets
4. Deploy to web server or CDN

### **Docker Integration**
The frontend can be served from the same container as the backend:
- Copy frontend files to backend container
- Serve static files via FastAPI
- Single container deployment

## 📊 **Performance**

- **Lightweight**: Minimal dependencies, fast loading
- **Responsive**: Optimized for all device sizes
- **Efficient**: Minimal DOM manipulation and reflows
- **Accessible**: Keyboard navigation and screen reader support

## 🔮 **Future Enhancements**

- **Real-time Updates**: WebSocket integration for live data
- **Advanced Filtering**: Drug category and interaction filters
- **User Accounts**: Personalized query history and favorites
- **Mobile App**: React Native or Flutter mobile application
- **Offline Support**: Service worker for offline functionality

---

**Built with modern web technologies for the best user experience! 🎉**
