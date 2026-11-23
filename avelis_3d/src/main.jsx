import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import App from "./App.jsx";
import { chargerPolice } from "./police.js";
import "./style.css";

chargerPolice();
createRoot(document.getElementById("racine")).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
