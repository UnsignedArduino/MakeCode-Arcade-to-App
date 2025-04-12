import { toast } from "react-toastify";

export interface LoadingToastCallbacks {
  success: () => void
  error: () => void
};

/* eslint-disable @typescript-eslint/no-empty-function */
export function createEmptyLoadingToastCallbacks(): LoadingToastCallbacks {
  return {
    success: () => {},
    error: () => {},
  };
}
/* eslint-enable @typescript-eslint/no-empty-function */

/* eslint-disable @typescript-eslint/no-floating-promises */
export function loadingToast(
  pending: string,
  success: string,
  error: string,
): LoadingToastCallbacks {
  let callbacks: LoadingToastCallbacks = createEmptyLoadingToastCallbacks();
  const p = new Promise<void>((resolve, reject) => {
    callbacks = {
      success: resolve,
      error: reject,
    };
  });
  toast.promise(p, {
    pending,
    success,
    error,
  });
  return callbacks;
}
/* eslint-enable @typescript-eslint/no-floating-promises */
