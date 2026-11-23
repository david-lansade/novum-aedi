import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Chemins relatifs : dist/ fonctionne quel que soit le chemin d'où il est servi (serveur local
// de l'application, ou tout autre serveur de fichiers).
export default defineConfig({
  base: "./",
  plugins: [react()],
  build: { outDir: "dist", emptyOutDir: true, chunkSizeWarningLimit: 1500 },
});
