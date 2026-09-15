import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import App from "./App";
import BoardPage from "./BoardPage";
import IssuePage from "./IssuePage";
import "./tokens.css";
import "./styles.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <BrowserRouter>
      <Routes>
        <Route element={<App />}>
          <Route path="/" element={<BoardPage />} />
          <Route path="/issue/:key" element={<IssuePage />} />
          <Route path="*" element={<BoardPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  </React.StrictMode>,
);
