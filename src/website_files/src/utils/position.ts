import { ToastPosition } from "react-toastify";

export function positionFixedElement(ele: HTMLElement, pos: ToastPosition) {
  switch (pos) {
    case "top-right": {
      ele.style.top = "0px";
      ele.style.right = "0px";
      break;
    }
    case "top-center": {
      ele.style.top = "0px";
      ele.style.left = "50%";
      ele.style.transform = "translateX(-50%)";
      break;
    }
    case "top-left": {
      ele.style.top = "0px";
      ele.style.left = "0px";
      break;
    }
    case "bottom-right": {
      ele.style.bottom = "0px";
      ele.style.right = "0px";
      break;
    }
    case "bottom-center": {
      ele.style.bottom = "0px";
      ele.style.left = "50%";
      ele.style.transform = "translateX(-50%)";
      break;
    }
    case "bottom-left": {
      ele.style.bottom = "0px";
      ele.style.left = "0px";
      break;
    }
  }
}
