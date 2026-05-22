/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./templates/**/*.html", // Scans all HTML files in your Flask templates folder
    "./static/**/*.js"       // Scans any JS files where you might inject classes
  ],
  theme: {
    extend: {
      fontFamily: {
        // Combines the fonts used across your different pages
        sans: ['Inter', 'Plus Jakarta Sans', 'Poppins', 'sans-serif'],
      },
      colors: {
        // Aggregated from Cashier, Waiter, and Floorplan
        primary: '#1cb2b6',
        primaryDark: '#17989b',
        // Aggregated from Manager and Floorplan
        dark: '#0f172a',
        
        /* Note: manager.html originally used '#1d4ed8' for primary. 
           If you want to keep the manager dashboard blue, you can manually 
           update the HTML classes in manager.html to use 'bg-managerBlue' 
           instead of 'bg-primary'. */
        managerBlue: '#1d4ed8', 
      }
    }
  },
  plugins: [],
}