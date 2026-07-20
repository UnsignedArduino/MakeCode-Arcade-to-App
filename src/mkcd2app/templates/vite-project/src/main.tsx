import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { Bounce, ToastContainer } from "react-toastify";
import App from "./App.tsx";
import { GameConfiguration } from "./gameConfiguration.ts";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
    <ToastContainer
      position={GameConfiguration.Toasts.TOAST_POSITION}
      autoClose={GameConfiguration.Toasts.TOAST_AUTO_CLOSE}
      hideProgressBar={GameConfiguration.Toasts.TOAST_HIDE_PROGRESS_BAR}
      newestOnTop={GameConfiguration.Toasts.TOAST_NEWEST_ON_TOP}
      closeOnClick={GameConfiguration.Toasts.TOAST_CLOSE_ON_CLICK}
      rtl={GameConfiguration.Toasts.TOAST_RTL}
      pauseOnFocusLoss={GameConfiguration.Toasts.TOAST_PAUSE_ON_FOCUS_LOSS}
      draggable={false}
      pauseOnHover={GameConfiguration.Toasts.TOAST_PAUSE_ON_HOVER}
      theme={GameConfiguration.Toasts.TOAST_THEME}
      transition={Bounce}
    />
  </StrictMode>,
);
