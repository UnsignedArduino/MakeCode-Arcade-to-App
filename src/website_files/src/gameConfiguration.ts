import { Theme, ToastPosition } from "react-toastify";

/* eslint-disable @typescript-eslint/no-namespace */
export namespace GameConfiguration {
  export namespace Toasts {
    // 'top-right' | 'top-center' | 'top-left' | 'bottom-right' | 'bottom-center' | 'bottom-left'
    export const TOAST_POSITION: ToastPosition = "bottom-right";
    export const TOAST_AUTO_CLOSE: false | number = 5000;
    export const TOAST_HIDE_PROGRESS_BAR = false;
    export const TOAST_NEWEST_ON_TOP = TOAST_POSITION.includes("bottom");
    export const TOAST_RTL = false;
    export const TOAST_CLOSE_ON_CLICK = false;
    export const TOAST_PAUSE_ON_FOCUS_LOSS = false;
    export const TOAST_PAUSE_ON_HOVER = false;
    // 'light' | 'dark' | 'colored'
    export const TOAST_THEME: Theme = "dark";

    export const ENABLE_LOADING_GAME_TOAST = true;
    export const LOADING_GAME_TOAST_PENDING_MSG = "Loading game...";
    export const LOADING_GAME_TOAST_SUCCESS_MSG = "Game loaded!";
    export const LOADING_GAME_TOAST_ERROR_MSG =
      "Failed to load game! Reload to try again.";

    export const ENABLE_RESTARTING_GAME_TOAST = true;
    export const RESTARTING_GAME_TOAST_PENDING_MSG = "Restarting game...";
    export const RESTARTING_GAME_TOAST_SUCCESS_MSG = "Game restarted!";
    export const RESTARTING_GAME_TOAST_ERROR_MSG =
      "Failed to restart game! Reload to try again.";

    export const ENABLE_POSSIBLE_GAME_CRASH_TOAST = true;
    export const POSSIBLE_GAME_CRASH_TOAST_BEGINNING_MSG =
      "It looks like the game may have crashed! To restart the game, press the backspace key or click ";
    export const POSSIBLE_GAME_CRASH_TOAST_RESTART_BTN_MSG = "here";
    export const POSSIBLE_GAME_CRASH_TOAST_END_MSG = ".";
    export const POSSIBLE_GAME_CRASH_TOAST_AUTOCLOSE: false | number = 30000;
    export const POSSIBLE_GAME_CRASH_TOAST_CLOSE_ON_CLICK = false;
  }

  export namespace DebugStats {
    export const SHOW_STATS = true;
    export const STATS_LOCATION: ToastPosition = "bottom-left";
    export const STATS_FONT_SIZE = "12px";
    export const STATS_BACKGROUND_COLOR = "rgba(0, 0, 0, 0.5)";
    export const STATS_FOREGROUND_COLOR = "white";
    export const STATS_PADDING = "10px";
  }

  export namespace FocusDetector {
    export const ENABLE_FOCUS_DETECTOR = true;
    export const FOCUS_DETECTOR_BACKGROUND_COLOR = "rgba(0, 0, 0, 0.5)";
    export const FOCUS_DETECTOR_FOREGROUND_COLOR = "white";
    export const FOCUS_DETECTOR_FONT_SIZE = "max(5vh, 24px)";
  }
}
