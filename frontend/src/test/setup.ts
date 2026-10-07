import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

// Testing Library unmounts after each test by itself only with Vitest globals enabled
afterEach(cleanup);

// jsdom has no <dialog> methods; enough of them for components that open dialogs
if (typeof HTMLDialogElement !== "undefined" && !HTMLDialogElement.prototype.showModal) {
  HTMLDialogElement.prototype.showModal = function showModal(this: HTMLDialogElement) {
    this.open = true;
  };
  HTMLDialogElement.prototype.close = function close(this: HTMLDialogElement) {
    this.open = false;
    this.dispatchEvent(new Event("close"));
  };
}
