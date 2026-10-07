import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { z } from "zod";

import { App } from "./app/App";
import "./styles.css";

// zod compiles validators with new Function() when it can; the CSP forbids eval,
// so skip the attempt (and the CSP error it logs) altogether
z.config({ jitless: true });

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
