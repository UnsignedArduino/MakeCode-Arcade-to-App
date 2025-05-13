import "./App.css";
import * as React from "react";
import {
  createEmptyLoadingToastCallbacks,
  loadingToast,
    type LoadingToastCallbacks,
} from "./utils/toasts";
import { toast } from "react-toastify";
import { GameConfiguration } from "./gameConfiguration.ts";
import { positionFixedElement } from "./utils/position.ts";

function App(): React.ReactNode {
  const simulatorRef = React.useRef<HTMLIFrameElement>(null);
  const statsRef = React.useRef<HTMLDivElement>(null);
  const [code, setCode] = React.useState("");
  const [simState, setSimState] = React.useState<unknown>({});

  const loadingGameToastCallbacksRef = React.useRef<LoadingToastCallbacks>(
    createEmptyLoadingToastCallbacks(),
  );
  const restartGameToastCallbacksRef = React.useRef<LoadingToastCallbacks>(
    createEmptyLoadingToastCallbacks(),
  );
  const [showNoFocusMessage, setShowNoFocusMessage] = React.useState(false);
  const [statsInnerText, setStatsInnerText] = React.useState("");

  React.useEffect(() => {
    try {
      setSimState(JSON.parse(localStorage.getItem("simState") ?? "{}"));
    } catch (err) {
      console.warn(
        // eslint-disable-next-line @typescript-eslint/restrict-template-expressions
        `Failed to load sim state, maybe first time run or simState is empty?\n${err}`,
      );
      setSimState({});
    }
  }, []);

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
    fetch("binary.js")
      .then((res) => {
        if (res.ok) {
          return res.text();
        } else {
          console.error(`Failed to load binary.js: ${res.statusText}`);
        }
      })
      .then((text) => {
        if (text) {
          console.log(
            `Loaded ${Math.round(text.length / 1024)} kb of binary.js`,
          );
          setCode(text);
          if (simulatorRef.current) {
            simulatorRef.current.src =
              "---simulator.html?hideSimButtons=1&noExtraPadding=1&fullscreen=1&autofocus=1&nofooter=1";
          } else {
            console.error("Simulator iframe ref is null");
          }
        } else {
          throw new Error("Failed to load binary.js: text is empty/undefined");
        }
      })
      .catch((err: unknown) => {
        console.error(err);
        loadingGameToastCallbacksRef.current.error();
      });
  }, []);

  React.useEffect(() => {
    function startSim() {
      console.log("Starting simulator");
      simulatorRef.current?.contentWindow?.postMessage({
        type: "run",
        parts: [],
        code,
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
      simulatorRef.current?.contentWindow?.postMessage({ type: "stop" });
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
            ({ closeToast }) => {
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
  }, [code, simState]);

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
        setStatsInnerText(statsText ?? "")
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
        ref={simulatorRef}
        allowFullScreen
        /* eslint-disable-next-line react-dom/no-unsafe-iframe-sandbox */
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
        hidden={!GameConfiguration.DebugStats.SHOW_STATS ||
            statsInnerText.length === 0}
      >
        {statsInnerText}
      </div>
    </div>
  );
}

export default App;
