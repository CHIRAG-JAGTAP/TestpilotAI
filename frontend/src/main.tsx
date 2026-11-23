import React from "react";
import ReactDOM from "react-dom/client";
import StatusBadge from "./components/StatusBadge";
import Generator from "./pages/Generator";
import "./styles.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <header><h1>TestPilot</h1><StatusBadge /></header>
    <main><Generator /></main>
  </React.StrictMode>
);
