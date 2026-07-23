import "./App.css";
import * as React from "react";
import {
  createEmptyLoadingToastCallbacks,
  loadingToast,
  type LoadingToastCallbacks,
} from "./utils/toasts.ts";
import {toast} from "react-toastify";
import {GameConfiguration} from "./gameConfiguration.ts";
import {positionFixedElement} from "./utils/position.ts";
import binaryJs from "./assets/binary.js?raw";
import simulatorHtml from "./assets/---simulator.html?raw";

function App(): React.ReactNode {
  const simulatorRef = React.useRef<HTMLIFrameElement>(null);
  const statsRef = React.useRef<HTMLDivElement>(null);
  const [simState, setSimState] = React.useState<unknown>(() => {
    try {
      return JSON.parse(localStorage.getItem("simState") ?? "{}");
    } catch (err) {
      console.warn(
        `Failed to load sim state, maybe first time run or simState is empty?\n${err}`,
      );
      return {};
    }
  });

  const loadingGameToastCallbacksRef = React.useRef<LoadingToastCallbacks>(
    createEmptyLoadingToastCallbacks(),
  );
  const restartGameToastCallbacksRef = React.useRef<LoadingToastCallbacks>(
    createEmptyLoadingToastCallbacks(),
  );
  const gameCrashToastCloseCallbackRef = React.useRef<() => void>(() => {
  });
  const [showNoFocusMessage, setShowNoFocusMessage] = React.useState(false);
  const [statsInnerText, setStatsInnerText] = React.useState("");

  const srcdocHtml = React.useMemo(
    () =>
      simulatorHtml.replace(
        "</body>",
        `<script>addEventListener("DOMContentLoaded",()=>{pxsim.simButtonsHidden=true;document.getElementsByClassName("game-player")[0]?.classList.add("just-screen","no-padding");});</script></body>`,
      ),
    [],
  );

  React.useEffect(() => {
    localStorage.setItem("simState", JSON.stringify(simState));
  }, [simState]);

  React.useEffect(() => {
    loadingGameToastCallbacksRef.current = GameConfiguration.Toasts
      .ENABLE_LOADING_GAME_TOAST
      ? loadingToast(
        GameConfiguration.Toasts.LOADING_GAME_TOAST_PENDING_MSG,
        GameConfiguration.Toasts.LOADING_GAME_TOAST_SUCCESS_MSG,
        GameConfiguration.Toasts.LOADING_GAME_TOAST_ERROR_MSG,
      )
      : createEmptyLoadingToastCallbacks();
  }, []);

  React.useEffect(() => {
    function startSim() {
      console.log("Starting simulator");
      simulatorRef.current?.contentWindow?.postMessage({
        type: "run",
        parts: [],
        code: binaryJs,
        partDefinitions: [],
        // cdnUrl: "https://cdn.makecode.com",
        // version: "",
        storedState: simState,
        frameCounter: 1,
        options: {
          theme: "green",
          player: "",
        },
        id: `green-${Math.random()}`,
      });
    }

    function stopSim() {
      console.log("Stopping simulator");
      simulatorRef.current?.contentWindow?.postMessage({type: "stop"});
    }

    /* eslint-disable */
    function onMessageHandler(event: MessageEvent) {
      const data: any = event.data;
      // if (data.type !== "messagepacket") {
      //   alert(JSON.stringify(data));
      // }
      // console.log(data);
      if (data.type == "ready") {
        console.log("Simulator is ready");
        startSim();
        loadingGameToastCallbacksRef.current.success();
      } else if (data.type == "simulator") {
        switch (data.command) {
          case "restart": {
            console.log("Simulator requested restart");
            restartGameToastCallbacksRef.current = GameConfiguration.Toasts
              .ENABLE_RESTARTING_GAME_TOAST
              ? loadingToast(
                GameConfiguration.Toasts.RESTARTING_GAME_TOAST_PENDING_MSG,
                GameConfiguration.Toasts.RESTARTING_GAME_TOAST_SUCCESS_MSG,
                GameConfiguration.Toasts.RESTARTING_GAME_TOAST_ERROR_MSG,
              )
              : createEmptyLoadingToastCallbacks();
            stopSim();
            gameCrashToastCloseCallbackRef.current();
            setTimeout(() => {
              startSim();
              restartGameToastCallbacksRef.current.success();
            }, 500);
            break;
          }
          case "setstate": {
            if (data.stateValue === null) {
              setSimState({
                // @ts-ignore
                ...simState,
                [data.stateKey]: undefined,
              });
            } else {
              setSimState({
                // @ts-ignore
                ...simState,
                [data.stateKey]: data.stateValue,
              });
            }
            break;
          }
          default:
            break;
        }
      } else if (data.type == "debugger" && data.subtype == "breakpoint") {
        // Error most likely
        console.error("Simulator may have crashed!");
        console.error(data);
        if (GameConfiguration.Toasts.ENABLE_POSSIBLE_GAME_CRASH_TOAST) {
          toast.error(
            ({closeToast}) => {
              gameCrashToastCloseCallbackRef.current = closeToast;
              return (
                <div>
                  {
                    GameConfiguration.Toasts
                      .POSSIBLE_GAME_CRASH_TOAST_BEGINNING_MSG
                  }
                  <button
                    type="button"
                    onClick={() => {
                      console.log("Restarting simulator after crash");
                      closeToast();
                      restartGameToastCallbacksRef.current = GameConfiguration
                        .Toasts.ENABLE_RESTARTING_GAME_TOAST
                        ? loadingToast(
                          GameConfiguration.Toasts
                            .RESTARTING_GAME_TOAST_PENDING_MSG,
                          GameConfiguration.Toasts
                            .RESTARTING_GAME_TOAST_SUCCESS_MSG,
                          GameConfiguration.Toasts
                            .RESTARTING_GAME_TOAST_ERROR_MSG,
                        )
                        : createEmptyLoadingToastCallbacks();
                      stopSim();
                      setTimeout(() => {
                        startSim();
                        restartGameToastCallbacksRef.current.success();
                      }, 500);
                    }}
                  >
                    {
                      GameConfiguration.Toasts
                        .POSSIBLE_GAME_CRASH_TOAST_RESTART_BTN_MSG
                    }
                  </button>
                  {GameConfiguration.Toasts.POSSIBLE_GAME_CRASH_TOAST_END_MSG}
                </div>
              );
            },
            {
              autoClose:
              GameConfiguration.Toasts.POSSIBLE_GAME_CRASH_TOAST_AUTOCLOSE,
              closeOnClick:
              GameConfiguration.Toasts
                .POSSIBLE_GAME_CRASH_TOAST_CLOSE_ON_CLICK,
            },
          );
        }
      }
    }

    /* eslint-enable */

    window.addEventListener("message", onMessageHandler, false);
    return () => {
      window.removeEventListener("message", onMessageHandler, false);
    };
  }, [simState]);

  React.useEffect(() => {
    const checkStatsId = setInterval(() => {
      const statsText =
        simulatorRef.current?.contentDocument?.getElementById(
          "debug-stats",
        )?.innerText;
      if (statsRef.current) {
        positionFixedElement(
          statsRef.current,
          GameConfiguration.DebugStats.STATS_LOCATION,
        );
        setStatsInnerText(statsText ?? "");
        statsRef.current.innerText = statsText ?? "";
      }
    }, 100);

    return () => {
      clearInterval(checkStatsId);
    };
  }, []);

  React.useEffect(() => {
    if (!GameConfiguration.FocusDetector.ENABLE_FOCUS_DETECTOR) {
      return;
    }

    const checkFocusID = setInterval(() => {
      setShowNoFocusMessage(
        !document.hasFocus() ||
        !simulatorRef.current?.contentDocument?.hasFocus(),
      );
    }, 100);

    return () => {
      clearInterval(checkFocusID);
    };
  });

  return (
    <div>
      <iframe
        srcDoc={srcdocHtml}
        ref={simulatorRef}
        allowFullScreen
        sandbox="allow-popups allow-forms allow-scripts allow-same-origin"
      />
      <div
        style={{
          position: "fixed",
          top: 0,
          left: 0,
          width: "100%",
          height: "100%",
          backgroundColor:
          GameConfiguration.FocusDetector.FOCUS_DETECTOR_BACKGROUND_COLOR,
          pointerEvents: "none",
          zIndex: 1001,
        }}
        hidden={!showNoFocusMessage}
      >
        <div
          style={{
            position: "absolute",
            top: "50%",
            left: "50%",
            transform: "translate(-50%, -50%)",
            fontFamily: "monospace",
            textAlign: "center",
            color:
            GameConfiguration.FocusDetector.FOCUS_DETECTOR_FOREGROUND_COLOR,
            fontSize: GameConfiguration.FocusDetector.FOCUS_DETECTOR_FONT_SIZE,
            pointerEvents: "none",
          }}
        >
          Game not receiving input
        </div>
      </div>
      <div
        ref={statsRef}
        style={{
          fontFamily: "monospace",
          fontSize: GameConfiguration.DebugStats.STATS_FONT_SIZE,
          position: "fixed",
          background: GameConfiguration.DebugStats.STATS_BACKGROUND_COLOR,
          color: GameConfiguration.DebugStats.STATS_FOREGROUND_COLOR,
          padding: GameConfiguration.DebugStats.STATS_PADDING,
          zIndex: 1000,
        }}
        hidden={
          !GameConfiguration.DebugStats.SHOW_STATS ||
          statsInnerText.length === 0
        }
      >
        {statsInnerText}
      </div>
    </div>
  );
}

export default App;
