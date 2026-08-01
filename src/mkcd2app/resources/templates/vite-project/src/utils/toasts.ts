import { toast } from "react-toastify";

export interface LoadingToastCallbacks {
  success: () => void;
  error: () => void;
}

export function createEmptyLoadingToastCallbacks(): LoadingToastCallbacks {
  return {
    success: () => {},
    error: () => {},
  };
}

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
